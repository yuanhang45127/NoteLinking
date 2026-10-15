"""账号路由：注册 / 登录 / 登出 / 会话状态。

- 还没人注册时（users.json 为空）status 返回 mode=open，前端不弹登录框，
  所有请求以 default 用户身份读写，与旧版单人使用完全兼容；
- 一旦有人注册进入多用户模式，其余 /api/* 由 main.UserContextMiddleware
  统一拦截（401），每个用户的数据完全隔离。

会话通过 HttpOnly Cookie（nl_session）携带；HTTPS 部署时设置环境变量
NOTEBOOK_COOKIE_SECURE=1 可为 Cookie 附加 Secure 标记。
"""
import os

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from .. import config
from ..services import auth_service, mail_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Credentials(BaseModel):
    username: str
    password: str
    email: str = ""
    code: str = ""


def _key(request: Request, username: str) -> str:
    ip = auth_service.client_ip(request.client.host if request.client else "",
                                request.headers.get("x-real-ip", ""))
    return f"{username}|{ip}"


def _secure_cookies() -> bool:
    return os.environ.get("NOTEBOOK_COOKIE_SECURE", "").strip().lower() in ("1", "true", "yes")


def _issue_session(response: Response, username: str) -> None:
    response.set_cookie(
        key=auth_service.SESSION_COOKIE,
        value=auth_service.create_session_token(username),
        max_age=auth_service.SESSION_TTL,
        httponly=True,
        samesite="lax",
        secure=_secure_cookies(),
        path="/",
    )


@router.get("/status")
def auth_status():
    """会话状态。open = 还没人注册（单人开放模式，无需登录）。"""
    users = auth_service.users_count()
    return {
        "mode": "open" if users == 0 else "multi",
        "user": config.get_current_user() or None,
        "users": users,
        "email_verify": mail_service.email_verify_enabled(),
    }


@router.post("/email-code")
def email_code(body: dict):
    """发送注册验证码到指定邮箱（60 秒冷却，每小时每邮箱 5 次上限）。"""
    if not mail_service.smtp_configured():
        raise HTTPException(status_code=400, detail="邮件服务未配置")
    email = (body or {}).get("email", "").strip()
    if not mail_service.EMAIL_RE.match(email):
        raise HTTPException(status_code=400, detail="邮箱格式不正确")
    err, retry = mail_service.issue_code(email)
    if err:
        raise HTTPException(status_code=429, detail=err)
    if retry:
        raise HTTPException(status_code=429, detail=f"发送太频繁，请 {retry} 秒后再试")
    return {"sent": True, "cooldown": 60}


@router.post("/register")
def register(body: Credentials, request: Request, response: Response):
    """注册新用户并直接登录。新用户从零开始，不会接管 default 的数据。

    开启邮箱验证（NOTELINK_EMAIL_VERIFY=1 且 SMTP 已配置）时，必须提供
    email + 刚收到的验证码；同一邮箱只能绑定一个账号。
    同一 IP 每小时限 REGISTER_PER_HOUR（默认 5）个账号（邮箱验证之外再加一道）。
    """
    email = body.email.strip()
    if mail_service.email_verify_enabled():
        if not email or not body.code.strip():
            raise HTTPException(status_code=400, detail="请填写邮箱并输入验证码")
        if auth_service.email_taken(email):
            raise HTTPException(status_code=409, detail="该邮箱已绑定其他账号")
        if not mail_service.verify_code(email, body.code):
            raise HTTPException(status_code=400, detail="验证码错误或已过期（错 5 次作废），请重新获取")
    ip = auth_service.client_ip(request.client.host if request.client else "",
                                request.headers.get("x-real-ip", ""))
    if not auth_service.register_allowed(ip):
        raise HTTPException(status_code=429, detail="注册太频繁，请稍后再试")
    result = auth_service.register_user(body.username, body.password, email)
    auth_service.record_register(ip)
    _issue_session(response, result["username"])
    return result


@router.post("/login")
def login(body: Credentials, request: Request, response: Response):
    username = (body.username or "").strip()
    key = _key(request, username)
    left = auth_service.login_lock_remaining(key)
    if left:
        raise HTTPException(status_code=429, detail=f"尝试次数过多，已锁定，请 {left} 秒后再试")
    if not auth_service.verify_user(username, body.password or ""):
        auth_service.record_login_fail(key)
        left = auth_service.login_lock_remaining(key)
        hint = f"，再错 {auth_service.LOGIN_MAX_FAILS} 次将锁定 10 分钟" if not left else f"，已锁定，请 {left} 秒后再试"
        raise HTTPException(status_code=401, detail=f"用户名或密码不对{hint}")
    auth_service.clear_login_fails(key)
    _issue_session(response, username)
    return {"username": username}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(key=auth_service.SESSION_COOKIE, path="/")
    return {"ok": True}

"""账号路由：注册 / 登录 / 登出 / 会话状态。

- 还没人注册时（users.json 为空）status 返回 mode=open，前端不弹登录框，
  所有请求以 default 用户身份读写，与旧版单人使用完全兼容；
- 一旦有人注册进入多用户模式，其余 /api/* 由 main.UserContextMiddleware
  统一拦截（401），每个用户的数据完全隔离。

会话通过 HttpOnly Cookie（nl_session）携带；HTTPS 部署时设置环境变量
NOTEBOOK_COOKIE_SECURE=1 可为 Cookie 附加 Secure 标记。
"""
import os

from fastapi import APIRouter, HTTPException, Response
from pydantic import BaseModel

from .. import config
from ..services import auth_service, mail_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Credentials(BaseModel):
    username: str
    password: str
    claim_existing: bool = False
    email: str = ""
    code: str = ""


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
def register(body: Credentials, response: Response):
    """注册新用户并直接登录。首位注册者可勾选接管旧版单人数据（users/default）。

    开启邮箱验证（NOTELINK_EMAIL_VERIFY=1 且 SMTP 已配置）时，必须提供
    email + 刚收到的验证码；同一邮箱只能绑定一个账号。
    """
    email = body.email.strip()
    if mail_service.email_verify_enabled():
        if not email or not body.code.strip():
            raise HTTPException(status_code=400, detail="请填写邮箱并输入验证码")
        if auth_service.email_taken(email):
            raise HTTPException(status_code=409, detail="该邮箱已绑定其他账号")
        if not mail_service.verify_code(email, body.code):
            raise HTTPException(status_code=400, detail="验证码错误或已过期，请重新获取")
    result = auth_service.register_user(body.username, body.password, body.claim_existing, email)
    _issue_session(response, result["username"])
    return result


@router.post("/login")
def login(body: Credentials, response: Response):
    username = (body.username or "").strip()
    if not auth_service.verify_user(username, body.password or ""):
        raise HTTPException(status_code=401, detail="用户名或密码不对")
    _issue_session(response, username)
    return {"username": username}


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(key=auth_service.SESSION_COOKIE, path="/")
    return {"ok": True}

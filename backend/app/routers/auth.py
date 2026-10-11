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
from ..services import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


class Credentials(BaseModel):
    username: str
    password: str
    claim_existing: bool = False


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
    }


@router.post("/register")
def register(body: Credentials, response: Response):
    """注册新用户并直接登录。首位注册者可勾选接管旧版单人数据（users/default）。"""
    result = auth_service.register_user(body.username, body.password, body.claim_existing)
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

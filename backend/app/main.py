"""My Notebook 后端入口。

启动：cd backend && python run.py
文档：http://127.0.0.1:8000/docs （Swagger UI）
"""
import json
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException

from . import config
from .config import get_annotations_dir, get_checklists_dir, get_exams_dir, get_vault_dir
from .routers import (
    annotations,
    auth,
    books,
    chat,
    exams,
    graph,
    importer,
    integrations,
    llm,
    mcp,
    misc,
    notes,
    papers,
    settings,
    terms,
    topics,
    web,
)
from .services import auth_service, mcp_client
from .services.llm_service import LLMError
from .services.websearch_service import WebSearchError


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    # 旧版单用户数据（data/vault…）自动迁移到 users/default，行为不变
    auth_service.migrate_legacy_single_user()
    get_vault_dir()
    get_annotations_dir()
    get_exams_dir()
    get_checklists_dir()
    yield
    mcp_client.shutdown_all()


app = FastAPI(
    title="NoteLink API",
    description="基于 Markdown 的 AI 笔记系统：笔记（生成/高亮/概念双链）、知识图谱、考试备考。多人可用。",
    version="0.4.0",
    lifespan=lifespan,
)


# ---------------- 用户上下文 + 多用户鉴权（纯 ASGI，确保 contextvar 对接口可见） ----------------
_OPEN_PATHS = ("/api/health", "/api/auth/status")
_OPEN_PREFIXES = ("/api/auth/",)


def _cookie_from_scope(scope, name: str) -> str:
    for h, v in scope.get("headers") or []:
        if h.decode("latin-1").lower() == "cookie":
            for part in v.decode("latin-1").split(";"):
                k, _, val = part.strip().partition("=")
                if k == name:
                    return val
    return ""


async def _send_json(send, status: int, payload: dict):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    await send({"type": "http.response.start", "status": status,
                "headers": [(b"content-type", b"application/json; charset=utf-8"),
                            (b"content-length", str(len(body)).encode())]})
    await send({"type": "http.response.body", "body": body})


class UserContextMiddleware:
    """解析会话 → 设置当前用户；多用户模式下未登录访问 /api/* 返回 401。"""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            path = scope["path"]
            method = scope.get("method", "GET")
            token = _cookie_from_scope(scope, auth_service.SESSION_COOKIE)
            if not token:
                for h, v in scope.get("headers") or []:
                    if h.decode("latin-1").lower() == "x-session":
                        token = v.decode("latin-1")
                        break
            user = auth_service.resolve_session_token(token) or ""
            config.set_current_user(user)

            if (
                method != "OPTIONS"
                and path.startswith("/api")
                and path not in _OPEN_PATHS
                and not any(path.startswith(p) for p in _OPEN_PREFIXES)
                and auth_service.users_count() > 0
                and not user
            ):
                await _send_json(send, 401, {"detail": "请先登录"})
                return
        await self.app(scope, receive, send)


app.add_middleware(UserContextMiddleware)

# CORS：默认只放行 Vite 开发服务器——前端构建产物由本服务同源托管，生产不需要 CORS。
# 前端若部署在其他域名，用 NOTEBOOK_CORS_ORIGINS 显式列出（逗号分隔），
# 避免配合 allow_credentials 出现「反射任意 Origin」的过宽配置。
_CORS_ORIGINS = [
    o.strip()
    for o in os.environ.get(
        "NOTEBOOK_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173"
    ).split(",")
    if o.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(topics.router)
app.include_router(notes.router)
app.include_router(chat.router)
app.include_router(papers.router)
app.include_router(books.router)
app.include_router(annotations.router)
app.include_router(llm.router)
app.include_router(terms.router)
app.include_router(graph.router)
app.include_router(exams.router)
app.include_router(importer.router)
app.include_router(settings.router)
app.include_router(integrations.router)
app.include_router(mcp.router)
app.include_router(misc.router)
app.include_router(web.router)


@app.exception_handler(LLMError)
async def llm_error_handler(request, exc: LLMError):
    """模型调用失败统一返回 502，便于前端提示。"""
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.exception_handler(WebSearchError)
async def websearch_error_handler(request, exc: WebSearchError):
    """联网搜索/抓取失败统一返回 502，便于前端提示。"""
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.get("/api/health", tags=["meta"])
def health():
    return {"ok": True, "service": "my-notebook", "version": app.version}


# ---------------- 访问令牌（部署到公网时用） ----------------
# 设置环境变量 NOTEBOOK_TOKEN 后，所有 /api/*（除 /api/health）都需要携带令牌：
#   请求头 X-Notebook-Token: <token>  或查询参数 ?token=<token>
# 不设置则完全关闭校验（本地使用不受影响）。
#
# 内网免令牌：设置 NOTEBOOK_TRUSTED_MARKER 后，携带
#   X-Notebook-Trusted: <marker>
# 的请求跳过令牌校验。该标记头由内网 nginx 反代注入；对公网入口必须在
# nginx 中显式置空（proxy_set_header X-Notebook-Trusted ""），
# 否则公网客户端可自带该头绕过校验。
_ACCESS_TOKEN = os.environ.get("NOTEBOOK_TOKEN", "").strip()
_TRUSTED_MARKER = os.environ.get("NOTEBOOK_TRUSTED_MARKER", "").strip()


@app.middleware("http")
async def token_guard(request: Request, call_next):
    if _ACCESS_TOKEN:
        path = request.url.path
        if (
            request.method != "OPTIONS"
            and path.startswith("/api")
            and path not in ("/api/health", "/api/auth/status")
        ):
            if not (
                _TRUSTED_MARKER
                and secrets.compare_digest(
                    request.headers.get("x-notebook-trusted") or "", _TRUSTED_MARKER
                )
            ):
                supplied = (
                    request.headers.get("x-notebook-token")
                    or request.query_params.get("token")
                    or ""
                )
                if not secrets.compare_digest(supplied, _ACCESS_TOKEN):
                    return JSONResponse(status_code=401, content={"detail": "需要访问令牌"})
    return await call_next(request)


class SPAStaticFiles(StaticFiles):
    """前端构建产物静态服务：未命中的路径回退到 index.html（SPA 路由）。

    兼容新旧 Starlette：旧版返回 404 响应，新版（≥0.33）抛 HTTPException(404)。
    /api/* 不做 SPA 回退——接口 404 保持 JSON 404，避免误回 HTML。
    index.html 不缓存，避免发版后浏览器拿着旧入口加载旧资源。
    """

    async def get_response(self, path: str, scope):
        fallback = not path.startswith("api/")
        try:
            response = await super().get_response(path, scope)
            if response.status_code == 404 and fallback:
                response = await super().get_response("index.html", scope)
        except HTTPException as exc:
            if exc.status_code != 404 or not fallback:
                raise
            response = await super().get_response("index.html", scope)
        if response.status_code == 200 and str(getattr(response, "path", "")).endswith("index.html"):
            response.headers["Cache-Control"] = "no-cache"
        return response


# 前端 build 后由同一服务直接托管（backend/app → 仓库根/frontend/dist）
# 注意：必须放在所有 API 路由之后，否则会遮蔽后注册的接口
_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _DIST.exists():
    app.mount("/", SPAStaticFiles(directory=_DIST, html=True), name="spa")

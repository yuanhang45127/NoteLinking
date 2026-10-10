"""My Notebook 后端入口。

启动：cd backend && python run.py
文档：http://127.0.0.1:8000/docs （Swagger UI）
"""
from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import get_annotations_dir, get_exams_dir, get_vault_dir
from .routers import (
    annotations,
    exams,
    graph,
    importer,
    llm,
    misc,
    notes,
    settings,
    terms,
    topics,
)
from .services.llm_service import LLMError


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    get_vault_dir()
    get_annotations_dir()
    get_exams_dir()
    yield


app = FastAPI(
    title="My Notebook API",
    description="基于 Markdown 文件的笔记系统后端：笔记（大模型生成 + 高亮 + 词条双链）、知识图谱、考试备考。",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 本地开发；后续前端上线可收紧
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(topics.router)
app.include_router(notes.router)
app.include_router(annotations.router)
app.include_router(llm.router)
app.include_router(terms.router)
app.include_router(graph.router)
app.include_router(exams.router)
app.include_router(importer.router)
app.include_router(settings.router)
app.include_router(misc.router)


@app.exception_handler(LLMError)
async def llm_error_handler(request, exc: LLMError):
    """模型调用失败统一返回 502，便于前端提示。"""
    return JSONResponse(status_code=502, content={"detail": str(exc)})


@app.get("/api/health", tags=["meta"])
def health():
    return {"ok": True, "service": "my-notebook", "version": app.version}


class SPAStaticFiles(StaticFiles):
    """前端构建产物静态服务：未命中的路径回退到 index.html（SPA 路由）。"""

    async def get_response(self, path: str, scope):
        response = await super().get_response(path, scope)
        if response.status_code == 404:
            return await super().get_response("index.html", scope)
        return response


# 前端 build 后由同一服务直接托管（backend/app → 仓库根/frontend/dist）
# 注意：必须放在所有 API 路由之后，否则会遮蔽后注册的接口
_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"
if _DIST.exists():
    app.mount("/", SPAStaticFiles(directory=_DIST, html=True), name="spa")

"""词条（双链解释文档）路由。"""
from fastapi import APIRouter, Query
from pydantic import BaseModel
from typing import Optional

from ..schemas import TermRequest
from ..services import term_service, vault
from ..services.llm_service import stream_llm
from .llm import sse_response

router = APIRouter(prefix="/api", tags=["terms"])


class TermToNoteRequest(BaseModel):
    """概念转完整笔记：path 为概念文档路径（schemas.py 正被他处改动，模型暂内联于此）。"""
    path: str
    language: str = "zh"
    provider: Optional[str] = None
    model: Optional[str] = None


@router.post("/terms")
async def create_term(body: TermRequest):
    """选中文本点「什么意思」：结合上下文生成/追加词条解释文档（双链）。"""
    return await term_service.create_term_doc(
        body.path,
        body.term,
        body.context_before,
        body.context_after,
        body.language,
        body.regenerate,
        body.provider or "",
        body.model or "",
    )


@router.post("/terms/stream")
async def stream_term(body: TermRequest):
    """概念解释流式生成：SSE 增量输出，结束时落盘并返回 saved_path。"""
    plan = await term_service.prepare_term(
        body.path, body.term, body.context_before, body.context_after, body.language
    )

    async def gen():
        buf = []
        async for delta in stream_llm(body.provider or "", plan["messages"], body.model or ""):
            buf.append(delta)
            yield {"type": "delta", "text": delta}
        saved = term_service.save_term_doc(plan, "".join(buf), regenerate=body.regenerate)
        done = {"type": "done", "saved_path": saved["path"]}
        for k in ("is_new", "regenerated", "appended"):
            if k in saved:
                done[k] = saved[k]
        yield done

    return sse_response(gen())


@router.post("/terms/to-note/stream")
async def stream_term_to_note(body: TermToNoteRequest):
    """概念转完整笔记：以概念文档为底稿，从这个概念出发流式生成一篇深入讲解
    （具体解释 + 用处）的普通笔记，结束时落盘到主题根下并返回 saved_path。"""
    plan = term_service.prepare_to_note(body.path, body.language)

    async def gen():
        buf = []
        async for delta in stream_llm(body.provider or "", plan["messages"], body.model or ""):
            buf.append(delta)
            yield {"type": "delta", "text": delta}
        saved = term_service.save_to_note(plan, "".join(buf))
        yield {"type": "done", "saved_path": saved["path"]}

    return sse_response(gen())


@router.get("/terms")
def list_terms(topic: str = ""):
    return {"terms": term_service.list_terms(topic)}


@router.get("/terms/resolve")
def resolve_term(name: str = Query(...), topic: str = ""):
    """悬浮解释 / 点击跳转：按名称找词条文档，找不到返回 404。"""
    note = term_service.resolve_term_reference(name, topic)
    if note is None:
        return {"found": False}
    return {"found": True, **note}

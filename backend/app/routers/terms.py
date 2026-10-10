"""词条（双链解释文档）路由。"""
from fastapi import APIRouter, Query

from ..schemas import TermRequest
from ..services import term_service, vault

router = APIRouter(prefix="/api", tags=["terms"])


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

"""联网搜索与网页抓取路由。"""
from typing import Optional

from fastapi import APIRouter, Query
from pydantic import BaseModel

from ..services import websearch_service

router = APIRouter(prefix="/api/web", tags=["web"])


@router.get("/search")
async def web_search(q: str = Query(...), max_results: Optional[int] = None):
    """联网搜索（需在「设置 → 联网搜索」启用并配置服务商）。"""
    return await websearch_service.search(q, max_results)


class WebFetchIn(BaseModel):
    url: str


@router.post("/fetch")
async def web_fetch(body: WebFetchIn):
    """抓取网页正文（标题 + 正文文本），供 AI 展开搜索结果里的链接。"""
    return await websearch_service.fetch_webpage(body.url)

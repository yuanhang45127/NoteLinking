"""知识图谱路由：由全库 [[双链]] 自动生成。"""
from fastapi import APIRouter

from ..services.graph_service import build_graph

router = APIRouter(prefix="/api", tags=["graph"])


@router.get("/graph")
def graph(topic: str = ""):
    return build_graph(topic)

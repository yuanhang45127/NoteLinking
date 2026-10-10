"""主题与目录树路由。"""
from fastapi import APIRouter

from ..schemas import TopicCreate, TopicRename
from ..services import vault

router = APIRouter(prefix="/api", tags=["topics"])


@router.get("/topics")
def list_topics():
    return {"topics": vault.list_topics()}


@router.post("/topics")
def create_topic(body: TopicCreate):
    return vault.create_topic(body.name)


@router.patch("/topics/{name}")
def rename_topic(name: str, body: TopicRename):
    return vault.rename_topic(name, body.name)


@router.delete("/topics/{name}")
def delete_topic(name: str, recursive: bool = False):
    vault.delete_topic(name, recursive=recursive)
    return {"ok": True}


@router.get("/tree")
def get_tree(path: str = ""):
    return vault.get_tree(path)

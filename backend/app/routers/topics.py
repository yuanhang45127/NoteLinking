"""主题与目录树路由。"""
from fastapi import APIRouter

from ..schemas import TopicCreate, TopicEmoji, TopicRename
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


@router.put("/topics/{name}/emoji")
def set_topic_emoji(name: str, body: TopicEmoji):
    """设置/清除主题 emoji 图标（传空字符串清除）。"""
    return vault.set_topic_emoji(name, body.emoji)


@router.delete("/topics/{name}")
def delete_topic(name: str, recursive: bool = False):
    vault.delete_topic(name, recursive=recursive)
    return {"ok": True}


@router.get("/tree")
def get_tree(path: str = ""):
    return vault.get_tree(path)

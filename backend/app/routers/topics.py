"""主题与目录树路由。"""
from fastapi import APIRouter

from ..schemas import TopicCreate, TopicEmoji, TopicRename
from ..services import papers_store, vault

router = APIRouter(prefix="/api", tags=["topics"])


@router.get("/topics")
def list_topics():
    return {"topics": vault.list_topics()}


@router.post("/topics")
def create_topic(body: TopicCreate):
    return vault.create_topic(body.name)


@router.patch("/topics/{name}")
def rename_topic(name: str, body: TopicRename):
    result = vault.rename_topic(name, body.name)
    papers_store.rename_topic_papers(name, body.name)
    return result


@router.put("/topics/{name}/emoji")
def set_topic_emoji(name: str, body: TopicEmoji):
    """设置/清除主题 emoji 图标（传空字符串清除）。"""
    return vault.set_topic_emoji(name, body.emoji)


@router.delete("/topics/{name}")
def delete_topic(name: str, recursive: bool = False):
    vault.delete_topic(name, recursive=recursive)
    papers_store.delete_topic_papers(name)  # 文献库随主题一并清理
    return {"ok": True}


@router.get("/tree")
def get_tree(path: str = ""):
    return vault.get_tree(path)

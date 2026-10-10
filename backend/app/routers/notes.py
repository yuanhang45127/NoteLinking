"""笔记 CRUD、反链与全文搜索路由。"""
from fastapi import APIRouter, HTTPException, Query

from ..schemas import NoteCreate, NoteMove, NoteSave
from ..services import annotations_store, vault

router = APIRouter(prefix="/api", tags=["notes"])


@router.get("/notes")
def read_note(path: str = Query(...)):
    note = vault.read_note(path)
    note["annotations"] = annotations_store.list_annotations(path)
    note["backlinks"] = vault.list_backlinks(path)
    return note


@router.post("/notes")
def create_note(body: NoteCreate):
    return vault.create_note(body.path, body.content, overwrite=body.overwrite)


@router.put("/notes")
def save_note(body: NoteSave):
    return vault.save_note(body.path, body.content)


@router.post("/notes/move")
def move_note(body: NoteMove):
    return vault.move_note(body.src, body.dst)


@router.delete("/notes")
def delete_note(path: str = Query(...)):
    vault.delete_note(path)
    return {"ok": True}


@router.get("/notes/backlinks")
def backlinks(path: str = Query(...)):
    return {"backlinks": vault.list_backlinks(path)}


@router.get("/search")
def search(q: str = Query(...), topic: str = "", limit: int = 50):
    return {"results": vault.search_vault(q, topic, limit)}


@router.get("/notes/resolve-link")
def resolve_link(target: str = Query(...), topic: str = ""):
    """解析 [[双链]] 目标 → 库内笔记（悬浮预览/跳转用）。"""
    index = vault.build_link_index()
    candidates = [i for i in index.values() if i["name"] == target]
    if not candidates:
        raise HTTPException(status_code=404, detail=f"链接目标不存在：{target}")
    chosen = next((c for c in candidates if not topic or c["topic"] == topic), candidates[0])
    return vault.read_note(chosen["path"])

"""笔记 CRUD、反链与全文搜索路由。"""
from typing import List

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from ..schemas import NoteCreate, NoteMove, NoteSave
from ..services import annotations_store, vault
from ..utils import sanitize_filename

router = APIRouter(prefix="/api", tags=["notes"])


class NoteBatch(BaseModel):
    action: str  # delete | move
    paths: List[str]
    target: str = ""  # move：目标主题（根目录）


class NotePin(BaseModel):
    path: str
    pinned: bool


class NoteFinish(BaseModel):
    path: str
    finished: bool


@router.get("/pinned")
def pinned_notes():
    """全库置顶笔记（跨主题，侧边栏顶部「置顶」区用）。"""
    return {"pinned": vault.list_pinned()}


@router.post("/notes/pin")
def pin_note(body: NotePin):
    """设置/取消某篇笔记的置顶（写 frontmatter）。"""
    return vault.set_pinned(body.path, body.pinned)


@router.post("/notes/finish")
def finish_note(body: NoteFinish):
    """标记/取消某篇笔记「看完」（写 frontmatter）。"""
    return vault.set_finished(body.path, body.finished)


@router.get("/notes")
def read_note(path: str = Query(...)):
    note = vault.read_note(path)
    note["annotations"] = annotations_store.list_annotations(path)
    note["backlinks"] = vault.list_backlinks(path)
    note["concept_refs"] = _concept_refs(note)
    return note


def _concept_refs(note: dict) -> list:
    """本文涉及的概念：概念文档名在正文中出现（纯文本或 [[双链]]）即算，带出现次数。

    前端据此把正文中的纯文本概念名自动渲染为可悬浮/跳转的概念链接。
    """
    if note.get("type") != "note":
        return []
    from ..markdown_utils import extract_wiki_links

    content = note["content"]
    linked = set(extract_wiki_links(content))
    refs = []
    for info in vault.build_link_index().values():
        if info["type"] != "term" or info["path"] == note["path"]:
            continue
        name = info["name"]
        count = content.count(name)
        if count == 0 and name not in linked:
            continue
        refs.append({"name": name, "path": info["path"], "count": max(count, 1)})
    refs.sort(key=lambda r: -r["count"])
    return refs


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


@router.post("/notes/batch")
def batch_notes(body: NoteBatch):
    """批量删除 / 批量移动到目标主题根目录。返回逐条成功与失败结果。"""
    if body.action not in ("delete", "move"):
        raise HTTPException(status_code=400, detail="action 仅支持 delete / move")
    if not body.paths:
        raise HTTPException(status_code=400, detail="paths 不能为空")

    ok, failed = [], []
    if body.action == "delete":
        for p in body.paths:
            try:
                vault.delete_note(p)
                ok.append(p)
            except HTTPException as e:
                failed.append({"path": p, "detail": e.detail})
        return {"ok": ok, "failed": failed}

    target = sanitize_filename(body.target, "")
    if not target:
        raise HTTPException(status_code=400, detail="移动目标主题不能为空")
    for p in body.paths:
        try:
            vault.move_note(p, f"{target}/{p.split('/')[-1]}")
            ok.append(p)
        except HTTPException as e:
            failed.append({"path": p, "detail": e.detail})
    return {"ok": ok, "failed": failed}

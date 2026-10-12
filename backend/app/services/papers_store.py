"""文献库存储：按主题存放 JSON（data/papers/<主题>.json）。

Zotero 思路的轻量实现：收录（arXiv 检索 / 手动添加）、元数据、标签、读状态、想法。
"""
import datetime
import json
import uuid
from pathlib import Path
from typing import Dict, List

from fastapi import HTTPException

from ..config import get_papers_dir
from ..utils import sanitize_filename

READ_STATUS = ("unread", "reading", "done")


def _file_for(topic: str) -> Path:
    return get_papers_dir() / (sanitize_filename(topic, "topic") + ".json")


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _read(f: Path) -> List[Dict]:
    if not f.exists():
        return []
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return []
    items = data.get("items", []) if isinstance(data, dict) else data
    return items if isinstance(items, list) else []


def _write(topic: str, items: List[Dict]) -> None:
    f = _file_for(topic)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({"items": items}, ensure_ascii=False, indent=1), encoding="utf-8")


def identity(paper: Dict) -> str:
    """论文唯一键：优先 arxiv_id / doi，其次 url，最后标题。"""
    for k in ("arxiv_id", "doi"):
        v = (paper.get(k) or "").strip()
        if v:
            return f"{k}:{v.lower()}"
    if (paper.get("url") or "").strip():
        return f"url:{paper['url'].strip()}"
    return f"title:{(paper.get('title') or '').strip().lower()}"


def list_papers(topic: str) -> List[Dict]:
    items = _read(_file_for(topic))
    for p in items:
        p.pop("_key", None)  # 内部去重键不外泄
    return sorted(items, key=lambda p: p.get("added_at", ""), reverse=True)


def add_paper(topic: str, paper: Dict) -> Dict:
    if not (paper.get("title") or "").strip():
        raise HTTPException(status_code=400, detail="论文缺少标题")
    items = _read(_file_for(topic))
    key = identity(paper)
    if any(identity(p) == key for p in items):
        raise HTTPException(status_code=409, detail="该论文已在文献库中")
    item = {
        "id": uuid.uuid4().hex[:12],
        "topic": topic,
        "title": (paper.get("title") or "").strip(),
        "authors": [str(a).strip() for a in (paper.get("authors") or []) if str(a).strip()],
        "year": (paper.get("year") or "").strip(),
        "venue": (paper.get("venue") or "").strip(),
        "abstract": (paper.get("abstract") or "").strip(),
        "doi": (paper.get("doi") or "").strip(),
        "arxiv_id": (paper.get("arxiv_id") or "").strip(),
        "url": (paper.get("url") or "").strip(),
        "pdf": (paper.get("pdf") or "").strip(),
        "tags": [str(t).strip() for t in (paper.get("tags") or []) if str(t).strip()],
        "status": "unread",
        "comment": "",
        "added_at": _now(),
    }
    items.append(item)
    _write(topic, items)
    return item


def update_paper(topic: str, paper_id: str, patch: Dict) -> Dict:
    items = _read(_file_for(topic))
    for idx, p in enumerate(items):
        if p.get("id") != paper_id:
            continue
        if "status" in patch:
            if patch["status"] not in READ_STATUS:
                raise HTTPException(status_code=400, detail=f"非法读状态：{patch['status']}")
            p["status"] = patch["status"]
        if "tags" in patch:
            p["tags"] = [str(t).strip() for t in patch["tags"] if str(t).strip()]
        if "comment" in patch:
            p["comment"] = str(patch["comment"])
        moved = (patch.get("topic") or "").strip()
        if moved and moved != topic:
            items.pop(idx)
            p["topic"] = moved
            target = _read(_file_for(moved))
            target.append(p)
            _write(moved, target)
        _write(topic, items)
        p.pop("_key", None)
        return p
    raise HTTPException(status_code=404, detail="文献不存在")


def get_paper(topic: str, paper_id: str) -> Dict:
    items = _read(_file_for(topic))
    for p in items:
        if p.get("id") == paper_id:
            p.pop("_key", None)
            return p
    raise HTTPException(status_code=404, detail="文献不存在")


def attach_pdf(topic: str, paper_id: str, filename: str) -> Dict:
    """记录已下载的 PDF 附件（存文件名，读取时按 pdf 附件目录解析）。"""
    items = _read(_file_for(topic))
    for p in items:
        if p.get("id") != paper_id:
            continue
        p["pdf_path"] = filename
        p["pdf_downloaded_at"] = _now()
        _write(topic, items)
        p.pop("_key", None)
        return p
    raise HTTPException(status_code=404, detail="文献不存在")


def delete_paper(topic: str, paper_id: str) -> None:
    items = _read(_file_for(topic))
    rest = [p for p in items if p.get("id") != paper_id]
    if len(rest) == len(items):
        raise HTTPException(status_code=404, detail="文献不存在")
    _write(topic, rest)


def delete_topic_papers(topic: str) -> None:
    f = _file_for(topic)
    if f.exists():
        f.unlink()


def rename_topic_papers(old: str, new: str) -> None:
    old_f, new_f = _file_for(old), _file_for(new)
    if old_f.exists():
        items = _read(old_f)
        for p in items:
            p["topic"] = new
        _write(new, items)
        if old_f != new_f:
            old_f.unlink()

"""高亮标注存储：按笔记路径存放 sidecar JSON（data/annotations/<笔记路径>.json）。

不改动 md 正文，阅读器渲染时按 quote/prefix/suffix/occurrence 锚定到文本。
"""
import datetime
import json
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import HTTPException

from ..config import get_annotations_dir, get_vault_dir
from ..utils import resolve_in, safe_rel_parts
from .settings_store import load_settings

VALID_STYLES = ("background", "font")


def _file_for(note_rel: str) -> Path:
    parts = safe_rel_parts(note_rel)
    name = str(parts).replace("/", "__") + ".json"
    return get_annotations_dir() / name


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


def _write(f: Path, items: List[Dict]) -> None:
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"items": items}, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(f)


def list_annotations(note_rel: str) -> List[Dict]:
    return _read(_file_for(note_rel))


def get_annotation(note_rel: str, ann_id: str) -> Dict:
    for item in _read(_file_for(note_rel)):
        if item["id"] == ann_id:
            return item
    raise HTTPException(status_code=404, detail=f"标注不存在：{ann_id}")


def add_annotation(
    note_rel: str,
    quote: str,
    prefix: str = "",
    suffix: str = "",
    occurrence: int = 1,
    color: Optional[str] = None,
    style: Optional[str] = None,
    comment: str = "",
) -> Dict:
    if not quote.strip():
        raise HTTPException(status_code=400, detail="高亮内容（quote）不能为空")
    hl = load_settings().get("highlight", {})
    item = {
        "id": uuid.uuid4().hex[:12],
        "quote": quote,
        "prefix": prefix or "",
        "suffix": suffix or "",
        "occurrence": max(1, int(occurrence or 1)),
        "color": color or hl.get("color", "#fef08a"),
        "style": style or hl.get("style", "background"),
        "comment": comment or "",
        "created_at": _now(),
        "updated_at": _now(),
    }
    if item["style"] not in VALID_STYLES:
        raise HTTPException(status_code=400, detail=f"style 仅支持 {' / '.join(VALID_STYLES)}")
    f = _file_for(note_rel)
    items = _read(f)
    items.append(item)
    _write(f, items)
    return item


def update_annotation(note_rel: str, ann_id: str, updates: Dict) -> Dict:
    f = _file_for(note_rel)
    items = _read(f)
    for item in items:
        if item["id"] == ann_id:
            if "style" in updates and updates["style"] is not None:
                if updates["style"] not in VALID_STYLES:
                    raise HTTPException(status_code=400, detail="style 仅支持 background / font")
                item["style"] = updates["style"]
            for k in ("color", "comment", "occurrence"):
                if updates.get(k) is not None:
                    item[k] = updates[k]
            item["updated_at"] = _now()
            _write(f, items)
            return item
    raise HTTPException(status_code=404, detail=f"标注不存在：{ann_id}")


def delete_annotation(note_rel: str, ann_id: str) -> None:
    f = _file_for(note_rel)
    items = _read(f)
    remaining = [i for i in items if i["id"] != ann_id]
    if len(remaining) == len(items):
        raise HTTPException(status_code=404, detail=f"标注不存在：{ann_id}")
    _write(f, remaining)


def note_exists(note_rel: str) -> bool:
    try:
        path = resolve_in(get_vault_dir(), note_rel)
    except HTTPException:
        return False
    return path.exists()

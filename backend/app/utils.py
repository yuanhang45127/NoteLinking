"""通用工具：路径安全、文件名清洗。"""
import re
from pathlib import Path

from fastapi import HTTPException

_INVALID_FS = re.compile(r'[\\/:*?"<>|\x00-\x1f]')


def sanitize_filename(name: str, fallback: str = "untitled") -> str:
    """清洗为安全文件名（不含扩展名）。"""
    name = (name or "").strip()
    name = _INVALID_FS.sub("_", name).strip(". ")
    name = name[:100].strip()
    return name or fallback


def safe_rel_parts(rel: str) -> Path:
    """把相对路径清洗为库内相对 Path，拒绝越权（..、绝对路径、空段）。"""
    rel = (rel or "").strip().replace("\\", "/").lstrip("/")
    parts = [seg for seg in rel.split("/") if seg not in ("", ".")]
    if not parts:
        raise HTTPException(status_code=400, detail="路径不能为空")
    for seg in parts:
        if seg == "..":
            raise HTTPException(status_code=400, detail="路径不允许包含 ..")
    return Path(*parts)


def resolve_in(root: Path, rel: str) -> Path:
    """解析库内相对路径为绝对路径，并确保不越出 root。"""
    root = root.resolve()
    full = (root / safe_rel_parts(rel)).resolve()
    if full != root and root not in full.parents:
        raise HTTPException(status_code=400, detail="路径越出笔记库范围")
    return full


def unique_path(path: Path) -> Path:
    """若文件已存在，追加 -2、-3… 直到可用。"""
    if not path.exists():
        return path
    stem, suffix = path.stem, path.suffix
    i = 2
    while True:
        cand = path.with_name(f"{stem}-{i}{suffix}")
        if not cand.exists():
            return cand
        i += 1

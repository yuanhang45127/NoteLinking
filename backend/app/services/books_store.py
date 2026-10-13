"""书籍存储：books/<book_id>.json 存章节全文与渲染 HTML，books/<book_id>.<fmt> 存原书文件。

与 papers 库的关系：papers 条目带 kind:"book" + book_id 指向这里，
书目状态（在读/读完）复用 papers 的 status。
"""
import datetime
import json
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import HTTPException

from ..config import get_user_data_dir

FMT_MIME = {"pdf": "application/pdf", "epub": "application/epub+zip"}


def _books_dir() -> Path:
    d = get_user_data_dir() / "books"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _book_file(book_id: str) -> Path:
    return _books_dir() / f"{Path(book_id).name}.json"


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def create_book(title: str, chapters: List[Dict], meta: Optional[Dict], topic: str = "",
                author: str = "", fmt: str = "", file_bytes: bytes = b"") -> Dict:
    # 章节只保留三种字段（解析过程中的私有键不落盘）
    clean = [{"title": c.get("title") or "", "text": c.get("text") or "", "html": c.get("html") or ""}
             for c in chapters]
    book: Dict = {
        "id": datetime.datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:6],
        "title": (title or "").strip() or "未命名书籍",
        "author": (author or "").strip(),
        "topic": topic,
        "fmt": fmt,
        "created_at": _now(),
        "meta": meta or {},
        "chapters": clean,
    }
    if file_bytes:
        name = f"{book['id']}.{fmt or 'bin'}"
        (_books_dir() / name).write_bytes(file_bytes)
        book["file"] = name
    f = _book_file(book["id"])
    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(book, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(f)
    return book


def get_book(book_id: str) -> Dict:
    f = _book_file(book_id)
    if not f.exists():
        raise HTTPException(status_code=404, detail=f"书籍不存在：{book_id}")
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError) as exc:
        raise HTTPException(status_code=500, detail=f"书籍数据损坏：{exc}") from exc


def chapter_texts(book: Dict) -> List[Dict]:
    """梗概生成用：[{title, text}]，过滤空章节。"""
    return [{"title": c.get("title") or "", "text": c.get("text") or ""}
            for c in book.get("chapters", []) if (c.get("text") or "").strip()]


def book_file_path(book: Dict) -> Optional[Path]:
    name = book.get("file") or ""
    if not name:
        return None
    p = _books_dir() / Path(name).name
    return p if p.exists() else None

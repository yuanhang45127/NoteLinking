"""读书笔记路由：书籍导入（PDF/EPUB）、章节梗概批量生成（SSE 进度流）。

事件协议（沿用 topic-architecture 约定）：
    {"type": "start", "total": N}
    {"type": "chapter_start"|"chapter_done"|"chapter_error", "index", "title", ...}
    {"type": "done", "path", "chapters", "failed"}
"""
import datetime
import re

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from ..markdown_utils import ensure_frontmatter
from ..schemas import BookNotesRequest
from ..services import book_parser, books_store, papers_store, vault
from ..services.books_store import FMT_MIME
from ..services.process import llm_call
from ..utils import sanitize_filename
from .llm import sse_response

router = APIRouter(prefix="/api/books", tags=["books"])

MAX_BOOK_SIZE = 100 * 1024 * 1024  # 整本书比论文大，放宽到 100MB

SUMMARY_USER = """下面是《{book}》中「{title}」一章的内容（可能截断）：

{text}

请写一段 200-400 字的中文内容梗概：
- 概括本章核心观点与关键要点，可分 2-4 个要点；
- 忠于原文，不要编造章节里没有的内容；
- 只输出梗概本身（Markdown 列表或段落），不要加标题和客套话。"""


def _note_rel(topic: str, title: str) -> str:
    safe = sanitize_filename(f"《{title}》读书笔记", "读书笔记")
    return f"{topic}/读书笔记/{safe}.md"


@router.post("/import")
async def import_book(file: UploadFile = File(...), topic: str = Form(...),
                      title: str = Form(""), author: str = Form("")):
    """上传 PDF/EPUB：解析章节 → 存书籍 JSON → 建 papers 书目条目（kind: book）。"""
    data = await file.read()
    if len(data) > 100 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="文件超过 100MB 上限")
    if not data:
        raise HTTPException(status_code=400, detail="空文件")
    parsed = book_parser.parse_book(data, file.filename or "")

    raw_title = (title or "").strip() \
        or re.sub(r"\.(pdf|epub)$", "", file.filename or "", flags=re.I).strip() \
        or "未命名书籍"
    book_title = sanitize_filename(raw_title, "未命名书籍")
    book_author = (author or "").strip() or parsed["meta"].get("author", "")
    book = books_store.create_book(book_title, parsed["chapters"], parsed["meta"],
                                   topic=topic, author=book_author,
                                   fmt=parsed["fmt"], file_bytes=data)

    paper = None
    try:
        paper = papers_store.add_paper(topic, {
            "kind": "book",
            "title": f"《{book['title']}》",
            "authors": [book["author"]] if book["author"] else [],
            "book_id": book["id"],
            "abstract": f"书籍 · {len(book['chapters'])} 章 · 来源 {file.filename}",
            "status": "reading",
        })
    except HTTPException:
        pass  # 同名书目已存在不阻塞导入，笔记生成不受影响

    return {
        "book": {k: book[k] for k in ("id", "title", "author", "topic", "created_at", "meta")},
        "chapters": [{"title": c["title"], "chars": len(c.get("text") or "")} for c in book["chapters"]],
        "paper": paper,
    }


@router.get("/{book_id}")
def get_book(book_id: str):
    book = books_store.get_book(book_id)
    return {
        "book": {k: book[k] for k in ("id", "title", "author", "topic", "created_at", "meta") if k in book},
        "fmt": book.get("fmt", "epub"),
        "chapters": [{"title": c["title"], "chars": len(c.get("text") or "")} for c in book["chapters"]],
    }


@router.get("/{book_id}/chapter/{index}/html")
def get_book_chapter(book_id: str, index: int):
    """原书对照分栏：某章的净化 HTML（iframe srcDoc 渲染，脚本已剥离）。"""
    book = books_store.get_book(book_id)
    chapters = book.get("chapters", [])
    if index < 0 or index >= len(chapters):
        raise HTTPException(status_code=404, detail="章节不存在")
    c = chapters[index]
    return {"title": c.get("title") or "", "html": c.get("html") or ""}


@router.get("/{book_id}/file")
def get_book_file(book_id: str):
    """原书文件（PDF 书的分栏直读；EPUB 供下载）。"""
    book = books_store.get_book(book_id)
    path = books_store.book_file_path(book)
    if not path:
        raise HTTPException(status_code=404, detail="原书文件不存在")
    media = FMT_MIME.get(book.get("fmt", ""), "application/octet-stream")
    return FileResponse(path, media_type=media, filename=f"{book['title']}.{book.get('fmt', 'bin')}")


@router.post("/{book_id}/notes/stream")
async def book_notes_stream(book_id: str, body: BookNotesRequest):
    """按章批量生成梗概并落盘《书名》读书笔记.md（SSE 进度流）。"""
    book = books_store.get_book(book_id)
    chapters = books_store.chapter_texts(book)
    if not chapters:
        raise HTTPException(status_code=400, detail="该书没有可用的章节文本")
    rel = _note_rel(book["topic"] or "读书笔记", book["title"])
    try:
        vault.read_note(rel)
        raise HTTPException(status_code=409, detail=f"读书笔记已存在：{rel}")
    except HTTPException as e:
        if e.status_code != 404:
            raise

    provider, model = body.provider or "", body.model or ""
    topic = book["topic"] or "读书笔记"

    async def gen():
        total = len(chapters)
        yield {"type": "start", "total": total, "title": book["title"]}
        summaries, failed = [], 0
        for i, ch in enumerate(chapters):
            yield {"type": "chapter_start", "index": i, "total": total, "title": ch["title"]}
            try:
                messages = [
                    {"role": "system", "content": "你是专业的读书助理，输出简明、忠实原文的中文内容梗概。"},
                    {"role": "user", "content": SUMMARY_USER.format(
                        book=book["title"], title=ch["title"], text=ch["text"][:8000])},
                ]
                text = ""
                async for ev in llm_call(provider, messages, model,
                                         purpose=f"梗概 {i + 1}/{total} · {ch['title']}"):
                    if ev["type"] == "delta":
                        text += ev["text"]
                    yield ev
                if not text.strip():
                    raise ValueError("模型返回空内容")
                summaries.append({"title": ch["title"], "summary": text.strip()})
                yield {"type": "chapter_done", "index": i, "title": ch["title"], "chars": len(text)}
            except Exception as e:  # noqa: BLE001 单章失败不中断整批
                failed += 1
                summaries.append({"title": ch["title"], "summary": ""})
                yield {"type": "chapter_error", "index": i, "title": ch["title"], "message": str(e)}

        today = datetime.date.today().isoformat()
        parts = [f"# 《{book['title']}》读书笔记\n\n"
                 f"> 作者：{book['author'] or '未知'} · 共 {total} 章 · 梗概生成于 {today}\n"
                 f"> 每章的「🤖 梗概」由 AI 生成，梗概下方留给你写自己的读书笔记。"]
        for i, s in enumerate(summaries):
            summary = s["summary"] or "（本章梗概生成失败，可重新生成）"
            parts.append(f"## {i + 1}. {s['title']}\n\n"
                         f"> 🤖 **梗概**\n>\n" +
                         "\n".join(f"> {line}" for line in summary.split("\n")) +
                         "\n\n（在这里写你的读书笔记）\n")
        md = ensure_frontmatter("\n\n".join(parts) + "\n", {
            "title": f"《{book['title']}》读书笔记",
            "book_id": book["id"],
            "book_fmt": book.get("fmt", "epub"),
            "author": book["author"],
            "kind": "reading-notes",
        })
        try:
            saved = vault.create_note(rel, md, overwrite=False)
        except HTTPException as e:
            yield {"type": "error", "message": e.detail}
            return
        yield {"type": "done", "path": saved["path"], "chapters": total, "failed": failed}

    return sse_response(gen())

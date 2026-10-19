"""读书笔记：EPUB 解析、PDF 无文本报错、梗概流事件与落盘、papers kind 字段。"""
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import books_store, papers_store


@pytest.fixture()
def client(data_dir):
    with TestClient(app) as c:
        yield c


def _make_epub() -> bytes:
    """用 ebooklib 现场构造一本 3 章小书（含目录与作者）。"""
    from ebooklib import epub

    book = epub.EpubBook()
    book.set_identifier("test-book-1")
    book.set_title("测试之书")
    book.add_author("测试作者")
    chapters = []
    for i in range(1, 4):
        c = epub.EpubHtml(title=f"第{i}章 测试", file_name=f"ch{i}.xhtml", lang="zh")
        c.content = f"<html><body><h1>第{i}章 测试</h1><p>{'内容' * 150}</p></body></html>"
        book.add_item(c)
        chapters.append(c)
    book.toc = chapters
    book.add_item(epub.EpubNcx())
    book.add_item(epub.EpubNav())
    import io
    buf = io.BytesIO()
    epub.write_epub(buf, book)
    return buf.getvalue()


def test_parse_epub(data_dir):
    from app.services import book_parser

    out = book_parser.parse_book(_make_epub(), "测试之书.epub")
    assert out["meta"]["author"] == "测试作者"
    assert len(out["chapters"]) == 3
    titles = [c["title"] for c in out["chapters"]]
    assert any("第1章" in t for t in titles)
    assert all(len(c["text"]) > 100 for c in out["chapters"])


def test_parse_pdf_without_text_raises(data_dir):
    """无文本层的空白 PDF（即使有书签）应明确报错而非产出空章节。"""
    import io

    from pypdf import PdfReader, PdfWriter

    writer = PdfWriter()
    for _ in range(3):
        writer.add_blank_page(width=595, height=842)
    parent = writer.add_outline_item("第一章", 0)
    writer.add_outline_item("第二节", 1, parent=parent)
    buf = io.BytesIO()
    writer.write(buf)

    from app.services import book_parser
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as e:
        book_parser.parse_book(buf.getvalue(), "空白书.pdf")
    assert "未提取到文本" in e.value.detail


def test_import_and_notes_stream(client, data_dir, monkeypatch):
    client.post("/api/topics", json={"name": "书架"})

    # 1) 导入 EPUB → books JSON + papers 书目（kind: book, book_id, status: reading）
    epub_bytes = _make_epub()
    r = client.post("/api/books/import",
                    files={"file": ("测试之书.epub", epub_bytes, "application/epub+zip")},
                    data={"topic": "书架", "title": "测试之书", "author": "测试作者"})
    assert r.status_code == 200
    body = r.json()
    assert body["book"]["title"] == "测试之书"
    assert len(body["chapters"]) == 3
    papers = client.get("/api/papers", params={"topic": "书架"}).json()["papers"]
    book_entry = next(p for p in papers if p.get("kind") == "book")
    assert book_entry["book_id"] == body["book"]["id"]
    assert book_entry["status"] == "reading"

    # 2) 梗概流：mock llm_call 产出固定梗概（事件协议：llm_start → delta* → llm_done）
    async def fake_llm_call(provider, messages, model="", temperature=None, purpose="", seq=1):
        yield {"type": "llm_start", "seq": seq, "purpose": purpose, "provider": "", "model": "", "prompt_chars": 0}
        yield {"type": "delta", "text": "- 要点一\n- 要点二"}
        yield {"type": "llm_done", "seq": seq, "chars": 12, "elapsed": 0.0}

    monkeypatch.setattr("app.routers.books.llm_call", fake_llm_call)

    with client as c:
        r = c.post(f"/api/books/{body['book']['id']}/notes/stream", json={})
    assert r.status_code == 200
    events = [json.loads(line[5:]) for line in r.text.split("\n") if line.startswith("data:")]
    types = [e["type"] for e in events]
    assert types[0] == "start" and types[-1] == "done"
    assert types.count("chapter_done") == 3 and "chapter_error" not in types
    done_evt = events[-1]
    assert done_evt["failed"] == 0 and done_evt["chapters"] == 3

    # 3) 落盘的读书笔记结构：frontmatter + 每章梗概引用块 + 留白
    note = client.get("/api/notes", params={"path": done_evt["path"]}).json()
    assert note["frontmatter"].get("book_id") == body["book"]["id"]
    assert note["frontmatter"].get("kind") == "reading-notes"
    for kw in ("🤖 **梗概**", "（在这里写你的读书笔记）", "## 1. ", "## 3. "):
        assert kw in note["content"]

    # 4) 重复生成 → 409
    r = client.post(f"/api/books/{body['book']['id']}/notes/stream", json={})
    assert r.status_code == 409


def test_papers_kind_and_status_fields(data_dir):
    p = papers_store.add_paper("书架", {
        "kind": "book", "title": "书A", "book_id": "b123", "status": "reading",
    })
    assert p["kind"] == "book" and p["book_id"] == "b123" and p["status"] == "reading"
    p2 = papers_store.add_paper("书架", {"title": "论文B"})
    assert p2["kind"] == "paper" and p2["status"] == "unread"

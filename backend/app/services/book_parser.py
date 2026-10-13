"""书籍解析：EPUB / PDF → 章节列表 [{title, text, html}]。

EPUB 用 ebooklib 读 spine + TOC（标题优先取目录，回退文档首个标题）；
PDF 优先读 outline 书签取顶层章节（title + 起止页，逐页提取文本），
无书签的书降级为整本单章（chunked=false 提示前端）。

每章同时给两种形态：
- text：纯文本（AI 梗概 / 检索用），截断到 MAX_CHAPTER_CHARS；
- html：净化后的轻量 HTML（原书对照分栏渲染用），脚本/样式/图片剔除。
"""
import io
import re
from typing import Dict, List

from fastapi import HTTPException

MAX_CHAPTER_CHARS = 12000
# 短于该长度的文档视为封面/空页；EPUB 导航页（nav/ncx）显式跳过
MIN_CHAPTER_CHARS = 50


def _clean(text: str) -> str:
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def _html_to_text(raw: bytes) -> str:
    from bs4 import BeautifulSoup
    return _clean(BeautifulSoup(raw, "html.parser").get_text("\n"))


def _sanitize_html(raw: bytes) -> str:
    """净化章节 HTML：去 script/style/iframe/img（图片在包内，iframe 里无法解析），保留正文标签。"""
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(raw, "html.parser")
    for tag in soup(["script", "style", "link", "iframe", "img", "object", "embed"]):
        tag.decompose()
    body = soup.body or soup
    html = body.decode_contents() if body.name == "body" else str(body)
    return re.sub(r"\n{3,}", "\n\n", html).strip()


def _first_heading(text: str) -> str:
    for line in text.split("\n"):
        line = line.strip()
        if line:
            return line[:60]
    return ""


def parse_epub(data: bytes) -> Dict:
    """EPUB → {chapters: [{title, text, html}], meta: {author}}。"""
    try:
        from ebooklib import epub
    except ImportError as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail="服务端缺少 ebooklib，请安装依赖") from exc

    try:
        book = epub.read_epub(io.BytesIO(data))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"无法解析 EPUB：{exc}") from exc

    # 导航文档（nav.xhtml）整份就是目录，显式跳过
    nav_names = {it.get_name() for it in book.get_items_of_type(getattr(epub, "ITEM_NAVIGATION", 0))}

    # TOC 标题表：spine 文档 href → 目录里第一个匹配的标题
    toc_titles: Dict[str, str] = {}

    def _walk_toc(items):
        for it in items:
            if isinstance(it, (list, tuple)):
                _walk_toc(it[1:] if isinstance(it, tuple) else it)
                continue
            href = (getattr(it, "href", "") or "").split("#")[0]
            title = (getattr(it, "title", "") or "").strip()
            if href and title:
                toc_titles.setdefault(href.split("/")[-1], title)
                toc_titles.setdefault(href, title)

    try:
        _walk_toc(book.toc)
    except Exception:
        pass

    chapters: List[Dict] = []
    for item in book.get_items_of_type(9):  # ITEM_DOCUMENT
        name = item.get_name() or ""
        if name in nav_names or name.rsplit("/", 1)[-1] in {"nav.xhtml", "toc.xhtml"}:
            continue
        raw = item.get_content()
        if not raw:
            continue
        text = _html_to_text(raw)
        html = _sanitize_html(raw)
        if len(text) < MIN_CHAPTER_CHARS or not html:
            continue  # 封面/空页
        href_key = name.split("/")[-1]
        title = toc_titles.get(href_key) or toc_titles.get(name) or _first_heading(text)
        chapters.append({"title": title or f"第 {len(chapters) + 1} 节", "text": text, "html": html})

    if not chapters:
        raise HTTPException(status_code=400, detail="EPUB 未解析出正文内容（可能是扫描版或纯图片）")

    author = ""
    try:
        author = (book.get_metadata("DC", "creator") or [(" ", "")])[0][0] or ""
    except Exception:
        pass
    return {"chapters": chapters[:200], "meta": {"author": str(author).strip(), "chunked": True}}


def parse_pdf(data: bytes) -> Dict:
    """PDF → {chapters, meta}。优先 outline 书签切章，无书签降级整本单章。"""
    try:
        from pypdf import PdfReader
    except ImportError as exc:  # pragma: no cover
        raise HTTPException(status_code=500, detail="服务端缺少 pypdf，请安装依赖") from exc

    try:
        reader = PdfReader(io.BytesIO(data))
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"无法解析 PDF：{exc}") from exc
    if getattr(reader, "is_encrypted", False):
        try:
            reader.decrypt("")
        except Exception:
            raise HTTPException(status_code=400, detail="PDF 已加密，无法导入")

    total = len(reader.pages)

    def _page_text(idx: int) -> str:
        try:
            return _clean(reader.pages[idx].extract_text() or "")
        except Exception:
            return ""

    # 书签 → 顶层章节（title, 起始页）。子书签并入所属顶层章。
    marks: List[Dict] = []
    try:
        for outline in reader.outline:
            if isinstance(outline, list):
                continue  # 子级并入顶层章，不单独切
            title = str(getattr(outline, "title", "") or "").strip()
            try:
                page_idx = reader.get_destination_page_number(outline)
            except Exception:
                continue
            if title and 0 <= page_idx < total:
                marks.append({"title": title[:80], "page": page_idx})
    except Exception:
        marks = []

    deduped: List[Dict] = []
    for m in marks:
        if deduped and deduped[-1]["page"] == m["page"] and deduped[-1]["title"] == m["title"]:
            continue
        deduped.append(m)

    chapters: List[Dict] = []
    if len(deduped) >= 2:
        for i, m in enumerate(deduped):
            start = m["page"]
            end = deduped[i + 1]["page"] - 1 if i + 1 < len(deduped) else total - 1
            if end < start:
                end = start
            pages = [(_page_text(p), p + 1) for p in range(start, end + 1)]
            text = _clean("\n\n".join(t for t, _ in pages))
            if text:
                chapters.append({"title": m["title"], "text": text,
                                 "html": _pages_to_html(pages), "_pages": (start + 1, end + 1)})
        meta = {"chunked": True}
    else:
        pages = [(_page_text(p), p + 1) for p in range(total)]
        text = _clean("\n\n".join(t for t, _ in pages))
        chapters = [{"title": "全书", "text": text, "html": _pages_to_html(pages)}]
        meta = {"chunked": False, "hint": "该 PDF 没有书签目录，已按整本生成一个章节；建议手动分章后再生成梗概"}

    if not any(c["text"] for c in chapters):
        raise HTTPException(status_code=400, detail="PDF 未提取到文本（可能是扫描版，需要 OCR，暂不支持）")
    return {"chapters": chapters, "meta": {**meta, "pages": total}}


def _pages_to_html(pages: List) -> str:
    """页文本 → 轻量 HTML：每页一个小节标题，空行分段。"""
    blocks = []
    for text, page_no in pages:
        paras = "".join(f"<p>{_esc(p)}</p>" for p in re.split(r"\n{2,}", text) if p.strip())
        if paras:
            blocks.append(f'<section class="pg"><div class="pg-no">第 {page_no} 页</div>{paras}</section>')
    return "\n".join(blocks)


def _esc(s: str) -> str:
    return (s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def parse_book(data: bytes, filename: str) -> Dict:
    """按扩展名分发；返回 {chapters, meta, fmt}。text 截断，html 保留（渲染用）。"""
    lower = (filename or "").lower()
    if lower.endswith(".epub"):
        out = parse_epub(data)
        fmt = "epub"
    elif lower.endswith(".pdf"):
        out = parse_pdf(data)
        fmt = "pdf"
    else:
        raise HTTPException(status_code=400, detail="仅支持 .pdf / .epub 格式")
    for c in out["chapters"]:
        if len(c["text"]) > MAX_CHAPTER_CHARS:
            c["text"] = c["text"][:MAX_CHAPTER_CHARS] + "\n…（超长章节已截断，梗概基于开头部分生成）"
    return {**out, "fmt": fmt}

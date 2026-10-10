"""PDF 导入：提取文本并转为基础 Markdown 笔记（基础实现，优先级低）。

pypdf 纯 Python 提取，适合文字型 PDF；扫描件需 OCR，暂不支持。
"""
import io
import re
from typing import Tuple

from fastapi import HTTPException

from . import vault
from ..markdown_utils import ensure_frontmatter


def extract_markdown(data: bytes, title: str) -> Tuple[str, int]:
    """返回 (markdown 文本, 页数)。"""
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

    pages_md = []
    for i, page in enumerate(reader.pages, 1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        pages_md.append(f"<!-- 第 {i} 页 -->\n\n{text}" if text else f"<!-- 第 {i} 页（无可提取文本，可能是扫描图） -->\n")

    md_body = "\n\n---\n\n".join(pages_md)
    front = {"title": title, "source": "pdf-import", "pages": len(reader.pages), "imported": True}
    md = ensure_frontmatter(f"# {title}\n", front) + md_body + "\n"
    return md, len(reader.pages)


async def import_pdf(data: bytes, filename: str, topic: str, name: str = "") -> dict:
    title = (name or "").strip() or re.sub(r"\.pdf$", "", filename or "导入的 PDF", flags=re.I).strip() or "导入的 PDF"
    md, pages = extract_markdown(data, title)
    rel = f"{topic}/{title}.md"
    note = vault.create_note(rel, md, overwrite=False)
    text_chars = len(md)
    return {**note, "pages": pages, "text_chars": text_chars}

"""文献库路由：arXiv 检索收录、增删改查（状态 / 标签 / 想法 / 移动主题）、
Zotero Web API 同步、arXiv PDF 附件下载与全文导入。"""
import re
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ..services import papers_store, zotero_service

router = APIRouter(prefix="/api/papers", tags=["papers"])

ARXIV_API = "http://export.arxiv.org/api/query"
_NS = {"a": "http://www.w3.org/2005/Atom"}


class PaperIn(BaseModel):
    title: str
    authors: List[str] = []
    year: str = ""
    venue: str = ""
    abstract: str = ""
    doi: str = ""
    arxiv_id: str = ""
    url: str = ""
    pdf: str = ""
    tags: List[str] = []


class PaperPatch(BaseModel):
    status: Optional[str] = None
    tags: Optional[List[str]] = None
    comment: Optional[str] = None
    topic: Optional[str] = None


# ---------------------------------------------------------------- Zotero 同步
class ZoteroConfigIn(BaseModel):
    user_id: str = ""
    api_key: str = ""
    collection: str = ""
    collection_name: str = ""
    base_url: str = ""
    download_pdf: Optional[bool] = None


class ZoteroSyncIn(BaseModel):
    topic: str = ""
    collection: str = ""
    download_pdf: Optional[bool] = None


@router.get("/zotero/config")
def zotero_get_config():
    return zotero_service.masked_config()


@router.put("/zotero/config")
def zotero_put_config(body: ZoteroConfigIn):
    updates = body.model_dump(exclude_none=True)
    return zotero_service.save_config(updates)


@router.get("/zotero/status")
def zotero_status():
    """校验凭据连通性，返回 collections 供前端选择。"""
    cfg = zotero_service.get_config()
    return {"ok": True, "collections": zotero_service.fetch_collections(cfg), "config": zotero_service.masked_config()}


@router.post("/zotero/sync")
def zotero_sync(body: ZoteroSyncIn):
    """增量拉取 Zotero 条目写入指定主题文献库（去重跳过，可选下载 arXiv PDF）。"""
    return zotero_service.sync(body.topic, body.collection, body.download_pdf)


@router.get("")
def list_papers(topic: str = Query(...)):
    return {"papers": papers_store.list_papers(topic)}


@router.post("")
def add_paper(topic: str = Query(...), body: PaperIn = None):
    return papers_store.add_paper(topic, body.model_dump())


@router.put("/{paper_id}")
def update_paper(topic: str = Query(...), paper_id: str = "", body: PaperPatch = None):
    return papers_store.update_paper(topic, paper_id, body.model_dump(exclude_none=True))


@router.delete("/{paper_id}")
def delete_paper(topic: str = Query(...), paper_id: str = ""):
    papers_store.delete_paper(topic, paper_id)
    return {"ok": True}


# ---------------------------------------------------------------- PDF 附件
@router.post("/{paper_id}/fetch-pdf")
def fetch_pdf(topic: str = Query(...), paper_id: str = ""):
    """按 arxiv_id 从 arxiv.org 下载 PDF 到附件目录（已存在则直接复用）。"""
    p = papers_store.get_paper(topic, paper_id)
    if not (p.get("arxiv_id") or "").strip():
        raise HTTPException(status_code=400, detail="该文献没有 arXiv ID，无法自动下载 PDF")
    try:
        filename = zotero_service.download_arxiv_pdf(p["arxiv_id"].strip())
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"PDF 下载失败：{e}")
    papers_store.attach_pdf(topic, paper_id, filename)
    return {"pdf_path": filename, "url": fetch_pdf_url(paper_id, topic)}


def fetch_pdf_url(paper_id: str, topic: str) -> str:
    return f"/api/papers/{urllib.parse.quote(paper_id)}/pdf?topic={urllib.parse.quote(topic)}"


@router.get("/{paper_id}/pdf")
def paper_pdf(topic: str = Query(...), paper_id: str = ""):
    """返回已下载的 PDF 附件文件流。"""
    p = papers_store.get_paper(topic, paper_id)
    name = p.get("pdf_path") or (zotero_service.pdf_filename(p["arxiv_id"]) if p.get("arxiv_id") else "")
    f = zotero_service.pdf_dir() / name if name else None
    if not f or not f.exists():
        raise HTTPException(status_code=404, detail="PDF 尚未下载")
    return FileResponse(f, media_type="application/pdf", filename=f.name)


@router.post("/{paper_id}/import-text")
async def import_paper_text(topic: str = Query(...), paper_id: str = ""):
    """把已下载的论文 PDF 导入为全文笔记（复用 PDF 导入管线，存到主题「文献」目录）。"""
    from .. import utils
    from ..services import pdf_service, vault

    p = papers_store.get_paper(topic, paper_id)
    name = p.get("pdf_path") or (zotero_service.pdf_filename(p["arxiv_id"]) if p.get("arxiv_id") else "")
    f = zotero_service.pdf_dir() / name if name else None
    if not f or not f.exists():
        raise HTTPException(status_code=404, detail="PDF 尚未下载，请先下载 PDF")
    safe = re.sub(r"[\\/:*?\"<>|]", " ", p["title"]).strip()[:60] or "文献全文"
    title = utils.sanitize_filename(f"全文 · {safe}", "文献全文")
    md, pages = pdf_service.extract_markdown(f.read_bytes(), title)
    note = vault.create_note(f"{topic}/文献/{title}.md", md, overwrite=False)
    return {**note, "pages": pages}


@router.get("/search-arxiv")
def search_arxiv(q: str = Query(..., min_length=2), max_results: int = Query(15, ge=1, le=40)):
    """arXiv 检索（按提交时间倒序）。多词默认 AND；中文不支持，请用英文关键词。"""
    terms = [w for w in re.split(r"\s+", q.strip()) if w]
    query = "+AND+".join(f"all:{urllib.parse.quote(t)}" for t in terms)
    url = f"{ARXIV_API}?search_query={query}&sortBy=submittedDate&sortOrder=descending&max_results={max_results}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "NoteLink/1.0 (papers library)"})
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = resp.read()
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"arXiv 检索失败：{e}")

    def clean(s) -> str:
        return re.sub(r"\s+", " ", s or "").strip()

    root = ET.fromstring(data)
    results = []
    for entry in root.findall("a:entry", _NS):
        abs_url = clean(entry.findtext("a:id", "", _NS))
        arxiv_id = abs_url.rsplit("/abs/", 1)[-1]
        pdf = ""
        for link in entry.findall("a:link", _NS):
            if link.get("title") == "pdf":
                pdf = link.get("href", "")
        published = clean(entry.findtext("a:published", "", _NS))
        results.append({
            "title": clean(entry.findtext("a:title", "", _NS)),
            "authors": [clean(a.findtext("a:name", "", _NS)) for a in entry.findall("a:author", _NS)],
            "year": published[:4],
            "venue": "arXiv",
            "abstract": clean(entry.findtext("a:summary", "", _NS)),
            "arxiv_id": arxiv_id,
            "url": abs_url,
            "pdf": pdf,
            "published": published[:10],
            "categories": [c.get("term", "") for c in entry.findall("a:category", _NS)][:4],
        })
    return {"results": results}

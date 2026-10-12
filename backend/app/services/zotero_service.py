"""Zotero Web API 同步：增量拉取个人库条目，映射写入 papers_store。

- 配置：settings.json 的 zotero 段（user_id / api_key / collection / base_url / download_pdf）；
  api_key 只落盘、回显打码（保存时空值或打码值沿用旧密钥）；
  base_url 可指向本地 mock 服务（测试用），默认 https://api.zotero.org。
- 增量协议：首次分页全量拉 top 条目；成功后把响应头 Last-Modified-Version 存进
  <papers>/_zotero_sync.json 的 last_version，之后带 since= 只拉变动条目。
- 去重：arxiv_id → doi → url → 标题（papers_store.identity），命中即跳过，不覆盖用户数据。
- PDF：有 arxiv_id 的条目可从 arxiv.org 下载到 <papers>/pdf/（不在 vault 内，不进笔记树）。
"""
import datetime
import json
import re
from typing import Dict, List, Optional

import httpx
from fastapi import HTTPException

from ..config import get_papers_dir
from ..utils import sanitize_filename
from . import papers_store, settings_store

DEFAULT_BASE = "https://api.zotero.org"
ARXIV_PDF_BASE = "https://arxiv.org/pdf"
MASK = "••••••"
_STATE_FILE = "_zotero_sync.json"
_ARXIV_ID = re.compile(r"arxiv[:\s/]*([0-9]{4}\.[0-9]{4,5})(?:v[0-9]+)?", re.I)


# ---------------------------------------------------------------- 配置
def get_config() -> Dict:
    s = settings_store.load_settings()
    cfg = s.get("zotero") if isinstance(s.get("zotero"), dict) else {}
    return {
        "user_id": str(cfg.get("user_id") or ""),
        "api_key": str(cfg.get("api_key") or ""),
        "collection": str(cfg.get("collection") or ""),
        "collection_name": str(cfg.get("collection_name") or ""),
        "base_url": str(cfg.get("base_url") or "").strip() or DEFAULT_BASE,
        "download_pdf": bool(cfg.get("download_pdf", True)),
    }


def masked_config() -> Dict:
    cfg = get_config()
    has_key = bool(cfg["api_key"])
    cfg["api_key"] = MASK if has_key else ""
    cfg["has_key"] = has_key
    return cfg


def save_config(updates: Dict) -> Dict:
    cur = get_config()
    key = (updates.get("api_key") or "").strip()
    if not key or key == MASK:
        updates["api_key"] = cur["api_key"]  # 留空/打码 = 沿用旧密钥
    for f in ("user_id", "collection", "collection_name", "base_url"):
        if f in updates:
            updates[f] = str(updates.get(f) or "").strip()
    if not updates.get("base_url"):
        updates["base_url"] = DEFAULT_BASE
    settings_store.update_settings("zotero", updates)
    return masked_config()


def _require_ready(cfg: Dict) -> None:
    if not cfg["user_id"] or not cfg["api_key"]:
        raise HTTPException(status_code=400, detail="请先配置 Zotero userID 与 API Key（zotero.org → Settings → Feeds/API）")


def _headers(cfg: Dict) -> Dict[str, str]:
    return {"Zotero-API-Key": cfg["api_key"], "Zotero-API-Version": "3"}


def _client() -> httpx.Client:
    return httpx.Client(timeout=30, follow_redirects=True, headers={"User-Agent": "NoteLink/1.0 (papers sync)"})


# ---------------------------------------------------------------- 同步游标
def _state_file():
    return get_papers_dir() / _STATE_FILE


def _load_state() -> Dict:
    f = _state_file()
    if not f.exists():
        return {}
    try:
        return json.loads(f.read_text(encoding="utf-8")) or {}
    except (json.JSONDecodeError, OSError):
        return {}


def _save_state(last_version: int) -> None:
    f = _state_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps({
        "last_version": last_version,
        "synced_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }, ensure_ascii=False, indent=1), encoding="utf-8")


# ---------------------------------------------------------------- Zotero API
def fetch_collections(cfg: Dict) -> List[Dict]:
    """校验凭据并返回 collections（同时充当连通性测试）。"""
    _require_ready(cfg)
    out: List[Dict] = []
    with _client() as client:
        start = 0
        while True:
            r = client.get(
                f"{cfg['base_url']}/users/{cfg['user_id']}/collections",
                params={"limit": 100, "start": start}, headers=_headers(cfg))
            if r.status_code == 403 or r.status_code == 401:
                raise HTTPException(status_code=400, detail="Zotero 凭据无效（检查 userID / API Key 权限）")
            if r.status_code == 404:
                raise HTTPException(status_code=400, detail=f"找不到该 userID 的库：{cfg['user_id']}")
            r.raise_for_status()
            batch = r.json()
            out += [{"key": c.get("key", ""), "name": (c.get("data") or {}).get("name", ""),
                     "num_items": (c.get("meta") or {}).get("numItems",
                                                            (c.get("data") or {}).get("numItems", 0))}
                    for c in batch]
            if len(batch) < 100:
                return out
            start += 100


def _fetch_items(cfg: Dict, collection: str) -> List[Dict]:
    """分页拉取条目（top 级，排除附件/笔记）；last_version 存在时增量拉取。"""
    base = f"{cfg['base_url']}/users/{cfg['user_id']}"
    if collection:
        base += f"/collections/{collection}"
    since = _load_state().get("last_version")
    items: List[Dict] = []
    last_version = None
    with _client() as client:
        start = 0
        while True:
            params: Dict = {"format": "json", "limit": 100, "start": start,
                            "itemType": "-attachment -note"}
            if since:
                params["since"] = since
            r = client.get(f"{base}/items/top", params=params, headers=_headers(cfg))
            if r.status_code in (401, 403):
                raise HTTPException(status_code=400, detail="Zotero 凭据无效（检查 userID / API Key 权限）")
            r.raise_for_status()
            batch = r.json()
            items += batch
            try:
                last_version = int(r.headers.get("Last-Modified-Version", "") or 0) or last_version
            except ValueError:
                pass
            if len(batch) < 100:
                break
            start += 100
    if last_version:
        _save_state(last_version)
    return items


# ---------------------------------------------------------------- 条目映射
def _creator_name(c: Dict) -> str:
    name = (c.get("name") or "").strip()
    if name:
        return name
    first, last = (c.get("firstName") or "").strip(), (c.get("lastName") or "").strip()
    if not (first or last):
        return ""
    if re.search(r"[\u4e00-\u9fff]", last + first):
        return f"{last}{first}"  # 中文名：姓在前不加空格
    return f"{first} {last}".strip()


def parse_arxiv_id(*texts: str) -> str:
    for t in texts:
        m = _ARXIV_ID.search(t or "")
        if m:
            return m.group(1)
    return ""


def map_item(item: Dict) -> Optional[Dict]:
    """Zotero item → PaperIn 字典；附件/笔记/无标题条目返回 None 跳过。"""
    data = item.get("data") or {}
    itype = (data.get("itemType") or "").strip()
    if itype in ("attachment", "note"):
        return None
    title = (data.get("title") or "").strip()
    if not title:
        return None
    doi = (data.get("DOI") or "").strip()
    doi = re.sub(r"^https?://(dx\.)?doi\.org/", "", doi, flags=re.I)
    url = (data.get("url") or "").strip()
    tags = [(t.get("tag") or "").strip() for t in (data.get("tags") or [])]
    tags = [t for t in tags if t]
    if itype:
        tags.append(itype)
    date = (data.get("date") or "").strip()
    arxiv_id = parse_arxiv_id(doi, url, data.get("archiveID") or "", data.get("extra") or "")
    if arxiv_id and re.match(r"^arxiv[:\s/]*", doi, re.I):
        doi = ""  # 预印本条目的 DOI 字段只是 arXiv 编号占位，不存为 DOI
    return {
        "title": title,
        "authors": [n for n in (_creator_name(c) for c in (data.get("creators") or [])) if n],
        "year": date[:4] if re.match(r"^\d{4}", date) else "",
        "venue": (data.get("publicationTitle") or data.get("proceedingsTitle") or "").strip(),
        "abstract": (data.get("abstractNote") or "").strip(),
        "doi": doi,
        "arxiv_id": arxiv_id,
        "url": url,
        "pdf": "",
        "tags": tags,
    }


# ---------------------------------------------------------------- PDF
def pdf_dir():
    d = get_papers_dir() / "pdf"
    d.mkdir(parents=True, exist_ok=True)
    return d


def pdf_filename(arxiv_id: str) -> str:
    return sanitize_filename(arxiv_id, "paper") + ".pdf"


def pdf_path_for(arxiv_id: str):
    return pdf_dir() / pdf_filename(arxiv_id)


def download_arxiv_pdf(arxiv_id: str) -> str:
    """从 arxiv.org 下载 PDF 到附件目录，返回文件名；失败抛 HTTPException。"""
    dest = pdf_path_for(arxiv_id)
    if dest.exists() and dest.stat().st_size > 1024:
        return dest.name
    with _client() as client:
        r = client.get(f"{ARXIV_PDF_BASE}/{arxiv_id}")
        r.raise_for_status()
        data = r.content
    if not data.startswith(b"%PDF") or len(data) < 1024:
        raise HTTPException(status_code=502, detail=f"arXiv 返回的不是有效 PDF：{arxiv_id}")
    dest.write_bytes(data)
    return dest.name


# ---------------------------------------------------------------- 同步主流程
def sync(topic: str, collection: str = "", download_pdf: Optional[bool] = None) -> Dict:
    """拉取 Zotero 条目写入指定主题的文献库；返回同步摘要。"""
    cfg = get_config()
    _require_ready(cfg)
    topic = (topic or "").strip()
    if not topic:
        raise HTTPException(status_code=400, detail="缺少目标主题")
    col = (collection or cfg["collection"]).strip()
    want_pdf = cfg["download_pdf"] if download_pdf is None else bool(download_pdf)

    fetched = added = skipped = pdf_new = pdf_failed = 0
    for item in _fetch_items(cfg, col):
        paper = map_item(item)
        if paper is None:
            continue
        fetched += 1
        try:
            rec = papers_store.add_paper(topic, paper)
        except HTTPException as e:
            if e.status_code == 409:
                skipped += 1
                continue
            raise
        added += 1
        if want_pdf and rec.get("arxiv_id"):
            try:
                rec_pdf = download_arxiv_pdf(rec["arxiv_id"])
                papers_store.attach_pdf(topic, rec["id"], rec_pdf)
                pdf_new += 1
            except (HTTPException, httpx.HTTPError):
                pdf_failed += 1
    return {
        "topic": topic, "fetched": fetched, "added": added, "skipped": skipped,
        "pdf_downloaded": pdf_new, "pdf_failed": pdf_failed,
        "last_version": _load_state().get("last_version", 0),
        "synced_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }

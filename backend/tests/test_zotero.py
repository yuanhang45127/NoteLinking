"""Zotero 同步端到端：本地 mock Zotero Web API + mock arXiv PDF，不发外网请求。"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import zotero_service

LIB_VERSION = 42

COLLECTIONS = [
    {"key": "COL1", "version": 1, "data": {"name": "AI法学", "parentCollection": False}, "meta": {"numItems": 2}},
]

# 条目1：期刊文章（DOI 去重、中英作者、tags、publicationTitle）
ITEM_A = {
    "key": "ITMA", "version": 10, "data": {
        "itemType": "journalArticle", "title": "Legal LLMs: A Survey",
        "creators": [
            {"creatorType": "author", "firstName": "Wei", "lastName": "张"},
            {"creatorType": "author", "firstName": "John", "lastName": "Smith"},
        ],
        "date": "2024-03-15", "publicationTitle": "Artificial Intelligence Review",
        "abstractNote": "A survey of legal LLMs.", "DOI": "10.1000/xyz.123",
        "url": "https://doi.org/10.1000/xyz.123", "tags": [{"tag": "survey"}, {"tag": "法律"}],
    },
}
# 条目2：预印本（DOI 里带 arXiv:2401.12345v2 → 解析出 arxiv_id 2401.12345）
ITEM_B = {
    "key": "ITMB", "version": 11, "data": {
        "itemType": "preprint", "title": "Court Judgment Prediction with LLMs",
        "creators": [{"creatorType": "author", "name": "Yuki Tanaka"}],
        "date": "2024-01-20", "abstractNote": "We predict judgments.", "DOI": "arXiv:2401.12345v2",
        "url": "https://arxiv.org/abs/2401.12345v2", "tags": [],
        "archiveID": "arXiv:2401.12345v2",
    },
}
# 条目3：笔记条目（应被过滤，不计入 fetched）
ITEM_NOTE = {"key": "ITMN", "version": 12, "data": {"itemType": "note", "note": "xx", "title": "ignore"}}

HITS = []  # mock 服务收到的请求路径记录（断言作用域/增量参数）


class MockZotero(BaseHTTPRequestHandler):
    def log_message(self, *a):  # 静默访问日志
        pass

    def _send(self, payload: bytes, version: bool = True, ctype: str = "application/json"):
        self.send_response(200)
        if version:
            self.send_header("Last-Modified-Version", str(LIB_VERSION))
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        HITS.append(self.path)
        path, _, query = self.path.partition("?")
        since = "since=" in query
        if path == f"/users/u1/collections":
            return self._send(json.dumps(COLLECTIONS).encode())
        if path.endswith("/items/top"):
            if since:
                # 增量：游标之后这两条被标记为“有变动”，重新下发（已收录的应被去重跳过）
                items = [ITEM_A, ITEM_B]
            else:
                items = [ITEM_A, ITEM_B, ITEM_NOTE]
            if "collections/COL1" in path:
                items = [ITEM_A]  # 作用域过滤
            return self._send(json.dumps(items).encode())
        if path.startswith("/pdf/"):  # mock arXiv PDF
            return self._send(b"%PDF-1.4 mock paper bytes" + b"x" * 2048, version=False, ctype="application/pdf")
        self.send_response(404)
        self.end_headers()


mock_zotero_base = [""]  # mock_zotero fixture 装填，供 _setup 引用


@pytest.fixture(scope="module")
def mock_zotero():
    srv = HTTPServer(("127.0.0.1", 0), MockZotero)
    port = srv.server_address[1]
    mock_zotero_base[0] = f"http://127.0.0.1:{port}"
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    yield mock_zotero_base[0]
    srv.shutdown()


@pytest.fixture()
def client(data_dir, mock_zotero, monkeypatch):
    monkeypatch.setattr(zotero_service, "ARXIV_PDF_BASE", mock_zotero + "/pdf")
    with TestClient(app) as c:
        yield c


def _setup(c, **cfg):
    body = {"user_id": "u1", "api_key": "k1", "base_url": mock_zotero_base[0], **cfg}
    r = c.put("/api/papers/zotero/config", json=body)
    assert r.status_code == 200


def test_config_mask_and_keep_key(client):
    r = client.put("/api/papers/zotero/config", json={"user_id": "u1", "api_key": "secret", "base_url": ""})
    assert r.status_code == 200
    cfg = r.json()
    assert cfg["api_key"] == zotero_service.MASK and cfg["has_key"] is True
    assert cfg["base_url"] == zotero_service.DEFAULT_BASE

    # 不带 key 再保存 → 沿用旧密钥
    r = client.put("/api/papers/zotero/config", json={"user_id": "u2", "api_key": ""})
    cfg = r.json()
    assert cfg["user_id"] == "u2" and cfg["has_key"] is True

    # 落盘的是真密钥
    from app.services.zotero_service import get_config
    assert get_config()["api_key"] == "secret"


def test_unconfigured_sync_rejected(client, data_dir):
    r = client.post("/api/papers/zotero/sync", json={"topic": "测试"})
    assert r.status_code == 400 and "userID" in r.json()["detail"]


def test_status_lists_collections(client):
    _setup(client)
    r = client.get("/api/papers/zotero/status")
    assert r.status_code == 200
    assert r.json()["collections"][0]["name"] == "AI法学"


def test_sync_mapping_dedup_and_state(client, data_dir):
    _setup(client, download_pdf=False)
    r = client.post("/api/papers/zotero/sync", json={"topic": "法考"})
    assert r.status_code == 200
    body = r.json()
    assert body["fetched"] == 2 and body["added"] == 2 and body["skipped"] == 0
    assert body["last_version"] == LIB_VERSION

    papers = client.get("/api/papers", params={"topic": "法考"}).json()["papers"]
    by_title = {p["title"]: p for p in papers}
    a = by_title["Legal LLMs: A Survey"]
    assert a["authors"] == ["张Wei", "John Smith"]
    assert a["year"] == "2024" and a["venue"] == "Artificial Intelligence Review"
    assert a["doi"] == "10.1000/xyz.123" and "survey" in a["tags"] and "journalArticle" in a["tags"]
    b = by_title["Court Judgment Prediction with LLMs"]
    assert b["arxiv_id"] == "2401.12345"
    assert b["authors"] == ["Yuki Tanaka"] and b["tags"] == ["preprint"]

    # 重复同步：全量条目全部命中去重 → 跳过，不覆盖
    r = client.post("/api/papers/zotero/sync", json={"topic": "法考"}).json()
    assert r["added"] == 0 and r["skipped"] == 2

    # 游标落盘
    state = json.loads((data_dir / "users" / "default" / "papers" / "_zotero_sync.json").read_text())
    assert state["last_version"] == LIB_VERSION

    # 用户数据不被覆盖（改状态后再同步，状态保留）
    pid = a["id"]
    client.put(f"/api/papers/{pid}", params={"topic": "法考"}, json={"status": "done"})
    client.post("/api/papers/zotero/sync", json={"topic": "法考"})
    p = [x for x in client.get("/api/papers", params={"topic": "法考"}).json()["papers"] if x["id"] == pid][0]
    assert p["status"] == "done"


def test_sync_collection_scope(client):
    _setup(client, collection="COL1", collection_name="AI法学", download_pdf=False)
    HITS.clear()
    r = client.post("/api/papers/zotero/sync", json={"topic": "法考"}).json()
    assert r["fetched"] == 1  # mock 对 collection 作用域只回 ITEM_A
    assert any("/collections/COL1/items/top" in h for h in HITS)


def test_sync_with_pdf_download_and_serve(client, monkeypatch):
    # mock 字节不是合法 PDF，提取层只验证我们的接线（下载→导入→建笔记）
    from app.services import pdf_service
    monkeypatch.setattr(pdf_service, "extract_markdown",
                        lambda data, title: (f"# {title}\n\nmock paper bytes", 3))
    _setup(client, download_pdf=True)
    r = client.post("/api/papers/zotero/sync", json={"topic": "法考"}).json()
    assert r["pdf_downloaded"] == 1 and r["pdf_failed"] == 0

    papers = client.get("/api/papers", params={"topic": "法考"}).json()["papers"]
    b = [p for p in papers if p["arxiv_id"]][0]
    assert b["pdf_path"].endswith(".pdf")

    # PDF 文件流
    r = client.get(f"/api/papers/{b['id']}/pdf", params={"topic": "法考"})
    assert r.status_code == 200 and r.content.startswith(b"%PDF")

    # 全文导入 → vault「文献」目录里出现笔记
    r = client.post(f"/api/papers/{b['id']}/import-text", params={"topic": "法考"})
    assert r.status_code == 200
    note_path = r.json()["path"]
    assert note_path.startswith("法考/文献/")
    note = client.get("/api/notes", params={"path": note_path}).json()
    assert "mock paper bytes" in note["content"]
    client.delete("/api/topics/法考", params={"recursive": "true"})

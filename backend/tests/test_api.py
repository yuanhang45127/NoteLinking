"""API 集成测试（TestClient 端到端，不含真实大模型调用）。"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import vault
from app.services.settings_store import load_settings


@pytest.fixture()
def client(data_dir):
    with TestClient(app) as c:
        yield c


def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json()["ok"] is True


def test_topic_note_annotation_flow(client):
    # 主题
    assert client.post("/api/topics", json={"name": "高数"}).status_code == 200
    r = client.get("/api/topics")
    assert r.json()["topics"][0]["name"] == "高数"

    # 笔记
    r = client.post("/api/notes", json={"path": "高数/极限.md", "content": "# 极限\n参见 [[洛必达法则]]"})
    assert r.status_code == 200
    r = client.get("/api/notes", params={"path": "高数/极限.md"})
    body = r.json()
    assert body["backlinks"] == [] and body["annotations"] == []

    # 树
    r = client.get("/api/tree", params={"path": "高数"})
    assert r.json()["children"][0]["name"] == "极限"

    # 高亮
    r = client.post("/api/annotations", json={"path": "高数/极限.md", "quote": "参见", "occurrence": 1})
    assert r.status_code == 200
    ann = r.json()
    assert ann["style"] in ("background", "font")
    r = client.put(f"/api/annotations/{ann['id']}", params={"path": "高数/极限.md"},
                   json={"color": "#123456", "style": "font"})
    assert r.json()["color"] == "#123456"
    r = client.get("/api/notes", params={"path": "高数/极限.md"})
    assert len(r.json()["annotations"]) == 1
    assert client.delete(f"/api/annotations/{ann['id']}", params={"path": "高数/极限.md"}).status_code == 200

    # 反链：建词条文档指向极限
    client.post("/api/notes", json={"path": "高数/terms/洛必达法则.md",
                                    "content": "---\ntype: term\norigin: \"[[极限]]\"\n---\n# 洛必达"})
    r = client.get("/api/notes/backlinks", params={"path": "高数/极限.md"})
    assert r.json()["backlinks"][0]["name"] == "洛必达法则"

    # 图谱
    r = client.get("/api/graph", params={"topic": "高数"})
    g = r.json()
    assert any(n["type"] == "term" for n in g["nodes"])
    assert len(g["edges"]) >= 2

    # 搜索 & 双链解析
    assert client.get("/api/search", params={"q": "洛必达"}).json()["results"]
    r = client.get("/api/notes/resolve-link", params={"target": "洛必达法则", "topic": "高数"})
    assert r.status_code == 200 and r.json()["type"] == "term"

    # 删除笔记
    assert client.delete("/api/notes", params={"path": "高数/terms/洛必达法则.md"}).status_code == 200


def test_settings_providers_and_masking(client):
    r = client.put("/api/settings/providers", json={"providers": [
        {"id": "deepseek", "type": "openai", "name": "DeepSeek",
         "base_url": "https://api.deepseek.com/v1", "api_key": "sk-secret", "model": "deepseek-chat"},
    ]})
    assert r.status_code == 200
    s = r.json()
    assert s["providers"][0]["api_key"] != "sk-secret" and s["providers"][0]["has_key"] is True
    assert s["active_provider"] == "deepseek"

    # 再次保存：不带 key（打码/为空）不应丢掉真实 key
    r = client.put("/api/settings/providers", json={"providers": [
        {"id": "deepseek", "type": "openai", "name": "DeepSeek",
         "base_url": "https://api.deepseek.com/v1", "api_key": "••••••", "model": "deepseek-reasoner"},
    ]})
    raw = load_settings()
    assert raw["providers"][0]["api_key"] == "sk-secret"
    assert raw["providers"][0]["model"] == "deepseek-reasoner"

    # 切换激活服务商
    r = client.put("/api/settings/active", json={"provider_id": ""})
    assert r.status_code == 200
    # 非法类型
    r = client.put("/api/settings/providers", json={"providers": [
        {"id": "x", "type": "unknown-type"}
    ]})
    assert r.status_code == 400


def test_llm_without_provider(client):
    r = client.post("/api/llm/chat", json={"messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 502  # 未配置服务商，统一 LLMError → 502


def test_highlight_settings(client):
    r = client.put("/api/settings/highlight", json={"color": "#ff0000", "style": "font"})
    assert r.json()["highlight"] == {"color": "#ff0000", "style": "font"}
    r = client.put("/api/settings/highlight", json={"style": "bad"})
    assert r.status_code == 400

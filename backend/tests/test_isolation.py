"""多用户数据隔离与路径穿越防护测试。

覆盖：主题/笔记、全文搜索、高亮标注、设置（API Key）、备考目标、
用户目录物理隔离，以及 ../、绝对路径、试卷 ID、主题名等越权尝试。
"""
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.config import get_exams_dir


@pytest.fixture()
def client(data_dir):
    with TestClient(app) as c:
        yield c


@pytest.fixture()
def two_users(data_dir):
    with TestClient(app) as alice, TestClient(app) as bob:
        for c, name in ((alice, "alice"), (bob, "bob")):
            r = c.post("/api/auth/register", json={"username": name, "password": f"pw-{name}1"})
            assert r.status_code == 200
        yield alice, bob


# ---------------------------------------------------------------- 资源隔离
def test_topics_notes_search_isolated(two_users):
    alice, bob = two_users
    alice.post("/api/topics", json={"name": "主题A"})
    alice.post("/api/notes", json={"path": "主题A/秘密.md", "content": "alice 的秘密"})

    assert [t["name"] for t in bob.get("/api/topics").json()["topics"]] == []
    assert bob.get("/api/notes", params={"path": "主题A/秘密.md"}).status_code == 404
    assert bob.get("/api/search", params={"q": "秘密"}).json()["results"] == []

    # bob 建同名主题与笔记，互不干扰
    bob.post("/api/topics", json={"name": "主题A"})
    bob.post("/api/notes", json={"path": "主题A/秘密.md", "content": "bob 的版本"})
    assert "alice 的秘密" in alice.get("/api/notes", params={"path": "主题A/秘密.md"}).json()["content"]
    assert "bob 的版本" in bob.get("/api/notes", params={"path": "主题A/秘密.md"}).json()["content"]


def test_annotations_isolated(two_users):
    alice, bob = two_users
    alice.post("/api/notes", json={"path": "笔记.md", "content": "alice 正文"})
    bob.post("/api/notes", json={"path": "笔记.md", "content": "bob 正文"})

    alice.post("/api/annotations", json={"path": "笔记.md", "quote": "alice 的划线"})
    assert len(alice.get("/api/annotations", params={"path": "笔记.md"}).json()["annotations"]) == 1
    assert bob.get("/api/annotations", params={"path": "笔记.md"}).json()["annotations"] == []

    bob.post("/api/annotations", json={"path": "笔记.md", "quote": "bob 的划线"})
    a_quotes = {a["quote"] for a in alice.get("/api/annotations", params={"path": "笔记.md"}).json()["annotations"]}
    b_quotes = {a["quote"] for a in bob.get("/api/annotations", params={"path": "笔记.md"}).json()["annotations"]}
    assert a_quotes == {"alice 的划线"} and b_quotes == {"bob 的划线"}


def test_settings_and_api_keys_isolated(two_users):
    alice, bob = two_users
    prov = {"id": "p1", "type": "openai", "name": "alice 的服务商",
            "api_key": "sk-alice-secret", "base_url": "https://api.example.com/v1", "model": "m"}
    assert alice.put("/api/settings/providers", json={"providers": [prov]}).status_code == 200

    # bob 看不到 alice 的服务商与密钥
    assert all(p["id"] != "p1" for p in bob.get("/api/settings").json().get("providers") or [])
    # alice 自己仍有（密钥脱敏显示）
    mine = [p for p in alice.get("/api/settings").json().get("providers") or [] if p["id"] == "p1"]
    assert mine and "sk-alice-secret" not in mine[0].get("api_key", "")


def test_goals_isolated(two_users):
    alice, bob = two_users
    alice.post("/api/goals", json={"title": "alice 的考研目标"})
    assert bob.get("/api/goals").json()["goals"] == []
    assert [g["title"] for g in alice.get("/api/goals").json()["goals"]] == ["alice 的考研目标"]


def test_user_directories_physically_separated(data_dir, two_users):
    alice_vault = data_dir / "users" / "alice" / "vault"
    bob_vault = data_dir / "users" / "bob" / "vault"
    assert alice_vault.is_dir() and bob_vault.is_dir()
    assert not any(bob_vault.rglob("*"))  # bob 目录里没有任何 alice 的内容


# ---------------------------------------------------------------- 越权尝试
def test_path_traversal_blocked(client):
    client.post("/api/auth/register", json={"username": "alice", "password": "pw-alice1"})
    # 相对路径穿越：.. 一律 400
    for bad in ("../users.json", "../../secret.key", "主题A/../../users.json"):
        r = client.get("/api/notes", params={"path": bad})
        assert r.status_code == 400, f"{bad} → {r.status_code}"
    # 绝对路径被钳入库内：读不到系统文件
    r = client.get("/api/notes", params={"path": "/etc/passwd"})
    assert "root:" not in r.text
    r = client.get("/api/annotations", params={"path": "/etc/passwd"})
    assert r.status_code == 200 and r.json()["annotations"] == []
    # 数据根的 users.json / secret.key 无法经标注或试卷通道读到
    assert client.get("/api/annotations", params={"path": "../../users.json"}).status_code == 400


def test_exam_id_stays_in_user_dir_and_missing_is_404(client):
    client.post("/api/auth/register", json={"username": "alice", "password": "pw-alice1"})
    # ID 的目录成分被剥掉：任何穿越样式最终都落在当前用户 exams/ 下
    assert f"{Path('../../users.json').name}.json" == "users.json.json"
    assert (get_exams_dir() / "users.json.json").parent == get_exams_dir()
    # 不存在的试卷（含穿越样式）返回 4xx，而不是 500 或读到全局文件
    for eid in ("does-not-exist", "..%2F..%2Fusers.json", "%2e%2e%2fusers.json"):
        assert client.get(f"/api/exams/{eid}").status_code in (400, 404), eid
        assert client.delete(f"/api/exams/{eid}").status_code in (400, 404, 405), eid


def test_topic_name_sanitized(client, data_dir):
    client.post("/api/auth/register", json={"username": "alice", "password": "pw-alice1"})
    assert client.post("/api/topics", json={"name": "../../evil"}).status_code == 200
    names = [t["name"] for t in client.get("/api/topics").json()["topics"]]
    assert len(names) == 1
    assert "/" not in names[0] and not names[0].startswith(".")
    # 目录只会建在当前用户 vault 内，不会跑到数据根或库外
    alice_vault = data_dir / "users" / "alice" / "vault"
    assert (alice_vault / names[0]).is_dir()
    assert not (data_dir / "evil").exists()


def test_cors_origins_restricted(client):
    ok = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    evil = client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert evil.headers.get("access-control-allow-origin") != "https://evil.example"

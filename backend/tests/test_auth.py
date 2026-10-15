"""账号系统测试：注册 / 登录 / 会话 / 多用户隔离 / 旧数据迁移。"""
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import auth_service


@pytest.fixture()
def client(data_dir):
    with TestClient(app) as c:
        yield c


def test_open_mode_no_login_needed(client, data_dir):
    r = client.get("/api/auth/status")
    assert r.status_code == 200
    body = r.json()
    assert body["mode"] == "open" and body["users"] == 0

    # 单人开放模式：不登录即可读写
    assert client.post("/api/topics", json={"name": "高数"}).status_code == 200
    assert client.get("/api/topics").json()["topics"][0]["name"] == "高数"


def test_register_login_logout_flow(client):
    # 注册即登录：拿到会话 Cookie
    r = client.post("/api/auth/register", json={"username": "alice", "password": "secret1"})
    assert r.status_code == 200
    assert "nl_session" in r.cookies or "nl_session" in client.cookies

    body = client.get("/api/auth/status").json()
    assert body["mode"] == "multi" and body["user"] == "alice"

    # 登出后需要重新登录
    assert client.post("/api/auth/logout").status_code == 200
    assert client.get("/api/topics").status_code == 401

    # 密码错 → 401；密码对 → 200
    assert client.post("/api/auth/login", json={"username": "alice", "password": "wrong!"}).status_code == 401
    r = client.post("/api/auth/login", json={"username": "alice", "password": "secret1"})
    assert r.status_code == 200
    assert client.get("/api/topics").status_code == 200


def test_register_validation(client):
    assert client.post("/api/auth/register", json={"username": "a", "password": "secret1"}).status_code == 400
    assert client.post("/api/auth/register", json={"username": "alice", "password": "123"}).status_code == 400
    assert client.post("/api/auth/register", json={"username": "alice", "password": "secret1"}).status_code == 200
    # 重复用户名
    client.post("/api/auth/logout")
    assert client.post("/api/auth/register", json={"username": "alice", "password": "secret2"}).status_code == 409
    # 非法用户名（空格 / 特殊字符）
    assert client.post("/api/auth/register", json={"username": "bad name!", "password": "secret1"}).status_code == 400


def test_multi_user_isolation(client):
    with TestClient(app) as alice:
        alice.post("/api/auth/register", json={"username": "alice", "password": "secret1"})
        alice.post("/api/topics", json={"name": "艾丽丝的笔记"})

    with TestClient(app) as bob:
        # 未登录 → 401
        assert bob.get("/api/topics").status_code == 401
        bob.post("/api/auth/register", json={"username": "bob", "password": "secret2"})
        # bob 看不到 alice 的主题
        assert bob.get("/api/topics").json()["topics"] == []
        bob.post("/api/topics", json={"name": "鲍勃的笔记"})
        names = [t["name"] for t in bob.get("/api/topics").json()["topics"]]
        assert names == ["鲍勃的笔记"]

    # alice 重新登录后数据不受影响
    assert client.post("/api/auth/login", json={"username": "alice", "password": "secret1"}).status_code == 200
    names = [t["name"] for t in client.get("/api/topics").json()["topics"]]
    assert names == ["艾丽丝的笔记"]


def test_register_cannot_claim_existing_data(data_dir):
    # 即使请求带 claim_existing，注册也不再接管 default 的数据
    default_vault = data_dir / "users" / "default" / "vault" / "高数"
    default_vault.mkdir(parents=True)
    (default_vault / "极限.md").write_text("# 极限", encoding="utf-8")

    with TestClient(app) as c:
        r = c.post(
            "/api/auth/register",
            json={"username": "lorry", "password": "secret1", "claim_existing": True},
        )
        assert r.status_code == 200 and "claimed_existing" not in r.json()
        # default 数据原地不动，新用户是空库
        assert (data_dir / "users" / "default" / "vault" / "高数" / "极限.md").exists()
        assert not (data_dir / "users" / "lorry" / "vault" / "高数").exists()
        assert c.get("/api/topics").json()["topics"] == []


def test_migration_merges_into_empty_default(data_dir):
    # 现场案例：users/default 被自动建过（空 vault），旧数据还在 data 根下
    (data_dir / "users" / "default" / "vault").mkdir(parents=True)
    legacy = data_dir / "vault" / "机器学习"
    legacy.mkdir(parents=True)
    (legacy / "线性代数.md").write_text("# 线性代数", encoding="utf-8")
    (data_dir / "settings.json").write_text("{}", encoding="utf-8")

    assert auth_service.migrate_legacy_single_user() is True
    assert (data_dir / "users" / "default" / "vault" / "机器学习" / "线性代数.md").exists()
    assert (data_dir / "users" / "default" / "settings.json").exists()
    assert not (data_dir / "vault").exists()
    # 幂等：再跑一遍不再移动
    assert auth_service.migrate_legacy_single_user() is False


def test_migration_skips_when_default_in_use(data_dir):
    legacy = data_dir / "vault"
    legacy.mkdir(parents=True)
    (legacy / "旧笔记.md").write_text("old", encoding="utf-8")
    default_vault = data_dir / "users" / "default" / "vault"
    default_vault.mkdir(parents=True)
    (default_vault / "新笔记.md").write_text("new", encoding="utf-8")

    assert auth_service.migrate_legacy_single_user() is False
    assert (data_dir / "vault" / "旧笔记.md").exists()
    assert (default_vault / "新笔记.md").exists()

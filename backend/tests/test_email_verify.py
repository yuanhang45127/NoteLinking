"""注册邮箱验证码：内存码存储、冷却/上限、开关开启后的注册流程（打桩发送，不真实发信）。"""
import time

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import mail_service


@pytest.fixture()
def send_stub(monkeypatch):
    sent = []

    def _send(email, code):
        sent.append((email, code))

    monkeypatch.setattr(mail_service, "send_verification_code", _send)
    return sent


@pytest.fixture()
def verify_on(monkeypatch):
    monkeypatch.setenv("SMTP_HOST", "smtp.example.com")
    monkeypatch.setenv("SMTP_USER", "noreply@example.com")
    monkeypatch.setenv("SMTP_PASS", "test-pass")
    monkeypatch.setenv("NOTELINK_EMAIL_VERIFY", "1")
    return True


# ---------------------------------------------------------------- 码存储
def test_code_lifecycle(send_stub):
    err, retry = mail_service.issue_code("a@b.com")
    assert err is None and retry is None
    assert len(send_stub) == 1
    code = send_stub[0][1]
    assert len(code) == 6 and code.isdigit()

    # 错码不销毁，可重试；对码销毁
    assert not mail_service.verify_code("a@b.com", "000000")
    assert mail_service.verify_code("a@b.com", code)
    assert not mail_service.verify_code("a@b.com", code)  # 已销毁

    # 过期即失效
    mail_service.issue_code("a@b.com")
    expired = send_stub[1][1]
    mail_service._store["a@b.com"]["expires"] = time.time() - 1
    assert not mail_service.verify_code("a@b.com", expired)


def test_resend_cooldown_and_limit(send_stub, monkeypatch):
    _, retry = mail_service.issue_code("c@d.com")
    assert retry is None
    err, retry = mail_service.issue_code("c@d.com")
    assert retry and 0 < retry <= 60  # 冷却中

    # 冷却归零后清空重计：连发 5 次达上限，第 6 次拒绝
    monkeypatch.setattr(mail_service, "RESEND_COOLDOWN", 0)
    mail_service._store.clear()
    for _ in range(mail_service.SEND_LIMIT_PER_HOUR):
        err, _ = mail_service.issue_code("c@d.com")
        assert err is None
    err, _ = mail_service.issue_code("c@d.com")
    assert err and "频繁" in err


# ---------------------------------------------------------------- 注册流程
@pytest.fixture()
def client(data_dir):
    with TestClient(app) as c:
        yield c
def test_register_requires_code_when_enabled(client, verify_on, send_stub):
    c = client
    assert c.get("/api/auth/status").json()["email_verify"] is True

    # 发码：格式校验 + 冷却
    assert c.post("/api/auth/email-code", json={"email": "not-an-email"}).status_code == 400
    r = c.post("/api/auth/email-code", json={"email": "u1@x.com"})
    assert r.status_code == 200 and r.json()["sent"] is True
    assert c.post("/api/auth/email-code", json={"email": "u1@x.com"}).status_code == 429
    code = send_stub[0][1]

    # 注册：缺验证码 / 错码 / 正确
    body = {"username": "用户一", "password": "pass123", "email": "u1@x.com"}
    assert c.post("/api/auth/register", json=body).status_code == 400
    r = c.post("/api/auth/register", json={**body, "code": "999999"})
    assert r.status_code == 400 and "验证码" in r.json()["detail"]
    r = c.post("/api/auth/register", json={**body, "code": code})
    assert r.status_code == 200 and r.json()["username"] == "用户一"
    assert c.cookies.get("nl_session")

    # 同邮箱不能再注册新账号
    r = c.post("/api/auth/register", json={"username": "user2", "password": "pass123",
                                           "email": "u1@x.com", "code": "123456"})
    assert r.status_code == 409


def test_register_unchanged_when_disabled(client, send_stub):
    assert client.get("/api/auth/status").json()["email_verify"] is False
    assert client.post("/api/auth/email-code", json={"email": "a@b.com"}).status_code == 400
    r = client.post("/api/auth/register", json={"username": "PlainUser", "password": "pass123"})
    assert r.status_code == 200


# ---------------------------------------------------------------- 防爆破
def test_code_five_wrong_attempts_invalidates(client, verify_on, send_stub):
    mail_service.issue_code("u1@x.com")
    code = send_stub[0][1]
    for _ in range(4):
        assert not mail_service.verify_code("u1@x.com", "000000")
    assert mail_service.verify_code("u1@x.com", code)  # 4 错后仍可
    mail_service.issue_code("u1@x.com")
    for _ in range(5):
        mail_service.verify_code("u1@x.com", "000000")
    assert not mail_service.verify_code("u1@x.com", send_stub[1][1])  # 5 错作废


def test_login_lockout_after_five_fails(client):
    client.post("/api/auth/register", json={"username": "alice", "password": "secret1"})
    for _ in range(5):
        r = client.post("/api/auth/login", json={"username": "alice", "password": "wrong"})
        assert r.status_code == 401
    # 锁定后即使密码正确也 429
    r = client.post("/api/auth/login", json={"username": "alice", "password": "secret1"})
    assert r.status_code == 429 and "锁定" in r.json()["detail"]
    # 清除锁后可正常登录（模拟 10 分钟过去由 record/clear 管理）
    from app.services import auth_service
    auth_service.clear_login_fails("alice|testclient")
    r = client.post("/api/auth/login", json={"username": "alice", "password": "secret1"})
    assert r.status_code == 200


def test_register_per_ip_cap(client, monkeypatch):
    monkeypatch.setattr("app.services.auth_service.REGISTER_PER_HOUR", 2)
    for i in range(2):
        r = client.post("/api/auth/register", json={"username": f"user{i}", "password": "pass123"})
        assert r.status_code == 200
    r = client.post("/api/auth/register", json={"username": "user2", "password": "pass123"})
    assert r.status_code == 429

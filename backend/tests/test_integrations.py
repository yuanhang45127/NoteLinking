"""Kimi Code Web 集成：默认关闭、设置读写、端口无服务时不外泄 token。"""
from fastapi.testclient import TestClient

from app.main import app


def test_kimi_web_default_disabled(data_dir):
    with TestClient(app) as c:
        r = c.get("/api/integrations/kimi-web")
        assert r.status_code == 200
        body = r.json()
        assert body == {"enabled": False, "running": False, "url": "", "token": ""}


def test_kimi_web_settings_roundtrip(data_dir):
    with TestClient(app) as c:
        r = c.put("/api/settings/kimi-web", json={"enabled": True, "port": 59999})
        assert r.status_code == 200
        assert r.json()["kimi_web"] == {"enabled": True, "port": 59999}
        # 测试环境 59999 没有 kimi web：探测失败 → running=false，token 不外泄
        body = c.get("/api/integrations/kimi-web").json()
        assert body["enabled"] is True
        assert body["running"] is False and body["url"] == "" and body["token"] == ""


def test_kimi_web_settings_validation(data_dir):
    with TestClient(app) as c:
        assert c.put("/api/settings/kimi-web", json={"port": 70000}).status_code == 400
        assert c.put("/api/settings/kimi-web", json={"port": "abc"}).status_code == 400
        assert c.put("/api/settings/kimi-web", json={"foo": 1}).status_code == 400
        # 默认设置里带 kimi_web 段
        s = c.get("/api/settings").json()
        assert s["kimi_web"] == {"enabled": False, "port": 58627}

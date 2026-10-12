"""批量删除 / 批量移动接口测试。"""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client(data_dir):
    with TestClient(app) as c:
        yield c


def _seed(client):
    client.post("/api/topics", json={"name": "机器学习"})
    client.post("/api/topics", json={"name": "深度学习"})
    for p in ("机器学习/a.md", "机器学习/b.md", "机器学习/子/c.md"):
        client.post("/api/notes", json={"path": p, "content": "# x"})


def test_batch_delete(client, data_dir):
    _seed(client)
    r = client.post("/api/notes/batch", json={
        "action": "delete",
        "paths": ["机器学习/a.md", "机器学习/b.md", "高数/不存在.md"],
    })
    assert r.status_code == 200
    body = r.json()
    assert sorted(body["ok"]) == ["机器学习/a.md", "机器学习/b.md"]
    assert len(body["failed"]) == 1 and body["failed"][0]["path"] == "高数/不存在.md"
    assert client.get("/api/notes", params={"path": "机器学习/a.md"}).status_code == 404


def test_batch_move(client, data_dir):
    _seed(client)
    r = client.post("/api/notes/batch", json={
        "action": "move", "paths": ["机器学习/a.md", "机器学习/b.md"], "target": "深度学习",
    })
    assert r.status_code == 200
    assert len(r.json()["ok"]) == 2
    assert client.get("/api/notes", params={"path": "深度学习/a.md"}).status_code == 200
    assert client.get("/api/notes", params={"path": "机器学习/a.md"}).status_code == 404
    # 同名冲突的目标保持原样并计入失败
    r = client.post("/api/notes/batch", json={
        "action": "move", "paths": ["机器学习/子/c.md", "机器学习/子/c.md"], "target": "深度学习",
    })
    body = r.json()
    assert len(body["ok"]) == 1 and len(body["failed"]) == 1


def test_batch_validation_and_traversal(client, data_dir):
    _seed(client)
    assert client.post("/api/notes/batch", json={"action": "nope", "paths": ["机器学习/a.md"]}).status_code == 400
    assert client.post("/api/notes/batch", json={"action": "delete", "paths": []}).status_code == 400
    assert client.post("/api/notes/batch", json={"action": "move", "paths": ["机器学习/a.md"], "target": ""}).status_code == 400
    # 穿越路径进 failed，不抛 500
    r = client.post("/api/notes/batch", json={"action": "delete", "paths": ["../users.json"]})
    body = r.json()
    assert body["ok"] == [] and len(body["failed"]) == 1

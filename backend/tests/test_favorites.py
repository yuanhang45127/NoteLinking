"""收藏接口测试：POST /api/notes/favorite、GET /api/favorites、目录树 updated_at。"""
import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture()
def client(data_dir):
    with TestClient(app) as c:
        yield c


def _seed(client):
    client.post("/api/topics", json={"name": "高数"})
    client.post("/api/notes", json={"path": "高数/极限.md", "content": "# 极限"})
    client.post("/api/notes", json={"path": "高数/连续.md", "content": "# 连续"})


def test_favorite_endpoint(client):
    """收藏：POST 写 frontmatter fav 键并返回笔记，GET /api/favorites 列出收藏。"""
    _seed(client)

    r = client.post("/api/notes/favorite", json={"path": "高数/极限.md", "fav": True})
    assert r.status_code == 200
    note = r.json()
    assert note["path"] == "高数/极限.md"
    assert note["frontmatter"]["fav"] is True

    r = client.get("/api/favorites")
    assert r.status_code == 200
    assert [f["path"] for f in r.json()["favorites"]] == ["高数/极限.md"]

    # 收藏不影响置顶列表
    client.post("/api/notes/pin", json={"path": "高数/极限.md", "pinned": True})
    assert [f["path"] for f in client.get("/api/favorites").json()["favorites"]] == ["高数/极限.md"]
    assert [p["path"] for p in client.get("/api/pinned").json()["pinned"]] == ["高数/极限.md"]

    # 取消收藏：键移除、列表同步
    r = client.post("/api/notes/favorite", json={"path": "高数/极限.md", "fav": False})
    assert r.status_code == 200
    assert "fav" not in r.json()["frontmatter"]
    assert client.get("/api/favorites").json()["favorites"] == []

    # 不存在的笔记 → 404
    assert client.post("/api/notes/favorite", json={"path": "高数/不存在.md", "fav": True}).status_code == 404


def test_tree_node_updated_at(client):
    """目录树 note 节点带 updated_at（ISO 格式，可解析）。"""
    from datetime import datetime

    client.post("/api/topics", json={"name": "高数"})
    client.post("/api/notes", json={"path": "高数/极限.md", "content": "# 极限"})
    node = client.get("/api/tree", params={"path": "高数"}).json()["children"][0]
    assert node["type"] == "note"
    datetime.fromisoformat(node["updated_at"])

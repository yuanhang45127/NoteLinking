"""概念转完整笔记测试：SSE 落盘、路径回退与覆盖规则（mock 模型输出，不联网）。"""
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import process as _process


@pytest.fixture()
def client(data_dir):
    with TestClient(app) as c:
        yield c


def _sse_events(text: str) -> list:
    out = []
    for line in text.splitlines():
        if line.startswith("data: "):
            out.append(json.loads(line[6:]))
    return out


def _seed_topic_note(client, topic="高数"):
    client.post("/api/topics", json={"name": topic})
    client.post("/api/notes", json={"path": f"{topic}/矩阵.md", "content": "# 矩阵\n特征值很重要"})


def _seed_term(client, term="特征值", topic="高数"):
    """直接落一个概念文档（type: term），不经过大模型。"""
    path = f"{topic}/terms/{term}.md"
    content = (
        "---\ntype: term\ntitle: 特征值\n"
        f"origin: [[矩阵]]\norigin_path: {topic}/矩阵.md\n"
        'sources: [矩阵]\n---\n# 特征值\n\n## 一句话解释\n矩阵的伸缩倍数。\n'
    )
    r = client.post("/api/notes", json={"path": path, "content": content})
    assert r.status_code == 200
    return path


def test_to_note_stream_saves_full_note(client, monkeypatch):
    from app.routers import terms as terms_router

    async def fake_stream(provider_id, messages, model="", temperature=None):
        assert "特征值" in messages[1]["content"]
        for chunk in ("## 是什么\n", "特征值是伸缩倍数", "## 具体用处\n降维"):
            yield chunk

    monkeypatch.setattr(_process, "stream_llm", fake_stream)
    _seed_topic_note(client)
    term_path = _seed_term(client)

    r = client.post("/api/terms/to-note/stream", json={"path": term_path})
    assert r.status_code == 200
    done = [e for e in _sse_events(r.text) if e["type"] == "done"][0]
    assert done["saved_path"] == "高数/特征值.md"

    note = client.get("/api/notes", params={"path": done["saved_path"]}).json()
    fm = note["frontmatter"]
    assert fm["source_term"] == "[[特征值]]"
    assert fm["source_term_path"] == term_path
    assert note["type"] != "term"
    assert "特征值是伸缩倍数" in note["content"]


def test_to_note_rerun_overwrites_own_note(client, monkeypatch):
    from app.routers import terms as terms_router

    async def fake_stream(provider_id, messages, model="", temperature=None):
        yield "第二版内容"

    monkeypatch.setattr(_process, "stream_llm", fake_stream)
    _seed_topic_note(client)
    term_path = _seed_term(client)

    first = client.post("/api/terms/to-note/stream", json={"path": term_path})
    again = client.post("/api/terms/to-note/stream", json={"path": term_path})
    p1 = [e for e in _sse_events(first.text) if e["type"] == "done"][0]["saved_path"]
    p2 = [e for e in _sse_events(again.text) if e["type"] == "done"][0]["saved_path"]
    assert p1 == p2
    body = client.get("/api/notes", params={"path": p1}).json()
    assert "第二版内容" in body["content"]
    assert body["content"].count("# 特征值") == 1  # 覆盖而非追加


def test_to_note_falls_back_when_name_taken(client, monkeypatch):
    from app.routers import terms as terms_router

    async def fake_stream(provider_id, messages, model="", temperature=None):
        yield "正文"

    monkeypatch.setattr(_process, "stream_llm", fake_stream)
    _seed_topic_note(client)
    # 同名位置被一篇无关笔记占用
    client.post("/api/notes", json={"path": "高数/特征值.md", "content": "# 特征值\n手写的旧笔记"})
    term_path = _seed_term(client)

    r = client.post("/api/terms/to-note/stream", json={"path": term_path})
    done = [e for e in _sse_events(r.text) if e["type"] == "done"][0]
    assert done["saved_path"] == "高数/特征值（详解）.md"
    old = client.get("/api/notes", params={"path": "高数/特征值.md"}).json()
    assert "手写的旧笔记" in old["content"]  # 原笔记不动


def test_to_note_rejects_non_term(client):
    _seed_topic_note(client)
    r = client.post("/api/terms/to-note/stream", json={"path": "高数/矩阵.md"})
    assert r.status_code == 400


def test_to_note_409_when_all_candidates_taken(client):
    _seed_topic_note(client)
    for suffix in ("", "（详解）", "（详解2）", "（详解3）"):
        client.post("/api/notes", json={"path": f"高数/特征值{suffix}.md", "content": f"无关笔记{suffix}"})
    term_path = _seed_term(client)

    r = client.post("/api/terms/to-note/stream", json={"path": term_path})
    assert r.status_code == 409

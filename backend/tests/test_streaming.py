"""流式生成接口测试：SSE 协议、落盘与结果结构（mock 模型输出，不联网）。"""
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app


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


def _seed_note(client, path="高数/矩阵.md", content="# 矩阵\n特征值很重要"):
    client.post("/api/topics", json={"name": path.split("/")[0]})
    client.post("/api/notes", json={"path": path, "content": content})


def test_term_stream(client, data_dir, monkeypatch):
    from app.routers import terms as terms_router

    async def fake_stream(provider_id, messages, model="", temperature=None):
        for chunk in ("特征值是", "矩阵的伸缩倍数"):
            yield chunk

    monkeypatch.setattr(terms_router, "stream_llm", fake_stream)
    _seed_note(client)

    r = client.post("/api/terms/stream", json={"path": "高数/矩阵.md", "term": "特征值"})
    assert r.status_code == 200
    assert "text/event-stream" in r.headers["content-type"]

    events = _sse_events(r.text)
    assert [e["type"] for e in events] == ["delta", "delta", "done"]
    assert events[0]["text"] == "特征值是"
    assert events[-1]["saved_path"] == "高数/terms/特征值.md"
    assert events[-1]["is_new"] is True

    # 落盘内容包含流式产生的全文
    note = client.get("/api/notes", params={"path": "高数/terms/特征值.md"}).json()
    assert "特征值是矩阵的伸缩倍数" in note["content"]
    assert note["type"] == "term"


def test_term_stream_regenerate(client, data_dir, monkeypatch):
    from app.routers import terms as terms_router

    calls = []

    async def fake_stream(provider_id, messages, model="", temperature=None):
        calls.append(messages)
        yield "新解释"

    monkeypatch.setattr(terms_router, "stream_llm", fake_stream)
    _seed_note(client)
    client.post("/api/terms/stream", json={"path": "高数/矩阵.md", "term": "特征值"})

    r = client.post("/api/terms/stream", json={"path": "高数/矩阵.md", "term": "特征值", "regenerate": True})
    events = _sse_events(r.text)
    assert events[-1]["regenerated"] is True
    note = client.get("/api/notes", params={"path": "高数/terms/特征值.md"}).json()
    assert "新解释" in note["content"] and "伸缩倍数" not in note["content"]


def test_exam_stream(client, data_dir, monkeypatch):
    from app.routers import exams as exams_router

    raw = json.dumps({
        "title": "矩阵小测",
        "questions": [
            {"id": "q1", "type": "mcq", "question": "1+1=?", "options": ["1", "2", "3", "4"], "answer": "B", "explanation": "显然"},
        ],
    }, ensure_ascii=False)

    async def fake_stream(provider_id, messages, model="", temperature=None):
        for i in range(0, len(raw), 20):
            yield raw[i:i + 20]

    monkeypatch.setattr(exams_router, "stream_llm", fake_stream)
    _seed_note(client, "高数/数.md", "数字内容")

    r = client.post("/api/exams/generate/stream", json={"paths": ["高数/数.md"], "types": ["mcq"], "count": 1})
    assert r.status_code == 200
    events = _sse_events(r.text)
    assert events[-1]["type"] == "done"
    assert events[-1]["count"] == 1

    exam = client.get(f"/api/exams/{events[-1]['exam_id']}").json()
    assert exam["title"] == "矩阵小测"
    assert exam["questions"][0]["question"] == "1+1=?"
    # 流式输出的原始片段不能当作正文落盘
    assert len(exam["questions"]) == 1


def test_checklist_stream(client, data_dir, monkeypatch):
    from app.routers import exams as exams_router

    raw = json.dumps({"points": [
        {"point": "特征值定义", "importance": "高", "suggestion": "背定义"},
        {"point": "矩阵乘法", "importance": "中", "suggestion": "多做练习"},
    ]}, ensure_ascii=False)

    async def fake_stream(provider_id, messages, model="", temperature=None):
        yield raw

    monkeypatch.setattr(exams_router, "stream_llm", fake_stream)
    _seed_note(client, "高数/数.md", "数字内容")

    r = client.post("/api/exams/checklist/stream", json={"paths": ["高数/数.md"]})
    events = _sse_events(r.text)
    assert events[-1]["type"] == "done"
    doc = events[-1]["checklist"]
    assert [p["point"] for p in doc["items"]] == ["特征值定义", "矩阵乘法"]
    assert doc["topic"] == "高数"
    # 与 GET 接口读到的是同一份
    again = client.get("/api/exams/checklist", params={"topic": "高数"}).json()["checklist"]
    assert again["items"][0]["id"] == "p1"


def test_study_guide_stream(client, data_dir, monkeypatch):
    from app.routers import llm as llm_router

    async def fake_stream(provider_id, messages, model="", temperature=None):
        for chunk in ("## 一页速览\n", "重点是特征值。"):
            yield chunk

    monkeypatch.setattr(llm_router, "stream_llm", fake_stream)
    _seed_note(client, "高数/数.md", "数字内容")

    r = client.post("/api/llm/study-guide/stream", json={"paths": ["高数/数.md"]})
    events = _sse_events(r.text)
    assert events[-1]["type"] == "done"
    assert events[-1]["markdown"] == "## 一页速览\n重点是特征值。"


def test_stream_error_propagates(client, data_dir, monkeypatch):
    from app.services.llm_service import LLMError
    from app.routers import terms as terms_router

    async def fake_stream(provider_id, messages, model="", temperature=None):
        raise LLMError("服务商不可用")
        yield  # pragma: no cover

    monkeypatch.setattr(terms_router, "stream_llm", fake_stream)
    _seed_note(client)
    r = client.post("/api/terms/stream", json={"path": "高数/矩阵.md", "term": "特征值"})
    events = _sse_events(r.text)
    assert events[-1]["type"] == "error" and "服务商不可用" in events[-1]["message"]

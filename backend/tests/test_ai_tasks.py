"""服务端后台 AI 任务：启动 / 事件流回放 / 列表 / 取消 / 过程事件。"""
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import process as _process


@pytest.fixture()
def client(data_dir):
    with TestClient(app) as c:
        yield c


def _sse_events(text):
    out = []
    for line in text.split("\n"):
        if line.startswith("data:"):
            out.append(json.loads(line[5:]))
    return out


@pytest.fixture()
def seeded_note(client):
    client.post("/api/topics", json={"name": "高数"})
    client.post("/api/notes", json={"path": "高数/矩阵.md", "content": "# 矩阵\n\n正文"})


def test_task_lifecycle_events_and_list(client, seeded_note, monkeypatch):
    async def fake_stream(provider_id, messages, model="", temperature=None):
        for chunk in ("第一段。", "第二段。"):
            yield chunk

    monkeypatch.setattr(_process, "stream_llm", fake_stream)

    # 1) 启动后台任务
    r = client.post("/api/ai-tasks", json={
        "title": "测试生成", "kind": "note", "op": "generate-note",
        "payload": {"topic": "高数", "prompt": "写矩阵", "save_path": "高数/生成.md"},
    })
    assert r.status_code == 200
    task = r.json()
    assert task["status"] == "running"
    tid = task["id"]

    # 2) 事件流：回放全部事件直到 done
    with client as c:
        r2 = c.post(f"/api/ai-tasks/{tid}/events")
    events = _sse_events(r2.text)
    types = [e["type"] for e in events]
    assert types[0] == "llm_start"
    # 连续 delta 在服务端合并为一条
    assert types.count("delta") == 1
    assert next(e for e in events if e["type"] == "delta")["text"] == "第一段。第二段。"
    assert types[-1] == "done"
    assert events[-1]["saved_path"] == "高数/生成.md"

    # 3) 列表里任务已结束并带结果
    tasks = client.get("/api/ai-tasks").json()["tasks"]
    row = next(t for t in tasks if t["id"] == tid)
    assert row["status"] == "done"
    assert row["result"]["saved_path"] == "高数/生成.md"
    assert row["chars"] > 0

    # 4) 笔记确实落盘
    note = client.get("/api/notes", params={"path": "高数/生成.md"})
    assert note.status_code == 200


def test_task_error_event(client, seeded_note, monkeypatch):
    from app.services.llm_service import LLMError

    async def fake_stream(provider_id, messages, model="", temperature=None):
        raise LLMError("服务商配置缺失")
        yield  # pragma: no cover

    monkeypatch.setattr(_process, "stream_llm", fake_stream)
    r = client.post("/api/ai-tasks", json={
        "title": "会失败", "kind": "chat", "op": "chat",
        "payload": {"messages": [{"role": "user", "content": "hi"}]},
    })
    tid = r.json()["id"]
    with client as c:
        r2 = c.post(f"/api/ai-tasks/{tid}/events")
    events = _sse_events(r2.text)
    assert events[-1]["type"] == "error"
    assert "服务商配置缺失" in events[-1]["message"]
    row = next(t for t in client.get("/api/ai-tasks").json()["tasks"] if t["id"] == tid)
    assert row["status"] == "error"


def test_task_cancel(client, seeded_note, monkeypatch):
    import asyncio

    async def fake_stream(provider_id, messages, model="", temperature=None):
        yield "开始"
        await asyncio.sleep(30)  # 挂住，等取消
        yield "不会到这里"

    monkeypatch.setattr(_process, "stream_llm", fake_stream)
    r = client.post("/api/ai-tasks", json={
        "title": "会取消", "kind": "chat", "op": "chat",
        "payload": {"messages": [{"role": "user", "content": "hi"}]},
    })
    tid = r.json()["id"]
    assert client.post(f"/api/ai-tasks/{tid}/cancel").json()["ok"] is True
    with client as c:
        r2 = c.post(f"/api/ai-tasks/{tid}/events")
    events = _sse_events(r2.text)
    # 取消发生在 llm_done 之前，llm_done 不会出现
    assert [e["type"] for e in events] == ["llm_start", "delta"]
    row = next(t for t in client.get("/api/ai-tasks").json()["tasks"] if t["id"] == tid)
    assert row["status"] == "stopped"


def test_unknown_op_errors(client):
    r = client.post("/api/ai-tasks", json={
        "title": "未知", "kind": "note", "op": "no-such-op", "payload": {}})
    tid = r.json()["id"]
    with client as c:
        r2 = c.post(f"/api/ai-tasks/{tid}/events")
    events = _sse_events(r2.text)
    assert events[-1]["type"] == "error"
    assert "未知任务类型" in events[-1]["message"]

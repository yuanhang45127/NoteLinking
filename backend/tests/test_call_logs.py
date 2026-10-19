"""调用日志：SSE 边界统一记录（含流程直 yield 的 tool 事件）、delta 合并与截断、
q 过滤、上限裁剪、后台任务会话、防抖落盘与 API 端点。"""
import asyncio
import json

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import call_log_store, chat_agent, process


@pytest.fixture()
def client(data_dir):
    with TestClient(app) as c:
        yield c


def _reset():
    """清空模块级运行态；待落盘任务先取消，避免跨用例污染。"""
    for t in list(call_log_store._flush_tasks):
        try:
            t.cancel()
        except Exception:  # noqa: BLE001 — 任务所属事件循环可能已关闭
            pass
    call_log_store._flush_tasks.clear()
    call_log_store._flush_pending.clear()
    call_log_store._dirty.clear()
    call_log_store._by_user.clear()
    call_log_store._loaded.clear()


@pytest.fixture(autouse=True)
def _reset_store():
    """调用日志是模块级内存 + 按用户懒加载，用例间必须清空（数据目录已由 data_dir 隔离）。"""
    _reset()
    yield
    _reset()


def _llm_start(seq: int = 1, purpose: str = "对话", provider: str = "p", model: str = "m") -> dict:
    return {"type": "llm_start", "seq": seq, "purpose": purpose,
            "provider": provider, "model": model, "prompt_chars": 10}


async def _feed(sid: str) -> None:
    """灌一条完整会话的事件：llm_start → delta×2（应合并）→ llm_done → step×2 → tool×2。"""
    await call_log_store.record_event(sid, _llm_start())
    await call_log_store.record_event(sid, {"type": "delta", "text": "你好"})
    await call_log_store.record_event(sid, {"type": "delta", "text": "，世界"})
    await call_log_store.record_event(sid, {"type": "llm_done", "seq": 1, "chars": 5, "elapsed": 1.5})
    await call_log_store.record_event(sid, {"type": "step", "name": "save", "status": "start", "label": "保存"})
    await call_log_store.record_event(sid, {"type": "step", "name": "save", "status": "done", "label": "保存"})
    await call_log_store.record_event(sid, {"type": "tool", "name": "web_search", "args": {"q": "x"}, "status": "start"})
    await call_log_store.record_event(sid, {"type": "tool", "name": "web_search", "args": {"q": "x"},
                                            "status": "done", "ok": True, "summary": "命中 2 条"})


# ---------------------------------------------------------------- 存储层
def test_session_lifecycle_list_and_get(data_dir):
    async def scenario():
        sid = await call_log_store.start_session("chat")
        await _feed(sid)
        await call_log_store.end_session(sid)

        entries = await call_log_store.list_records()
        assert len(entries) == 1
        e = entries[0]
        assert e["id"] == sid and e["flow"] == "chat" and e["purpose"] == "对话"
        assert e["llm_calls"] == 1 and e["tool_calls"] == 1 and e["steps"] == 1
        assert e["models"] == ["p/m"]
        assert "events" not in e and e["ts"]          # 列表项不带事件，ISO8601 时间戳

        rec = await call_log_store.get_record(sid)
        assert rec is not None
        assert [ev["type"] for ev in rec["events"]] == [
            "llm_start", "delta", "llm_done", "step", "step", "tool", "tool"]
        assert rec["events"][1]["text"] == "你好，世界"   # 连续 delta 合并为一条
        assert rec["llm"] == [{"provider": "p", "model": "m", "prompt_chars": 10,
                               "output_chars": 5, "elapsed_ms": 1500}]
        assert rec["summary"] == {"llm_calls": 1, "tool_calls": 1, "steps": 1}
        assert await call_log_store.get_record("不存在的id") is None

    asyncio.run(scenario())


def test_empty_session_dropped_on_end(data_dir):
    async def scenario():
        sid = await call_log_store.start_session("chat")
        await call_log_store.end_session(sid)
        assert await call_log_store.list_records() == []
        assert await call_log_store.get_record(sid) is None

    asyncio.run(scenario())


def test_persist_and_reload(data_dir):
    async def scenario():
        sid = await call_log_store.start_session("chat")
        await _feed(sid)
        await call_log_store.end_session(sid)

        # 模拟重启：清空内存，懒加载应从 JSONL 恢复
        call_log_store._by_user.clear()
        call_log_store._loaded.clear()
        entries = await call_log_store.list_records()
        assert len(entries) == 1 and entries[0]["id"] == sid
        rec = await call_log_store.get_record(sid)
        assert rec is not None and len(rec["events"]) == 7
        assert rec["events"][1]["text"] == "你好，世界"

    asyncio.run(scenario())


def test_delta_text_truncated_on_store_and_reload(data_dir):
    """delta 正文截断到 1000 字符（带原长度标记），落盘与读回一致。"""
    async def scenario():
        sid = await call_log_store.start_session("chat")
        await call_log_store.record_event(sid, {"type": "delta", "text": "x" * 2500})
        rec = await call_log_store.get_record(sid)
        text = rec["events"][0]["text"]
        assert text.startswith("x" * 1000)
        assert text.endswith(" …[截断，共2500字符]")

        await call_log_store.end_session(sid)
        call_log_store._by_user.clear()
        call_log_store._loaded.clear()
        rec2 = await call_log_store.get_record(sid)
        assert rec2["events"][0]["text"] == text

    asyncio.run(scenario())


def test_q_filter_and_paging(data_dir):
    async def scenario():
        sid1 = await call_log_store.start_session("chat")
        await call_log_store.record_event(sid1, _llm_start(purpose="对话"))
        sid2 = await call_log_store.start_session("generate-note")
        await call_log_store.record_event(sid2, _llm_start(purpose="生成笔记正文"))

        assert len(await call_log_store.list_records()) == 2
        assert len(await call_log_store.list_records(q="CHAT")) == 1        # 大小写不敏感，匹配 flow
        assert (await call_log_store.list_records(q="chat"))[0]["id"] == sid1
        assert len(await call_log_store.list_records(q="笔记")) == 1        # 匹配 purpose
        assert len(await call_log_store.list_records(q="不存在的关键词")) == 0

        assert [r["id"] for r in await call_log_store.list_records(limit=1)] == [sid2]   # 新 → 旧
        assert (await call_log_store.list_records(limit=1, offset=1))[0]["id"] == sid1

    asyncio.run(scenario())


def test_cap_pruning(data_dir, monkeypatch):
    monkeypatch.setattr(call_log_store, "MAX_RECORDS", 3)

    async def scenario():
        ids = []
        for i in range(5):
            sid = await call_log_store.start_session("chat")
            await call_log_store.record_event(sid, _llm_start(purpose=f"第{i}次"))
            await call_log_store.end_session(sid)
            ids.append(sid)
        return ids, [e["id"] for e in await call_log_store.list_records(limit=50)]

    ids, listed = asyncio.run(scenario())
    assert listed == list(reversed(ids[-3:]))


def test_flush_loop_stops_when_idle(data_dir, monkeypatch):
    """防抖循环：有变更才落盘，空闲后退出，不会无限重排（重启也可恢复进行中的会话）。"""
    monkeypatch.setattr(call_log_store, "FLUSH_DELAY", 0.2)

    async def scenario():
        sid = await call_log_store.start_session("unknown")
        await call_log_store.record_event(sid, _llm_start())
        await asyncio.sleep(0.2 * 2 + 0.3)      # 两轮：落盘 + 空闲退出
        assert not call_log_store._dirty.get("default")
        assert "default" not in call_log_store._flush_pending
        f = call_log_store._file()
        first = f.read_bytes()
        await asyncio.sleep(0.2 * 2 + 0.2)      # 再等：无变更不应有任何重写
        assert f.read_bytes() == first
        return sid

    sid = asyncio.run(scenario())
    call_log_store._by_user.clear()
    call_log_store._loaded.clear()
    entries = asyncio.run(call_log_store.list_records())
    assert len(entries) == 1 and entries[0]["id"] == sid
    assert asyncio.run(call_log_store.get_record(sid))["summary"]["llm_calls"] == 1


# ---------------------------------------------------------------- API 端点
def _sse_events(text):
    out = []
    for line in text.split("\n"):
        if line.startswith("data:"):
            out.append(json.loads(line[5:]))
    return out


def test_api_end_to_end(client, monkeypatch):
    """真实 SSE 端点：process 助手产出的事件在边界恰好记录一次（含收尾 done）。"""
    async def fake_stream(provider_id, messages, model="", temperature=None):
        for chunk in ("第一段。", "第二段。"):
            yield chunk

    monkeypatch.setattr(process, "stream_llm", fake_stream)

    r = client.post("/api/llm/chat", json={
        "stream": True, "model": "gpt-4o-mini",
        "messages": [{"role": "user", "content": "你好"}],
    })
    assert r.status_code == 200
    events = _sse_events(r.text)
    assert events[-1]["type"] == "done"

    body = client.get("/api/call-logs").json()
    assert len(body["entries"]) == 1
    e = body["entries"][0]
    assert e["flow"] == "chat" and e["purpose"] == "对话"
    assert e["llm_calls"] == 1 and e["tool_calls"] == 0 and e["steps"] == 0
    assert e["models"] == ["/gpt-4o-mini"]

    rec = client.get(f"/api/call-logs/{e['id']}").json()
    assert rec["id"] == e["id"]
    assert [ev["type"] for ev in rec["events"]] == ["llm_start", "delta", "llm_done", "done"]
    assert rec["events"][1]["text"] == "第一段。第二段。"
    assert rec["llm"][0]["output_chars"] == len("第一段。第二段。")

    assert client.get("/api/call-logs/不存在的id").status_code == 404


def test_api_chat_tool_events_recorded(client, monkeypatch):
    """回归（原缺陷 1）：chat_agent 直接 yield 的 tool 事件（不经 process 助手）
    也必须经 SSE 边界落库，tool_calls 计数正确、不双记。"""
    async def fake_llm_call(provider_id, messages, model="", temperature=None, purpose="", seq=1):
        yield {"type": "llm_start", "seq": seq, "purpose": purpose,
               "provider": "p", "model": "m", "prompt_chars": 10}
        if seq == 1:
            yield {"type": "delta", "text": '```json\n{"tool": "search_notes", "args": {"q": "EDA"}}\n```'}
        else:
            yield {"type": "delta", "text": "查到了：EDA 是电子设计自动化。"}
        yield {"type": "llm_done", "seq": seq, "chars": 5, "elapsed": 0.1}

    monkeypatch.setattr(chat_agent.process, "llm_call", fake_llm_call)

    sid = client.post("/api/chat/sessions", json={}).json()["id"]
    r = client.post(f"/api/chat/sessions/{sid}/turn",
                    json={"content": "EDA 是什么", "provider": "p", "model": "m"})
    assert r.status_code == 200

    entries = client.get("/api/call-logs").json()["entries"]
    assert len(entries) == 1
    e = entries[0]
    assert e["flow"] == "unknown" and e["purpose"] == "回答"
    assert e["tool_calls"] == 1 and e["llm_calls"] == 2 and e["steps"] == 1
    rec = client.get(f"/api/call-logs/{e['id']}").json()
    tools = [ev for ev in rec["events"] if ev["type"] == "tool"]
    assert [t["status"] for t in tools] == ["start", "done"]
    assert tools[1]["name"] == "search_notes" and tools[1]["ok"] is True
    # 每个事件恰好出现一次（无双记）
    types = [ev["type"] for ev in rec["events"]]
    assert types.count("llm_start") == 2 and types.count("delta") == 2


def test_api_web_context_step_recorded(client, monkeypatch):
    """web_context_step 的 tool 事件经 SSE 边界落库；内部键（_results/_block）不落库。"""
    async def fake_search(query, max_results=6):
        return [{"title": "t", "url": "u"}], "上下文块"

    async def fake_stream(provider_id, messages, model="", temperature=None):
        yield "正文"

    monkeypatch.setattr(process.websearch_service, "is_enabled", lambda: True)
    monkeypatch.setattr(process.websearch_service, "search_and_block", fake_search)
    monkeypatch.setattr(process, "stream_llm", fake_stream)

    r = client.post("/api/llm/generate-note", json={
        "stream": True, "use_web": True, "topic": "演示", "title": "演示",
        "prompt": "写一篇演示笔记",
    })
    assert r.status_code == 200
    assert any(ev.get("type") == "tool" for ev in _sse_events(r.text))

    entries = client.get("/api/call-logs").json()["entries"]
    assert len(entries) == 1
    e = entries[0]
    assert e["flow"] == "generate-note" and e["purpose"] == "生成笔记正文"
    assert e["tool_calls"] == 1
    rec = client.get(f"/api/call-logs/{e['id']}").json()
    tools = [ev for ev in rec["events"] if ev["type"] == "tool"]
    assert [t["status"] for t in tools] == ["start", "done"]
    assert all(not k.startswith("_") for ev in rec["events"] for k in ev)


def test_api_record_failure_never_breaks_sse(client, monkeypatch):
    """记录故障绝不能影响流式输出（SSE 边界 try/except 兜底）。"""
    async def boom(session_id, event):
        raise RuntimeError("日志故障")

    async def fake_stream(provider_id, messages, model="", temperature=None):
        yield "ok"

    monkeypatch.setattr(call_log_store, "record_event", boom)
    monkeypatch.setattr(process, "stream_llm", fake_stream)

    r = client.post("/api/llm/chat", json={"stream": True,
                                           "messages": [{"role": "user", "content": "hi"}]})
    assert r.status_code == 200
    assert [e["type"] for e in _sse_events(r.text)] == [
        "llm_start", "delta", "llm_done", "done"]


def test_api_list_q_and_paging(client):
    async def seed():
        for flow, purpose in (("chat", "对话"), ("generate-note", "生成笔记正文")):
            sid = await call_log_store.start_session(flow)
            await call_log_store.record_event(sid, _llm_start(purpose=purpose))
            await call_log_store.end_session(sid)

    asyncio.run(seed())
    body = client.get("/api/call-logs", params={"q": "CHAT"}).json()
    assert len(body["entries"]) == 1 and body["entries"][0]["flow"] == "chat"

    body = client.get("/api/call-logs", params={"limit": 1}).json()
    assert len(body["entries"]) == 1 and body["entries"][0]["flow"] == "generate-note"
    body = client.get("/api/call-logs", params={"limit": 1, "offset": 1}).json()
    assert body["entries"][0]["flow"] == "chat"


def test_api_ai_task_records_once_with_flow(client, monkeypatch):
    """后台任务：事件在 append_event 汇点记录一次；回放不重复记录；
    流程名取任务 op（不再是 unknown）。"""
    async def fake_stream(provider_id, messages, model="", temperature=None):
        for chunk in ("甲", "乙"):
            yield chunk

    monkeypatch.setattr(process, "stream_llm", fake_stream)
    r = client.post("/api/ai-tasks", json={
        "title": "后台任务", "kind": "note", "op": "chat",
        "payload": {"messages": [{"role": "user", "content": "hi"}]},
    })
    tid = r.json()["id"]
    # 直接复用夹具已进入的 client：嵌套 with 会把请求换到另一个事件循环，
    # 与任务 asyncio.Condition 所在循环不一致（Starlette TestClient 每次进入都新建 portal）
    r2 = client.post(f"/api/ai-tasks/{tid}/events")     # 回放（不得重复记录）
    events = _sse_events(r2.text)
    assert events[-1]["type"] == "done"

    rec = asyncio.run(call_log_store.get_record(f"task-{tid}"))
    assert rec is not None
    assert rec["flow"] == "chat"
    assert [ev["type"] for ev in rec["events"]] == ["llm_start", "delta", "llm_done", "done"]
    assert rec["events"][1]["text"] == "甲乙"
    assert len(client.get("/api/call-logs").json()["entries"]) == 1

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


def test_attempt_stream_grades_progressively(client, data_dir, monkeypatch):
    """交卷流式：简答题逐题推送 grade 事件，done 返回完整 attempt 并落盘。"""
    from app.routers import exams as exams_router
    from app.services import exam_service as exam_service_mod

    raw = json.dumps({"title": "简答卷", "questions": [
        {"id": "q1", "type": "mcq", "question": "1+1=?", "options": ["1", "2", "3", "4"], "answer": "B", "explanation": ""},
        {"id": "q2", "type": "short", "question": "什么是特征值?", "reference_answer": "伸缩倍数", "explanation": ""},
        {"id": "q3", "type": "short", "question": "什么是特征向量?", "reference_answer": "方向", "explanation": ""},
    ]}, ensure_ascii=False)

    async def fake_gen(provider_id, messages, model="", temperature=None):
        yield raw

    monkeypatch.setattr(exams_router, "stream_llm", fake_gen)
    _seed_note(client, "高数/数.md", "内容")
    r = client.post("/api/exams/generate/stream", json={"paths": ["高数/数.md"], "types": ["mcq", "short"], "count": 3})
    exam_id = _sse_events(r.text)[-1]["exam_id"]

    async def fake_complete(provider_id, messages, model="", temperature=None):
        if "特征向量" in messages[-1]["content"]:
            return json.dumps({"score": 60, "feedback": "一般"}, ensure_ascii=False)
        return json.dumps({"score": 80, "feedback": "不错"}, ensure_ascii=False)

    monkeypatch.setattr(exam_service_mod, "complete", fake_complete)

    r = client.post(f"/api/exams/{exam_id}/attempts/stream", json={"answers": [
        {"question_id": "q1", "answer": "B"},
        {"question_id": "q2", "answer": "特征值是伸缩倍数"},
        {"question_id": "q3", "answer": "方向"},
    ]})
    assert "text/event-stream" in r.headers["content-type"]
    events = _sse_events(r.text)
    grade_events = [e for e in events if e["type"] == "grade"]
    assert {e["question_id"] for e in grade_events} == {"q2", "q3"}
    scores = {e["question_id"]: e["score"] for e in grade_events}
    assert scores == {"q2": 80, "q3": 60}

    done = events[-1]
    assert done["type"] == "done"
    attempt = done["attempt"]
    assert attempt["total_score"] == round((100 + 80 + 60) / 3)
    q2 = next(a for a in attempt["answers"] if a["question_id"] == "q2")
    assert q2["score"] == 80 and q2["feedback"] == "不错"
    # attempts 已落盘
    attempts = client.get(f"/api/exams/{exam_id}/attempts").json()["attempts"]
    assert len(attempts) == 1 and attempts[0]["id"] == attempt["id"]


def test_topic_architecture_stream(client, data_dir, monkeypatch):
    """主题整体架构：prompt 带内容盘点，流式生成后落盘为主题下笔记。"""
    from app.routers import llm as llm_router

    seen_prompts = []

    async def fake_stream(provider_id, messages, model="", temperature=None):
        seen_prompts.append(messages[-1]["content"])
        for chunk in ("## 现有内容盘点\n", "已有矩阵运算相关笔记。"):
            yield chunk

    monkeypatch.setattr(llm_router, "stream_llm", fake_stream)
    _seed_note(client, "机器学习/矩阵.md", "# 矩阵\n## 基础运算\n内容")

    r = client.post("/api/llm/topic-architecture/stream", json={"topic": "机器学习"})
    assert r.status_code == 200
    events = _sse_events(r.text)
    assert events[-1]["type"] == "done"
    path = events[-1]["saved_path"]
    assert path == "机器学习/_架构/整体架构.md"
    # prompt 里带上了主题的结构盘点（笔记标题 + 小节）
    assert "机器学习" in seen_prompts[0] and "矩阵" in seen_prompts[0]
    # 落盘为可读笔记
    note = client.get("/api/notes", params={"path": path}).json()
    assert "已有矩阵运算相关笔记" in note["content"]
    assert note["frontmatter"].get("generated") is True

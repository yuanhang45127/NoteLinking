"""考试服务测试：选项归一、出题解析（mock 大模型）、判分流程。"""
import json

import pytest

from app.services import exam_service, vault
from app.services.llm_service import extract_json


def _norm(s):
    return exam_service._norm_choice(s)


def test_norm_choice():
    assert _norm("A") == "A" and _norm("a") == "A"
    assert _norm("B. 函数极限") == "B"
    assert _norm("(C) xxx") == "C"
    assert _norm("D、xxx") == "D"
    assert _norm("") == ""


def test_extract_json():
    assert extract_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert extract_json('好的，结果如下：{"a": {"b": 2}} 请查收') == {"a": {"b": 2}}
    import pytest as _p
    from app.services.llm_service import LLMError

    with _p.raises(LLMError):
        extract_json("完全没有 JSON")


FAKE_EXAM = {
    "title": "极限测试卷",
    "questions": [
        {"id": "q1", "type": "mcq", "question": "lim x->0 sin x / x = ?",
         "options": ["1", "0", "∞", "不存在"], "answer": "A", "explanation": "重要极限"},
        {"id": "q2", "type": "short", "question": "叙述洛必达法则条件",
         "reference_answer": "0/0 或 ∞/∞ 型且导数比极限存在"},
    ],
}


@pytest.fixture()
def mock_llm(monkeypatch):
    async def fake_complete(provider_id, messages, model="", temperature=None):
        last = messages[-1]["content"]
        if "阅卷" in messages[0]["content"]:
            return json.dumps(
                {"grades": [{"id": "q2", "score": 80, "feedback": "要点基本齐全"}]},
                ensure_ascii=False,
            )
        if "学习指南" in last:
            return "# 学习指南\n- [ ] 复习极限"
        return "```json\n" + json.dumps(FAKE_EXAM, ensure_ascii=False) + "\n```"

    monkeypatch.setattr(exam_service, "complete", fake_complete)


def test_generate_and_get(data_dir, mock_llm):
    import asyncio

    vault.create_topic("数学")
    vault.create_note("数学/极限.md", "# 极限 内容")
    exam = asyncio.run(exam_service.generate_exam(["数学/极限.md"], ["mcq", "short"], 2))
    assert exam["title"] == "极限测试卷"
    assert len(exam["questions"]) == 2

    got = exam_service.get_exam(exam["id"])
    assert got["questions"][0]["answer"] == "A"
    no_ans = exam_service.get_exam(exam["id"], include_answers=False)
    assert "answer" not in no_ans["questions"][0]
    assert exam_service.list_exams()[0]["id"] == exam["id"]


def test_submit_attempt_grading(data_dir, mock_llm):
    import asyncio

    vault.create_topic("数学")
    vault.create_note("数学/极限.md", "# 极限")
    exam = asyncio.run(exam_service.generate_exam(["数学/极限.md"], ["mcq", "short"], 2))

    attempt = asyncio.run(
        exam_service.submit_attempt(exam["id"], [
            {"question_id": "q1", "answer": "A. 1"},   # 自动判对
            {"question_id": "q2", "answer": "0/0 型…"},  # 大模型给 80 分
        ])
    )
    assert attempt["answers"][0]["correct"] is True and attempt["answers"][0]["score"] == 100
    assert attempt["answers"][1]["score"] == 80
    assert attempt["total_score"] == 90
    assert len(exam_service.list_attempts(exam["id"])) == 1


def test_study_guide(data_dir, mock_llm):
    import asyncio

    vault.create_topic("数学")
    vault.create_note("数学/极限.md", "# 极限")
    md = asyncio.run(exam_service.generate_study_guide(["数学/极限.md"]))
    assert "学习指南" in md

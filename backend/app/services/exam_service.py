"""考试备考：基于选定笔记让大模型出题（选择题/简答题/闪卡）、
判分（选择题自动判、简答题大模型评阅）、生成学习指南。
参考 NotebookLM 的「学习指南 / 测验」能力。
"""
import datetime
import json
import re
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import HTTPException

from ..config import get_exams_dir
from ..markdown_utils import parse_frontmatter, strip_frontmatter
from . import vault
from .llm_service import complete, extract_json

MAX_CHARS_PER_NOTE = 12000
MAX_CHARS_TOTAL = 48000


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _gather_context(paths: List[str]) -> str:
    if not paths:
        raise HTTPException(status_code=400, detail="请至少选择一篇笔记作为出题范围")
    chunks, total = [], 0
    used = []
    for rel in paths:
        note = vault.read_note(rel)
        body = strip_frontmatter(note["content"])[:MAX_CHARS_PER_NOTE]
        if total + len(body) > MAX_CHARS_TOTAL:
            body = body[: max(0, MAX_CHARS_TOTAL - total)]
        used.append(note["title"])
        chunks.append(f"===== 笔记：《{note['title']}》 =====\n{body}")
        total += len(body)
        if total >= MAX_CHARS_TOTAL:
            break
    return "\n\n".join(chunks), used


def _question_spec(types: List[str]) -> str:
    desc = {
        "mcq": (
            '{"id": "q1", "type": "mcq", "question": "题干", '
            '"options": ["选项内容A", "选项内容B", "选项内容C", "选项内容D"], '
            '"answer": "A", "explanation": "解析"}'
        ),
        "short": (
            '{"id": "q5", "type": "short", "question": "简答题干", '
            '"reference_answer": "参考答案要点", "explanation": "解析"}'
        ),
        "flashcard": ('{"id": "q9", "type": "flashcard", "front": "正面问题", "back": "背面答案"}'),
    }
    lines = []
    for t in types:
        if t not in desc:
            raise HTTPException(status_code=400, detail=f"不支持的题型：{t}（可选 mcq/short/flashcard）")
        lines.append(f"- {t}: {desc[t]}")
    return "\n".join(lines)


def _build_exam_prompt(context: str, types: List[str], count: int, difficulty: str, language: str) -> List[Dict[str, str]]:
    lang = "中文" if language == "zh" else language
    system = (
        "你是资深考试命题人，严格依据给定笔记内容出题，不编造笔记中不存在的内容。"
        "只输出一个 JSON 对象，不要输出任何其他文字或代码块围栏。"
    )
    user = (
        f"以下是我的学习笔记，请据此出一套 {lang} 试题。\n\n"
        f"{context}\n\n"
        f"要求：\n"
        f"1. 共 {count} 题，题型组合为：{', '.join(types)}（合理分配数量，闪卡至少 2 张如包含）；\n"
        f"2. 难度：{difficulty}；覆盖笔记的主要知识点，含少量细节题；\n"
        f"3. 每题的 id 依次为 q1、q2…；选择题 answer 用 \"A\"/\"B\"/\"C\"/\"D\"；\n"
        f"4. 输出格式：\n"
        f'{{"title": "试卷标题", "questions": [\n{_question_spec(types)}\n]}}'
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


async def generate_exam(
    paths: List[str],
    types: List[str],
    count: int,
    difficulty: str = "medium",
    language: str = "zh",
    title: str = "",
    provider_id: str = "",
    model: str = "",
) -> Dict:
    context, used_titles = _gather_context(paths)
    messages = _build_exam_prompt(context, types, max(1, min(count, 50)), difficulty, language)
    raw = await complete(provider_id, messages, model)
    data = extract_json(raw)

    questions = data.get("questions") if isinstance(data, dict) else None
    if not isinstance(questions, list) or not questions:
        raise HTTPException(status_code=502, detail="模型未生成有效题目，请重试")
    for i, q in enumerate(questions, 1):
        q.setdefault("id", f"q{i}")
        q["type"] = q.get("type") or "short"
        if q["type"] == "mcq":
            q["options"] = q.get("options") or []

    exam = {
        "id": datetime.datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:6],
        "title": (title or data.get("title") or "练习卷").strip() or "练习卷",
        "created_at": _now(),
        "scope": {"paths": paths, "titles": used_titles},
        "settings": {"types": types, "count": len(questions), "difficulty": difficulty, "language": language},
        "questions": questions,
        "attempts": [],
    }
    f = get_exams_dir() / f"{exam['id']}.json"
    f.write_text(json.dumps(exam, ensure_ascii=False, indent=2), encoding="utf-8")
    return exam


def list_exams() -> List[Dict]:
    out = []
    for f in sorted(get_exams_dir().glob("*.json"), key=lambda p: p.name, reverse=True):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        out.append(
            {
                "id": data.get("id", f.stem),
                "title": data.get("title", ""),
                "created_at": data.get("created_at", ""),
                "question_count": len(data.get("questions") or []),
                "attempt_count": len(data.get("attempts") or []),
                "scope": data.get("scope", {}),
            }
        )
    return out


def _exam_file(exam_id: str) -> Path:
    f = get_exams_dir() / f"{Path(exam_id).name}.json"
    if not f.exists():
        raise HTTPException(status_code=404, detail=f"试卷不存在：{exam_id}")
    return f


def get_exam(exam_id: str, include_answers: bool = True) -> Dict:
    data = json.loads(_exam_file(exam_id).read_text(encoding="utf-8"))
    if not include_answers:
        data = dict(data)
        data["questions"] = [
            {k: v for k, v in q.items() if k not in ("answer", "reference_answer", "explanation")}
            for q in data.get("questions", [])
        ]
        data.pop("attempts", None)
    return data


def delete_exam(exam_id: str) -> None:
    _exam_file(exam_id).unlink()


def _norm_choice(ans) -> str:
    """把 'A'、'a'、'A. xxx'、'选项A' 归一为首字母。"""
    s = str(ans or "").strip()
    m = re.match(r"^\(?([A-Da-d])\)?[.、．:：\s]", s)
    if m:
        return m.group(1).upper()
    if s and s[0].upper() in "ABCD":
        return s[0].upper()
    return s.upper()


async def _grade_short_questions(questions: List[Dict], answers: Dict[str, str], language: str) -> Dict[str, Dict]:
    short_qs = [q for q in questions if q.get("type") == "short" and str(q.get("id")) in answers]
    if not short_qs:
        return {}
    lang = "中文" if language == "zh" else language
    items = []
    for q in short_qs:
        items.append(
            {
                "id": q["id"],
                "question": q.get("question", ""),
                "reference_answer": q.get("reference_answer", ""),
                "student_answer": answers[q["id"]],
            }
        )
    system = "你是阅卷老师。按参考答案给学生的简答打分，只输出 JSON，不要其他文字。"
    user = (
        f"题目与作答如下（{lang}）：\n{json.dumps(items, ensure_ascii=False, indent=2)}\n\n"
        '请输出：{"grades": [{"id": "题目id", "score": 0到100的整数, "feedback": "一句话点评"}]}'
    )
    raw = await complete("", [{"role": "system", "content": system}, {"role": "user", "content": user}])
    try:
        data = extract_json(raw)
        return {g["id"]: g for g in data.get("grades", []) if isinstance(g, dict) and "id" in g}
    except (HTTPException, KeyError, TypeError):
        return {}


async def submit_attempt(exam_id: str, answers: List[Dict], provider_id: str = "", model: str = "") -> Dict:
    """answers: [{question_id, answer}]；选择题自动判分，简答题交给大模型评阅。"""
    data = json.loads(_exam_file(exam_id).read_text(encoding="utf-8"))
    questions = data.get("questions", [])
    qmap = {str(q["id"]): q for q in questions}
    ans_map = {str(a.get("question_id")): a.get("answer", "") for a in answers}
    language = (data.get("settings") or {}).get("language", "zh")

    short_grades = await _grade_short_questions(questions, ans_map, language)

    per_question, scores = [], []
    for q in questions:
        qid = str(q["id"])
        qtype = q.get("type")
        student = ans_map.get(qid, "")
        entry: Dict = {"question_id": qid, "type": qtype, "answer": student}
        if qtype == "mcq":
            correct = _norm_choice(q.get("answer")) == _norm_choice(student)
            entry["correct"] = correct
            entry["score"] = 100 if correct else 0
            entry["reference"] = q.get("answer")
            entry["feedback"] = q.get("explanation", "")
            scores.append(entry["score"])
        elif qtype == "short":
            g = short_grades.get(qid)
            score = int(g.get("score", 0)) if g else None
            entry["score"] = score
            entry["feedback"] = (g or {}).get("feedback", "")
            entry["reference"] = q.get("reference_answer", "")
            if score is not None:
                scores.append(score)
        else:  # flashcard：自评，不计分
            entry["score"] = None
            entry["reference"] = q.get("back", "")
        per_question.append(entry)

    total = round(sum(scores) / len(scores)) if scores else None
    attempt = {
        "id": uuid.uuid4().hex[:8],
        "submitted_at": _now(),
        "answers": per_question,
        "total_score": total,
        "graded_count": len(scores),
    }
    data.setdefault("attempts", []).append(attempt)
    _exam_file(exam_id).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return attempt


def list_attempts(exam_id: str) -> List[Dict]:
    data = json.loads(_exam_file(exam_id).read_text(encoding="utf-8"))
    return data.get("attempts", [])


async def generate_study_guide(paths: List[str], language: str = "zh", provider_id: str = "", model: str = "") -> str:
    """NotebookLM 风格学习指南：核心概念、公式、易错点、考点预测、记忆技巧。"""
    context, used = _gather_context(paths)
    lang = "中文" if language == "zh" else language
    system = "你是学习教练，输出 GitHub 风格 Markdown 学习指南，公式用 LaTeX（$...$ / $$...$$）。"
    user = (
        f"以下是我的学习笔记（{', '.join(used)}），请生成一份 {lang} 备考学习指南：\n\n"
        f"{context}\n\n"
        "结构要求：\n"
        "## 一页速览（本部分核心脉络，10 行以内）\n"
        "## 核心概念（逐条：定义 + 为什么重要）\n"
        "## 关键公式与方法（LaTeX 呈现，附使用条件）\n"
        "## 易错点与辨析\n"
        "## 考点预测（可能怎么考，怎么应对）\n"
        "## 记忆技巧\n"
        "## 自测清单（可勾选的检查项，用 - [ ] 列表）"
    )
    return await complete(provider_id, [{"role": "system", "content": system}, {"role": "user", "content": user}])


__all__ = [
    "generate_exam", "list_exams", "get_exam", "delete_exam",
    "submit_attempt", "list_attempts", "generate_study_guide",
]

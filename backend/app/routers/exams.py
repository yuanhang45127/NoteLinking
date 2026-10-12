"""考试备考路由：出题、试卷管理、作答判分、考点清单、备考目标、学习指南。"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional

from ..schemas import AttemptRequest, ExamGenerateRequest
from ..services import exam_service, goals_store
from ..services.llm_service import stream_llm
from .llm import sse_response

router = APIRouter(prefix="/api", tags=["exams"])


class ChecklistRequest(BaseModel):
    paths: List[str]
    language: str = "zh"
    provider: Optional[str] = None
    model: Optional[str] = None


class ChecklistToggle(BaseModel):
    item_id: str
    mastered: bool


@router.post("/exams/generate/stream")
async def stream_generate_exam(body: ExamGenerateRequest):
    """出卷流式：SSE 增量输出模型原始文本（JSON，作进度展示），
    结束时解析、校验、落盘，done 事件返回 exam_id。"""
    messages, used_titles = exam_service._exam_messages(
        body.paths, body.types, body.count, body.difficulty, body.language
    )

    async def gen():
        buf = []
        async for delta in stream_llm(body.provider or "", messages, body.model or ""):
            buf.append(delta)
            yield {"type": "delta", "text": delta}
        exam = exam_service._finalize_exam(
            "".join(buf), body.paths, used_titles, body.types,
            body.count, body.difficulty, body.language, body.title or "",
        )
        yield {"type": "done", "exam_id": exam["id"], "title": exam["title"],
               "count": len(exam["questions"])}

    return sse_response(gen())


@router.post("/exams/generate")
async def generate_exam(body: ExamGenerateRequest):
    """基于选定笔记让大模型出卷（mcq 选择 / short 简答 / flashcard 闪卡）。"""
    return await exam_service.generate_exam(
        paths=body.paths,
        types=body.types,
        count=body.count,
        difficulty=body.difficulty,
        language=body.language,
        title=body.title or "",
        provider_id=body.provider or "",
        model=body.model or "",
    )


@router.get("/exams")
def list_exams():
    return {"exams": exam_service.list_exams()}


# 注意：/exams/checklist 是静态路径，必须注册在 /exams/{exam_id} 之前，
# 否则 "checklist" 会被当成试卷 ID 捕获（404）。
@router.get("/exams/checklist")
def get_checklist(topic: str):
    doc = exam_service.get_checklist(topic)
    return {"checklist": doc}


@router.put("/exams/checklist")
def toggle_checklist(body: ChecklistToggle, topic: str):
    return exam_service.toggle_checklist_item(topic, body.item_id, body.mastered)


@router.get("/exams/{exam_id}")
def get_exam(exam_id: str, include_answers: bool = True):
    return exam_service.get_exam(exam_id, include_answers=include_answers)


@router.delete("/exams/{exam_id}")
def delete_exam(exam_id: str):
    exam_service.delete_exam(exam_id)
    return {"ok": True}


@router.post("/exams/{exam_id}/attempts")
async def submit_attempt(exam_id: str, body: AttemptRequest):
    """交卷：选择/简答判分（简答由大模型评阅），返回逐题结果与总分。"""
    return await exam_service.submit_attempt(
        exam_id, body.answers, body.provider or "", body.model or ""
    )


@router.get("/exams/{exam_id}/attempts")
def list_attempts(exam_id: str):
    return {"attempts": exam_service.list_attempts(exam_id)}


# ---------------------------------------------------------------- 考点清单
@router.post("/exams/checklist")
async def generate_checklist(body: ChecklistRequest):
    """基于勾选资料生成考点清单（按重要度排序）。"""
    return await exam_service.generate_checklist(
        body.paths, body.language, body.provider or "", body.model or ""
    )


@router.post("/exams/checklist/stream")
async def stream_generate_checklist(body: ChecklistRequest):
    """考点清单流式：SSE 增量输出模型原始文本（JSON，作进度展示），
    结束时解析、校验、落盘，done 事件返回完整清单文档。"""
    messages, used = exam_service._checklist_messages(body.paths, body.language)

    async def gen():
        buf = []
        async for delta in stream_llm(body.provider or "", messages, body.model or ""):
            buf.append(delta)
            yield {"type": "delta", "text": delta}
        doc = exam_service._finalize_checklist("".join(buf), body.paths, used)
        yield {"type": "done", "checklist": doc}

    return sse_response(gen())


# ---------------------------------------------------------------- 备考目标
class GoalIn(BaseModel):
    title: str
    date: str = ""
    topic: str = ""


class GoalUpdate(BaseModel):
    title: Optional[str] = None
    date: Optional[str] = None
    topic: Optional[str] = None


@router.get("/goals")
def list_goals():
    return {"goals": goals_store.list_goals()}


@router.post("/goals")
def add_goal(body: GoalIn):
    return goals_store.add_goal(body.title, body.date, body.topic)


@router.put("/goals/{goal_id}")
def update_goal(goal_id: str, body: GoalUpdate):
    return goals_store.update_goal(goal_id, body.model_dump(exclude_none=True))


@router.delete("/goals/{goal_id}")
def delete_goal(goal_id: str):
    goals_store.delete_goal(goal_id)
    return {"ok": True}

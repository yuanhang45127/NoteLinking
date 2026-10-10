"""考试备考路由：出题、试卷管理、作答判分、考点清单、备考目标、学习指南。"""
from fastapi import APIRouter
from pydantic import BaseModel
from typing import List, Optional

from ..schemas import AttemptRequest, ExamGenerateRequest
from ..services import exam_service, goals_store

router = APIRouter(prefix="/api", tags=["exams"])


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
class ChecklistRequest(BaseModel):
    paths: List[str]
    language: str = "zh"
    provider: Optional[str] = None
    model: Optional[str] = None


class ChecklistToggle(BaseModel):
    item_id: str
    mastered: bool


@router.post("/exams/checklist")
async def generate_checklist(body: ChecklistRequest):
    """基于勾选资料生成考点清单（按重要度排序）。"""
    return await exam_service.generate_checklist(
        body.paths, body.language, body.provider or "", body.model or ""
    )


@router.get("/exams/checklist")
def get_checklist(topic: str):
    doc = exam_service.get_checklist(topic)
    return {"checklist": doc}


@router.put("/exams/checklist")
def toggle_checklist(body: ChecklistToggle, topic: str):
    return exam_service.toggle_checklist_item(topic, body.item_id, body.mastered)


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

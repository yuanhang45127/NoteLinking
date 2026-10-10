"""考试备考路由：出题、试卷管理、作答判分、学习指南。"""
from fastapi import APIRouter

from ..schemas import AttemptRequest, ExamGenerateRequest
from ..services import exam_service

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

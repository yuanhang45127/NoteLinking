"""PDF 导入路由（基础实现：文本提取 → md 笔记）。"""
import shutil
import tempfile
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from ..services import pdf_service, vault

router = APIRouter(prefix="/api/import", tags=["import"])

MAX_PDF_SIZE = 50 * 1024 * 1024  # 50MB


@router.post("/pdf")
async def import_pdf(
    file: UploadFile = File(...),
    topic: str = Form(...),
    name: str = Form(""),
):
    if not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="请上传 .pdf 文件")
    vault.get_tree(topic)  # 校验主题存在（不存在则 404）
    data = await file.read()
    if len(data) > MAX_PDF_SIZE:
        raise HTTPException(status_code=413, detail="PDF 超过 50MB 限制")
    if not data[:5] == b"%PDF-":
        raise HTTPException(status_code=400, detail="文件不是有效的 PDF")
    return await pdf_service.import_pdf(data, file.filename or "import.pdf", topic, name)

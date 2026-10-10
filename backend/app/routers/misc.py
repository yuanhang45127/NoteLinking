"""导入导出路由：笔记库整体导出为 zip。"""
import datetime
import io
import zipfile

from fastapi import APIRouter
from fastapi.responses import Response

from ..config import get_vault_dir

router = APIRouter(prefix="/api/export", tags=["export"])


@router.get("/vault")
def export_vault():
    vault_dir = get_vault_dir()
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(vault_dir.rglob("*")):
            if p.is_file() and not any(part.startswith(".") for part in p.relative_to(vault_dir).parts):
                z.write(p, p.relative_to(vault_dir).as_posix())
    filename = f"notelink-vault-{datetime.date.today().isoformat()}.zip"
    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )

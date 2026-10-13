"""设置路由：模型服务商（支持当前所有主流接口）、高亮偏好、考试默认值。"""
from fastapi import APIRouter, HTTPException

from ..schemas import ActiveProviderIn, ExamSettingsIn, HighlightIn, ProviderIn, ProvidersIn
from ..services.llm_service import SUPPORTED_TYPES
from ..services.settings_store import (
    load_settings,
    mask_settings,
    merge_provider_secret,
    save_settings,
    update_settings,
)

router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def get_settings():
    s = load_settings()
    s["supported_types"] = list(SUPPORTED_TYPES)
    return mask_settings(s)


@router.put("/providers")
def put_providers(body: ProvidersIn):
    for p in body.providers:
        if p.type not in SUPPORTED_TYPES:
            raise HTTPException(status_code=400, detail=f"不支持的接口类型：{p.type}（可选 {', '.join(SUPPORTED_TYPES)}）")
        if not p.id.strip():
            raise HTTPException(status_code=400, detail="服务商 id 不能为空")
    s = load_settings()
    s["providers"] = merge_provider_secret(s.get("providers") or [], [p.model_dump() for p in body.providers])
    if s.get("active_provider") and s["active_provider"] not in {p["id"] for p in s["providers"]}:
        s["active_provider"] = s["providers"][0]["id"] if s["providers"] else ""
    if not s.get("active_provider") and s["providers"]:
        s["active_provider"] = s["providers"][0]["id"]
    save_settings(s)
    return mask_settings(s)


@router.put("/active")
def put_active(body: ActiveProviderIn):
    s = load_settings()
    ids = {p["id"] for p in s.get("providers") or []}
    if body.provider_id and body.provider_id not in ids:
        raise HTTPException(status_code=404, detail=f"服务商不存在：{body.provider_id}")
    s["active_provider"] = body.provider_id
    save_settings(s)
    return mask_settings(s)


@router.put("/highlight")
def put_highlight(body: HighlightIn):
    if body.style is not None and body.style not in ("background", "font"):
        raise HTTPException(status_code=400, detail="style 仅支持 background（背景高亮）或 font（字体高亮）")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    return mask_settings(update_settings("highlight", updates))


@router.put("/reader")
def put_reader(body: dict):
    allowed = {"selection_menu", "auto_concept", "context_scope"}
    updates = {k: v for k, v in (body or {}).items() if k in allowed}
    if not updates:
        raise HTTPException(status_code=400, detail=f"无有效字段，允许：{', '.join(sorted(allowed))}")
    return mask_settings(update_settings("reader", updates))


@router.put("/graph")
def put_graph(body: dict):
    allowed = {"default_filter", "show_missing"}
    updates = {k: v for k, v in (body or {}).items() if k in allowed}
    if not updates:
        raise HTTPException(status_code=400, detail=f"无有效字段，允许：{', '.join(sorted(allowed))}")
    return mask_settings(update_settings("graph", updates))


@router.put("/exam")
def put_exam(body: ExamSettingsIn):
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    return mask_settings(update_settings("exam", updates))


@router.put("/kimi-web")
def put_kimi_web(body: dict):
    allowed = {"enabled", "port"}
    updates = {k: v for k, v in (body or {}).items() if k in allowed}
    if not updates:
        raise HTTPException(status_code=400, detail=f"无有效字段，允许：{', '.join(sorted(allowed))}")
    if "port" in updates:
        try:
            port = int(updates["port"])
            if not (1 <= port <= 65535):
                raise ValueError
            updates["port"] = port
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="port 需为 1-65535 的整数")
    return mask_settings(update_settings("kimi_web", updates))

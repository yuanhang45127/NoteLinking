"""设置路由：模型服务商（支持当前所有主流接口）、高亮偏好、考试默认值、联网搜索、MCP 服务器。"""
import uuid

from fastapi import APIRouter, HTTPException

from ..schemas import ActiveProviderIn, ExamSettingsIn, HighlightIn, ProviderIn, ProvidersIn
from ..services import mcp_client
from ..services.llm_service import SUPPORTED_TYPES
from ..services.settings_store import (
    MASK,
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


@router.put("/web-search")
def put_web_search(body: dict):
    allowed = {"enabled", "provider", "api_key", "base_url", "max_results", "mcp_server", "mcp_tool"}
    updates = {k: v for k, v in (body or {}).items() if k in allowed}
    if not updates:
        raise HTTPException(status_code=400, detail=f"无有效字段，允许：{', '.join(sorted(allowed))}")
    if "max_results" in updates:
        try:
            updates["max_results"] = max(1, min(int(updates["max_results"]), 20))
        except (TypeError, ValueError):
            raise HTTPException(status_code=400, detail="max_results 需为 1-20 的整数")
    # 前端带回的可能是打码值/空串：沿用已保存的真实 key（与服务商列表一致的处理）
    if updates.get("api_key") in ("", MASK):
        updates["api_key"] = (load_settings().get("web_search") or {}).get("api_key", "")
    return mask_settings(update_settings("web_search", updates))


def _merge_mcp_env_secrets(incoming: dict, existing: dict) -> dict:
    """保存 MCP server 的 env：值为空或打码值时沿用已保存的真实值（与服务商列表一致）。"""
    old = existing.get("env") if isinstance(existing.get("env"), dict) else {}
    out = {}
    for k, v in (incoming.get("env") or {}).items():
        if v in ("", MASK):
            v = old.get(k, "")
        out[str(k)] = "" if v is None else str(v)
    return out


@router.put("/mcp-servers")
def put_mcp_servers(body: dict):
    """保存外部 MCP 服务器列表（stdio）：command 必填、id 唯一（缺省生成）。"""
    servers = (body or {}).get("mcp_servers") if isinstance(body, dict) else None
    if not isinstance(servers, list):
        raise HTTPException(status_code=400, detail='请求体应为 {"mcp_servers": [...]}')
    s = load_settings()
    old_by_id = {srv.get("id"): srv for srv in (s.get("mcp_servers") or [])
                 if isinstance(srv, dict)}
    cleaned, seen = [], set()
    for srv in servers:
        if not isinstance(srv, dict):
            raise HTTPException(status_code=400, detail="MCP server 配置格式不正确")
        command = str(srv.get("command") or "").strip()
        if not command:
            raise HTTPException(status_code=400, detail="每个 MCP server 都必须填写 command（启动命令）")
        sid = str(srv.get("id") or "").strip() or uuid.uuid4().hex[:8]
        if sid in seen:
            raise HTTPException(status_code=400, detail=f"MCP server id 重复：{sid}")
        seen.add(sid)
        args = srv.get("args") or []
        if isinstance(args, str):  # 容忍逗号分隔的一行
            args = [a.strip() for a in args.split(",") if a.strip()]
        entry = {
            "id": sid,
            "name": str(srv.get("name") or "").strip(),
            "command": command,
            "args": [str(a) for a in args],
            "env": _merge_mcp_env_secrets(srv, old_by_id.get(sid) or {}),
            "enabled": bool(srv.get("enabled", True)),
        }
        cleaned.append(entry)
    s["mcp_servers"] = cleaned
    save_settings(s)
    mcp_client.invalidate()
    return mask_settings(s)

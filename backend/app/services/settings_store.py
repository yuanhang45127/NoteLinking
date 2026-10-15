"""设置存储：data/settings.json（含服务商 API Key，目录已被 gitignore）。"""
import copy
import json
import threading
from typing import Any, Dict

from ..config import get_settings_file

_LOCK = threading.Lock()

DEFAULT_SETTINGS: Dict[str, Any] = {
    # 服务商列表，元素形如：
    # {"id": "deepseek", "type": "openai", "name": "DeepSeek",
    #  "base_url": "https://api.deepseek.com/v1", "api_key": "sk-...", "model": "deepseek-chat"}
    # type 支持：openai（OpenAI 及一切兼容接口：DeepSeek/Qwen/GLM/Kimi/OpenRouter/Ollama…）、
    #          anthropic、gemini
    "providers": [],
    "active_provider": "",
    # 阅读器默认高亮样式
    "highlight": {"color": "#fef08a", "style": "background"},
    # 阅读行为：划选菜单、「什么意思」自动建概念文档、携带上下文范围
    "reader": {"selection_menu": True, "auto_concept": True, "context_scope": "section"},
    # 图谱默认状态
    "graph": {"default_filter": "all", "show_missing": True},
    # 考试备考默认参数
    "exam": {
        "default_count": 10,
        "types": ["mcq", "short", "flashcard"],
        "difficulty": "medium",
    },
    # 侧边 AI 对话嵌入本机 Kimi Code Web（kimi web）：默认关闭（开启后登录者
    # 可获得本机 kimi web 访问，仅建议单人本地部署打开）
    "kimi_web": {"enabled": False, "port": 58627},
    # 外部 MCP 服务器（stdio）：元素形如
    # {"id": "a1b2c3d4", "name": "web search", "command": "npx",
    #  "args": ["-y", "some-search-mcp"], "env": {"API_KEY": "..."}, "enabled": true}
    # 供联网搜索 provider=mcp 与 AI 对话 mcp_tool 工具调用
    "mcp_servers": [],
    # 联网搜索：provider 支持 tavily / brave / serper / searxng / mcp；searxng 填 base_url，
    # mcp 填 mcp_server（服务器 id）与 mcp_tool（工具名），其余填 api_key
    "web_search": {"enabled": False, "provider": "tavily", "api_key": "", "base_url": "", "max_results": 8,
                   "mcp_server": "", "mcp_tool": ""},
    "language": "zh",
}


def load_settings() -> Dict[str, Any]:
    f = get_settings_file()
    data: Dict[str, Any] = {}
    if f.exists():
        try:
            data = json.loads(f.read_text(encoding="utf-8")) or {}
        except (json.JSONDecodeError, OSError):
            data = {}
    merged = copy.deepcopy(DEFAULT_SETTINGS)
    for k, v in data.items():
        if isinstance(v, dict) and isinstance(merged.get(k), dict):
            merged[k].update(v)
        else:
            merged[k] = v
    return merged


def save_settings(settings: Dict[str, Any]) -> None:
    f = get_settings_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(settings, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(f)


def update_settings(section: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """合并更新某个子配置（highlight / exam），或顶层键。"""
    with _LOCK:
        s = load_settings()
        if section:
            cur = s.get(section)
            if not isinstance(cur, dict):
                cur = {}
            cur.update(updates)
            s[section] = cur
        else:
            s.update(updates)
        save_settings(s)
        return s


MASK = "••••••"


def mask_settings(s: Dict[str, Any]) -> Dict[str, Any]:
    """返回给前端的设置：API Key 打码。"""
    out = copy.deepcopy(s)
    for p in out.get("providers", []):
        key = p.get("api_key") or ""
        p["api_key"] = MASK if key else ""
        p["has_key"] = bool(key)
    ws = out.get("web_search")
    if isinstance(ws, dict):
        key = ws.get("api_key") or ""
        ws["api_key"] = MASK if key else ""
        ws["has_key"] = bool(key)
    for srv in out.get("mcp_servers", []):
        env = srv.get("env")
        if isinstance(env, dict):
            # env 里键名含 KEY / TOKEN 的视为密钥，值打码（保存时按 id 沿用旧值）
            srv["env"] = {k: (MASK if ("KEY" in k.upper() or "TOKEN" in k.upper()) and v else v)
                          for k, v in env.items()}
    return out


def merge_provider_secret(existing: list, incoming: list) -> list:
    """保存服务商列表时：api_key 为空或为打码值则沿用旧值。"""
    old_by_id = {p.get("id"): p for p in existing}
    result = []
    for p in incoming:
        p = dict(p)
        key = p.get("api_key") or ""
        old = old_by_id.get(p.get("id"), {})
        if not key or key == MASK:
            p["api_key"] = old.get("api_key", "")
        result.append(p)
    return result

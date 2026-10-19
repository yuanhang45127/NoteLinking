"""「调用过程」事件辅助：把每一次大模型调用、工具调用、步骤都以事件产出，
供 SSE 客户端实时展示（对齐 DeepSeek Harness 式的过程视图）。

事件协议（与既有 delta/done/error 事件共存，向后兼容）：
    {"type":"llm_start","seq":n,"purpose":..,"provider":..,"model":..,"prompt_chars":n}
    {"type":"delta","text":"..."}
    {"type":"llm_done","seq":n,"chars":n,"elapsed":1.23}
    {"type":"tool","name":..,"args":{..},"status":"start"}
    {"type":"tool","name":..,"args":{..},"status":"done","ok":true,"summary":..,"result":..}
    {"type":"step","name":..,"status":"start"|"done","label":..,"detail"?:..}

事件里以 `_` 开头的键是流程间传值的内部数据，sse_response 序列化前剔除。

调用日志：事件在 SSE 边界（routers/llm.py 的 sse_response，每条 yield 前）
与后台任务汇点（services/ai_task_store.append_event）旁路落盘，
见 services/call_log_store.py——在这里记录会漏掉流程直接 yield 的事件
（如 chat_agent 的 tool、gen_flows 的 note_start 等），故本模块只管会话作用域。
"""
import time
from contextvars import ContextVar
from typing import AsyncIterator, Dict, List, Optional

from . import call_log_store, websearch_service
from .llm_service import get_provider, stream_llm

RESULT_PREVIEW_CHARS = 400    # tool done 事件里附带的结果预览长度

# 当前调用日志会话 id（set_session 开启 / clear_session 结束并落盘）；
# 每请求运行在独立 asyncio 任务里，天然隔离。
_current_session: ContextVar[Optional[str]] = ContextVar("nl_call_session", default=None)


async def set_session(flow: str) -> str:
    """开启调用日志会话（SSE 入口在流式开始时调用），返回会话 id。"""
    sid = await call_log_store.start_session(flow)
    _current_session.set(sid)
    return sid


async def clear_session() -> None:
    """结束并落盘当前调用日志会话，清理上下文标记（SSE 流结束时调用）。"""
    sid = _current_session.get()
    _current_session.set(None)
    if sid:
        try:
            await call_log_store.end_session(sid)
        except Exception:  # noqa: BLE001 — 收尾落盘失败不影响响应
            pass


def call_desc(provider_id: str, model: str) -> Dict:
    """一次模型调用的展示信息（服务商名 + 模型名）。"""
    try:
        p = get_provider(provider_id)
        return {"provider": p.get("name") or p.get("id") or "",
                "model": model or p.get("model") or ""}
    except Exception:  # noqa: BLE001 — 未配置服务商时也要能展示
        return {"provider": provider_id, "model": model}


async def llm_call(provider_id: str, messages: List[Dict], model: str = "",
                   temperature: Optional[float] = None,
                   purpose: str = "", seq: int = 1) -> AsyncIterator[Dict]:
    """包一次模型调用：llm_start → delta* → llm_done。"""
    desc = call_desc(provider_id, model)
    yield {
        "type": "llm_start", "seq": seq, "purpose": purpose,
        "provider": desc["provider"], "model": desc["model"],
        "prompt_chars": sum(len(str(m.get("content") or "")) for m in messages),
    }
    start = time.monotonic()
    chars = 0
    async for delta in stream_llm(provider_id, messages, model, temperature):
        chars += len(delta)
        yield {"type": "delta", "text": delta}
    yield {"type": "llm_done", "seq": seq, "chars": chars,
           "elapsed": round(time.monotonic() - start, 2)}


async def web_context_step(query: str, use_web: bool, max_results: int = 6) -> AsyncIterator[Dict]:
    """条件联网搜索步骤：use_web 且已启用才执行，失败不影响后续生成。

    done 事件带 _results（结果列表）与 _block（注入用文本块），由调用方取用。
    """
    if not use_web or not query.strip() or not websearch_service.is_enabled():
        return
    args = {"q": query}
    yield {"type": "tool", "name": "web_search", "args": args, "status": "start"}
    try:
        results, block = await websearch_service.search_and_block(query, max_results)
    except Exception as e:  # noqa: BLE001 — 搜索失败降级为无联网上下文
        yield {"type": "tool", "name": "web_search", "args": args, "status": "done",
               "ok": False, "summary": f"搜索失败：{e}", "result": ""}
        return
    yield {"type": "tool", "name": "web_search", "args": args, "status": "done",
           "ok": True, "summary": f"命中 {len(results)} 条",
           "result": (block or "")[:RESULT_PREVIEW_CHARS],
           "_results": results, "_block": block or ""}


def take_payload(ev: Dict) -> Dict:
    """取事件里 `_` 开头的内部传值数据（没有则 {}）。"""
    return {k: v for k, v in ev.items() if k.startswith("_")}


def strip_internal(ev: Dict) -> Dict:
    """剔除事件里 `_` 开头的内部键（SSE 序列化前调用）。"""
    return {k: v for k, v in ev.items() if not k.startswith("_")}


def step(name: str, status: str, label: str, detail: str = "") -> Dict:
    ev = {"type": "step", "name": name, "status": status, "label": label}
    if detail:
        ev["detail"] = detail
    return ev

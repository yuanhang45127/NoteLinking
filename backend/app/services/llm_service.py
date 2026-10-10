"""大模型服务：统一封装 OpenAI 兼容接口 / Anthropic / Gemini 三类协议，
覆盖当前主流大模型（OpenAI、DeepSeek、Qwen、GLM、Kimi、OpenRouter、
Ollama / LM Studio 本地模型、Claude、Gemini……）。

所有生成接口均以异步生成器逐段产出文本，供 SSE 流式接口使用；
complete() 则聚合为完整文本。
"""
import json
from typing import AsyncIterator, Dict, List, Optional

import httpx

from ..utils import sanitize_filename  # noqa: F401  (re-export 便利)
from .settings_store import load_settings

TIMEOUT = httpx.Timeout(connect=15.0, read=600.0, write=60.0, pool=15.0)

DEFAULT_BASE_URLS = {
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com",
    "gemini": "https://generativelanguage.googleapis.com",
}

SUPPORTED_TYPES = ("openai", "anthropic", "gemini")


class LLMError(Exception):
    """模型调用失败（配置缺失、HTTP 错误、响应不可解析等）。"""


def get_provider(provider_id: str = "") -> Dict:
    """取指定服务商配置；为空则取当前激活服务商。"""
    s = load_settings()
    providers = s.get("providers") or []
    pid = provider_id or s.get("active_provider") or ""
    if providers and not pid:
        pid = providers[0].get("id", "")
    for p in providers:
        if p.get("id") == pid:
            return p
    if not providers:
        raise LLMError("尚未配置模型服务商，请先在设置中添加（支持 OpenAI 兼容 / Anthropic / Gemini）")
    raise LLMError(f"未找到模型服务商：{pid}，请检查设置")


def _resolve(provider: Dict, model: str) -> tuple:
    ptype = (provider.get("type") or "openai").lower()
    if ptype not in SUPPORTED_TYPES:
        raise LLMError(f"不支持的接口类型：{ptype}（可选 {', '.join(SUPPORTED_TYPES)}）")
    base = (provider.get("base_url") or DEFAULT_BASE_URLS[ptype]).rstrip("/")
    m = model or provider.get("model") or ""
    if not m:
        raise LLMError("未指定模型名称（model）")
    key = provider.get("api_key") or ""
    return ptype, base, m, key


async def stream_llm(
    provider_id: str,
    messages: List[Dict[str, str]],
    model: str = "",
    temperature: Optional[float] = None,
) -> AsyncIterator[str]:
    """逐段产出回答文本。messages: [{role: system|user|assistant, content}]"""
    provider = get_provider(provider_id)
    ptype, base, m, key = _resolve(provider, model)
    if ptype == "openai":
        gen = _stream_openai(base, key, m, messages, temperature)
    elif ptype == "anthropic":
        gen = _stream_anthropic(base, key, m, messages, temperature)
    else:
        gen = _stream_gemini(base, key, m, messages, temperature)
    async for delta in gen:
        yield delta


async def complete(
    provider_id: str,
    messages: List[Dict[str, str]],
    model: str = "",
    temperature: Optional[float] = None,
) -> str:
    parts = []
    async for delta in stream_llm(provider_id, messages, model, temperature):
        parts.append(delta)
    return "".join(parts)


# ---------------------------------------------------------------- openai 兼容
async def _stream_openai(base, key, model, messages, temperature) -> AsyncIterator[str]:
    url = f"{base}/chat/completions"
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    body: Dict = {"model": model, "messages": messages, "stream": True}
    if temperature is not None:
        body["temperature"] = temperature
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        async with client.stream("POST", url, headers=headers, json=body) as resp:
            if resp.status_code >= 400:
                raw = (await resp.aread()).decode("utf-8", "replace")
                raise LLMError(f"OpenAI 兼容接口 HTTP {resp.status_code}: {raw[:500]}")
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    obj = json.loads(data)
                except json.JSONDecodeError:
                    continue
                choices = obj.get("choices") or []
                if choices:
                    delta = (choices[0].get("delta") or {}).get("content")
                    if delta:
                        yield delta


# ---------------------------------------------------------------- anthropic
async def _stream_anthropic(base, key, model, messages, temperature) -> AsyncIterator[str]:
    if not key:
        raise LLMError("Anthropic 服务商缺少 API Key")
    url = f"{base}/v1/messages"
    system = "\n".join(m["content"] for m in messages if m.get("role") == "system")
    msgs = [
        {"role": m["role"], "content": m["content"]}
        for m in messages
        if m.get("role") in ("user", "assistant")
    ]
    body: Dict = {"model": model, "max_tokens": 8192, "messages": msgs, "stream": True}
    if system:
        body["system"] = system
    if temperature is not None:
        body["temperature"] = temperature
    headers = {"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"}
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        async with client.stream("POST", url, headers=headers, json=body) as resp:
            if resp.status_code >= 400:
                raw = (await resp.aread()).decode("utf-8", "replace")
                raise LLMError(f"Anthropic 接口 HTTP {resp.status_code}: {raw[:500]}")
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                try:
                    obj = json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue
                if obj.get("type") == "content_block_delta":
                    text = (obj.get("delta") or {}).get("text")
                    if text:
                        yield text


# ---------------------------------------------------------------- gemini
async def _stream_gemini(base, key, model, messages, temperature) -> AsyncIterator[str]:
    if not key:
        raise LLMError("Gemini 服务商缺少 API Key")
    url = f"{base}/v1beta/models/{model}:streamGenerateContent?alt=sse"
    system = "\n".join(m["content"] for m in messages if m.get("role") == "system")
    contents = [
        {
            "role": "model" if m.get("role") == "assistant" else "user",
            "parts": [{"text": m.get("content", "")}],
        }
        for m in messages
        if m.get("role") in ("user", "assistant")
    ]
    body: Dict = {"contents": contents}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    if temperature is not None:
        body["generationConfig"] = {"temperature": temperature}
    headers = {"x-goog-api-key": key, "content-type": "application/json"}
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        async with client.stream("POST", url, headers=headers, json=body) as resp:
            if resp.status_code >= 400:
                raw = (await resp.aread()).decode("utf-8", "replace")
                raise LLMError(f"Gemini 接口 HTTP {resp.status_code}: {raw[:500]}")
            async for line in resp.aiter_lines():
                if not line.startswith("data:"):
                    continue
                try:
                    obj = json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    continue
                for cand in obj.get("candidates") or []:
                    for part in ((cand.get("content") or {}).get("parts")) or []:
                        text = part.get("text")
                        if text:
                            yield text


# ---------------------------------------------------------------- JSON 解析
def extract_json(text: str):
    """从模型回复中稳健地取 JSON（容忍 ```json 代码块与前后闲话）。"""
    t = text.strip()
    import re

    fence = re.search(r"```(?:json)?\s*(.*?)```", t, re.DOTALL)
    if fence:
        t = fence.group(1).strip()
    s, e = t.find("{"), t.rfind("}")
    if s == -1 or e == -1 or e <= s:
        raise LLMError("模型未返回 JSON，请重试或更换模型")
    try:
        return json.loads(t[s:e + 1])
    except json.JSONDecodeError as exc:
        raise LLMError(f"模型返回的 JSON 无法解析：{exc}") from exc

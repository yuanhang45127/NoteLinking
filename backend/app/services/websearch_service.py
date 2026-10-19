"""联网搜索服务：Tavily / Brave / Serper / DeepSeek / SearXNG / MCP 六类服务商，以及网页正文抓取。

搜索结果统一为 {"provider": ..., "results": [{"title", "url", "snippet"}]}；
web_context_block 把结果格式化为可注入 prompt 的资料块。抓取失败、未配置等
统一抛 WebSearchError，由路由层转为 502。
"""
import json
import re
from typing import Dict, List, Optional, Tuple
from urllib.parse import urlparse

import httpx
from bs4 import BeautifulSoup

from . import mcp_client
from .settings_store import load_settings

SEARCH_TIMEOUT = 30.0
FETCH_TIMEOUT = 20.0
MAX_FETCH_BYTES = 2 * 1024 * 1024   # 只读前 2MB，避免抓取超大页面
MAX_FETCH_TEXT = 8000               # 正文截断上限
_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
_BLOCK_HEADER = "\n\n以下是联网搜索到的最新资料（搜索结果，可能包含比你的训练数据更新的信息）：\n\n"
_DROP_TAGS = ("script", "style", "nav", "header", "footer", "aside", "form")
_TEXT_TAGS = ("p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote")


class WebSearchError(Exception):
    """联网搜索/抓取失败（未启用、缺配置、HTTP 错误、响应不可解析等）。"""


def _cfg() -> Dict:
    return load_settings().get("web_search") or {}


def is_enabled() -> bool:
    """是否已在设置中启用联网搜索（AI 功能注入前判断，避免未配置时报错中断生成）。"""
    return bool(_cfg().get("enabled"))


def _norm(title, url, snippet) -> Optional[Dict]:
    """统一各服务商的字段名；没有 url 的条目丢弃。"""
    url = str(url or "").strip()
    if not url:
        return None
    return {"title": str(title or "").strip() or url, "url": url, "snippet": str(snippet or "").strip()}


def _extract_json_block(text: str) -> Optional[str]:
    """提取文本中第一个完整的 JSON 对象/数组（括号配平，容忍字符串内的括号）。"""
    start = next((i for i, ch in enumerate(text) if ch in "{["), -1)
    if start < 0:
        return None
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch in "{[":
            depth += 1
        elif ch in "}]":
            depth -= 1
            if depth == 0:
                return text[start: i + 1]
    return None


def _parse_mcp_results(text: str) -> Optional[List[Dict]]:
    """从 MCP 工具返回的文本提取结果列表：整体 JSON、或文本中第一个 {...}/[...]。

    对象里依次找 results / organic / data 列表字段；文本直接是列表也行。
    完全解析不出返回 None。
    """
    text = (text or "").strip()
    if not text:
        return None
    data = None
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        block = _extract_json_block(text)
        if block:
            try:
                data = json.loads(block)
            except (json.JSONDecodeError, ValueError):
                data = None
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = next((data[k] for k in ("results", "organic", "data")
                      if isinstance(data.get(k), list)), None)
    else:
        items = None
    if items is None:
        return None
    return [x for x in items if isinstance(x, dict)]


def _mcp_search_text(query: str, cfg: Dict, n: int) -> str:
    """调用 MCP 搜索工具，返回结果文本（isError 或未配置抛 WebSearchError）。"""
    server = str(cfg.get("mcp_server") or "").strip()
    tool = str(cfg.get("mcp_tool") or "").strip()
    if not server or not tool:
        raise WebSearchError(
            "未选择 MCP 搜索工具，请先在「设置 → 联网搜索」选择 MCP 服务器与工具")
    result = mcp_client.call_tool(server, tool, {"query": query, "max_results": n})
    text = "\n".join(c.get("text", "") for c in result.get("content") or []
                     if isinstance(c, dict))
    if result.get("isError"):
        raise WebSearchError(f"MCP 搜索工具执行失败：{text[:200] or '（无返回）'}")
    return text


async def _post_json(url: str, payload: Dict, headers: Optional[Dict] = None) -> Dict:
    async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT) as client:
        resp = await client.post(url, json=payload, headers=headers or {})
        return await _json_or_raise(resp)


async def _get_json(url: str, params: Dict, headers: Optional[Dict] = None) -> Dict:
    async with httpx.AsyncClient(timeout=SEARCH_TIMEOUT) as client:
        resp = await client.get(url, params=params, headers=headers or {})
        return await _json_or_raise(resp)


async def _json_or_raise(resp) -> Dict:
    if resp.status_code >= 400:
        raise WebSearchError(f"搜索失败（HTTP {resp.status_code}）：{(resp.text or '')[:200]}")
    try:
        data = resp.json()
    except ValueError:
        raise WebSearchError("搜索响应不是合法 JSON")
    return data if isinstance(data, dict) else {}


async def search(query: str, max_results: Optional[int] = None) -> Dict:
    """联网搜索，统一返回 {"provider", "results"}；结果为空时 results 为 []。"""
    cfg = _cfg()
    if not cfg.get("enabled"):
        raise WebSearchError("请先在「设置 → 联网搜索」启用并配置搜索服务")
    q = (query or "").strip()
    if not q:
        raise WebSearchError("搜索关键词不能为空")
    provider = str(cfg.get("provider") or "").strip().lower()
    try:
        n = int(max_results or cfg.get("max_results") or 8)
    except (TypeError, ValueError):
        n = 8
    n = max(1, min(n, 20))
    key = str(cfg.get("api_key") or "").strip()

    if provider == "tavily":
        if not key:
            raise WebSearchError("未配置 Tavily API Key，请先在「设置 → 联网搜索」填写")
        data = await _post_json(
            "https://api.tavily.com/search",
            {"api_key": key, "query": q, "max_results": n, "search_depth": "basic"},
        )
        raw = data.get("results") or []
        results = [_norm(r.get("title"), r.get("url"), r.get("content")) for r in raw if isinstance(r, dict)]
    elif provider == "brave":
        if not key:
            raise WebSearchError("未配置 Brave API Key，请先在「设置 → 联网搜索」填写")
        data = await _get_json(
            "https://api.search.brave.com/res/v1/web/search",
            {"q": q, "count": n},
            {"X-Subscription-Token": key, "Accept": "application/json"},
        )
        raw = (data.get("web") or {}).get("results") or []
        results = [_norm(r.get("title"), r.get("url"), r.get("description")) for r in raw if isinstance(r, dict)]
    elif provider == "serper":
        if not key:
            raise WebSearchError("未配置 Serper API Key，请先在「设置 → 联网搜索」填写")
        data = await _post_json(
            "https://google.serper.dev/search", {"q": q, "num": n}, {"X-API-KEY": key}
        )
        raw = data.get("organic") or []
        results = [_norm(r.get("title"), r.get("link"), r.get("snippet")) for r in raw if isinstance(r, dict)]
    elif provider == "deepseek":
        if not key:
            raise WebSearchError("未配置 DeepSeek API Key，请先在「设置 → 联网搜索」填写")
        data = await _post_json(
            "https://api.deepseek.com/v1/tools/search",
            {"query": q, "count": n},
            {"Authorization": f"Bearer {key}"},
        )
        raw = data.get("results") or []
        # DeepSeek 每条含 snippet(短摘要)/summary(长摘要)，need_content=True 才有正文；这里取长摘要优先
        results = [_norm(r.get("title"), r.get("url"),
                         r.get("summary") or r.get("snippet") or r.get("content"))
                   for r in raw if isinstance(r, dict)]
    elif provider == "searxng":
        base = str(cfg.get("base_url") or "").strip().rstrip("/")
        if not base:
            raise WebSearchError("未配置 SearXNG 实例地址（Base URL），请先在「设置 → 联网搜索」填写")
        data = await _get_json(f"{base}/search", {"q": q, "format": "json"})
        raw = data.get("results") or []
        results = [_norm(r.get("title"), r.get("url"), r.get("content")) for r in raw if isinstance(r, dict)]
    elif provider == "mcp":
        text = _mcp_search_text(q, cfg, n)
        raw = _parse_mcp_results(text)
        if raw is None:
            raise WebSearchError(f"MCP 搜索工具返回的结果无法解析：{text[:200]}")
        results = [
            _norm(r.get("title") or r.get("headline") or r.get("name"),
                  r.get("url") or r.get("link"),
                  r.get("snippet") or r.get("description") or r.get("content") or r.get("summary"))
            for r in raw
        ]
    else:
        raise WebSearchError(f"不支持的搜索服务商：{provider or '（未选择）'}")
    return {"provider": provider, "results": [r for r in results if r]}


def _format_block(results: List[Dict]) -> str:
    if not results:
        return ""
    parts = [_BLOCK_HEADER]
    for r in results:
        parts.append(f"### {r.get('title') or r.get('url')}\n{r.get('snippet') or ''}\n来源：{r.get('url')}\n\n")
    return "".join(parts)


async def search_and_block(query: str, max_results: int = 6) -> Tuple[List[Dict], str]:
    """搜索并返回 (结果列表, prompt 注入块)；落盘回填参考链接时用结果列表。"""
    results = (await search(query, max_results)).get("results") or []
    return results, _format_block(results)


async def web_context_block(query: str, max_results: int = 6) -> str:
    """搜索并格式化为 prompt 注入块；无结果返回空串。"""
    _, block = await search_and_block(query, max_results)
    return block


async def maybe_web_context(query: str, use_web: bool, max_results: int = 6) -> str:
    """use_web 且已启用 → 注入块，否则空串。"""
    if not use_web or not is_enabled():
        return ""
    return await web_context_block(query, max_results)


def _collapse_ws(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip()


def _extract_text(soup: BeautifulSoup) -> str:
    """删掉脚本/样式/导航等噪声后，按段落标签收集正文，折叠空白、段间空行。"""
    for tag in soup(_DROP_TAGS):
        tag.decompose()
    for br in soup.find_all("br"):
        br.replace_with("\n")
    parts: List[str] = []
    for el in soup.find_all(_TEXT_TAGS):
        if el.find_parent(_TEXT_TAGS) is not None:
            continue  # 嵌套块（如 blockquote 内的 p）由最外层收集，避免重复
        for line in el.get_text().split("\n"):
            t = _collapse_ws(line)
            if t:
                parts.append(t)
    return "\n\n".join(parts)[:MAX_FETCH_TEXT]


async def fetch_webpage(url: str) -> dict:
    """抓取网页正文：{"title", "url", "text"}；非 HTML / 提取不到正文抛 WebSearchError。"""
    target = (url or "").strip()
    if not target:
        raise WebSearchError("链接地址不能为空")
    if urlparse(target).scheme.lower() not in ("http", "https"):
        raise WebSearchError(f"仅支持抓取 http/https 网页：{target}")
    async with httpx.AsyncClient(timeout=FETCH_TIMEOUT) as client:
        resp = await client.get(target, headers={"User-Agent": _USER_AGENT}, follow_redirects=True)
    if resp.status_code >= 400:
        raise WebSearchError(f"抓取失败（HTTP {resp.status_code}）：{(resp.text or '')[:200]}")
    if "text/html" not in (resp.headers.get("content-type") or "").lower():
        raise WebSearchError("仅支持抓取 HTML 网页")
    raw = b""
    async for chunk in resp.aiter_bytes():
        raw += chunk
        if len(raw) >= MAX_FETCH_BYTES:
            raw = raw[:MAX_FETCH_BYTES]
            break
    soup = BeautifulSoup(raw.decode("utf-8", "replace"), "html.parser")
    title = soup.title.string.strip() if soup.title and soup.title.string else ""
    text = _extract_text(soup)
    if len(text) < 50:
        raise WebSearchError("未能从页面提取到正文")
    return {"title": title or target, "url": str(resp.url), "text": text}

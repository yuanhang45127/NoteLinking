"""联网搜索、网页抓取、笔记参考链接与 use_web 注入测试（mock 网络与模型，不联网）。"""
import asyncio
import json
import types

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.routers import llm as llm_router
from app.services import chat_agent, vault, websearch_service
from app.services.settings_store import load_settings, update_settings


@pytest.fixture()
def client(data_dir):
    with TestClient(app) as c:
        yield c


def _sse_events(text: str) -> list:
    out = []
    for line in text.splitlines():
        if line.startswith("data: "):
            out.append(json.loads(line[6:]))
    return out


def _enable_web(provider="tavily", **kw):
    update_settings("web_search", {"enabled": True, "provider": provider, "api_key": "k-test", **kw})


# ---------------------------------------------------------------- 假 httpx
class _FakeResponse:
    def __init__(self, status=200, payload=None, text="", headers=None, url="https://example.com/", content=b""):
        self.status_code = status
        self._payload = payload
        self.text = text
        self.headers = headers or {}
        self.url = url
        self._content = content

    def json(self):
        if self._payload is None:
            raise ValueError("not json")
        return self._payload

    async def aiter_bytes(self):
        for i in range(0, len(self._content), 512):
            yield self._content[i:i + 512]


def _patch_httpx(monkeypatch, response):
    """把 websearch_service 内部用的 httpx 换成假 client，返回记录调用的 dict。"""
    calls = {}

    class FakeClient:
        def __init__(self, *args, **kwargs):
            calls["init"] = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json=None, headers=None):
            calls["post"] = {"url": url, "json": json, "headers": headers}
            return response

        async def get(self, url, params=None, headers=None, follow_redirects=False, **kw):
            calls["get"] = {"url": url, "params": params, "headers": headers, "follow_redirects": follow_redirects}
            return response

    monkeypatch.setattr(websearch_service, "httpx", types.SimpleNamespace(AsyncClient=FakeClient))
    return calls


# ---------------------------------------------------------------- 搜索：四类服务商
def test_tavily_search(data_dir, monkeypatch):
    _enable_web("tavily", api_key="tvly-key")
    resp = _FakeResponse(payload={"results": [
        {"title": "特征值", "url": "https://a.com/1", "content": "特征值是伸缩倍数"},
        {"title": "", "url": "", "content": "没有链接的条目"},
    ]})
    calls = _patch_httpx(monkeypatch, resp)
    out = asyncio.run(websearch_service.search("特征值", 3))
    assert out["provider"] == "tavily"
    assert out["results"] == [{"title": "特征值", "url": "https://a.com/1", "snippet": "特征值是伸缩倍数"}]
    assert calls["post"]["url"] == "https://api.tavily.com/search"
    body = calls["post"]["json"]
    assert body["api_key"] == "tvly-key" and body["query"] == "特征值"
    assert body["max_results"] == 3 and body["search_depth"] == "basic"


def test_brave_search(data_dir, monkeypatch):
    _enable_web("brave")
    resp = _FakeResponse(payload={"web": {"results": [
        {"title": "B", "url": "https://b.com", "description": " brave 摘要"},
    ]}})
    calls = _patch_httpx(monkeypatch, resp)
    out = asyncio.run(websearch_service.search("q"))
    assert calls["get"]["url"] == "https://api.search.brave.com/res/v1/web/search"
    assert calls["get"]["params"] == {"q": "q", "count": 8}  # 缺省取设置里的 max_results
    assert calls["get"]["headers"]["X-Subscription-Token"] == "k-test"
    assert out["results"] == [{"title": "B", "url": "https://b.com", "snippet": "brave 摘要"}]


def test_serper_search(data_dir, monkeypatch):
    _enable_web("serper")
    resp = _FakeResponse(payload={"organic": [
        {"title": "S", "link": "https://s.com", "snippet": "serper 摘要"},
    ]})
    calls = _patch_httpx(monkeypatch, resp)
    out = asyncio.run(websearch_service.search("q", 2))
    assert calls["post"]["url"] == "https://google.serper.dev/search"
    assert calls["post"]["headers"]["X-API-KEY"] == "k-test"
    assert calls["post"]["json"] == {"q": "q", "num": 2}
    assert out["results"][0]["url"] == "https://s.com"  # link → url


def test_searxng_search(data_dir, monkeypatch):
    _enable_web("searxng", base_url="https://searx.example/")
    resp = _FakeResponse(payload={"results": [
        {"title": "X", "url": "https://x.com", "content": "searxng 摘要"},
    ]})
    calls = _patch_httpx(monkeypatch, resp)
    out = asyncio.run(websearch_service.search("q"))
    assert calls["get"]["url"] == "https://searx.example/search"  # base_url 末尾斜杠去掉
    assert calls["get"]["params"] == {"q": "q", "format": "json"}
    assert out["results"][0]["snippet"] == "searxng 摘要"


def test_search_disabled(data_dir):
    with pytest.raises(websearch_service.WebSearchError) as e:
        asyncio.run(websearch_service.search("q"))
    assert "启用" in str(e.value)


def test_missing_key_or_base_url(data_dir):
    _enable_web("tavily", api_key="")
    with pytest.raises(websearch_service.WebSearchError) as e:
        asyncio.run(websearch_service.search("q"))
    assert "API Key" in str(e.value)

    update_settings("web_search", {"provider": "searxng", "base_url": ""})
    with pytest.raises(websearch_service.WebSearchError) as e:
        asyncio.run(websearch_service.search("q"))
    assert "Base URL" in str(e.value)


def test_unsupported_provider(data_dir):
    _enable_web("someprovider")
    with pytest.raises(websearch_service.WebSearchError) as e:
        asyncio.run(websearch_service.search("q"))
    assert "不支持" in str(e.value)


def test_empty_results_and_http_error(data_dir, monkeypatch):
    _enable_web("tavily")
    _patch_httpx(monkeypatch, _FakeResponse(payload={"results": []}))
    assert asyncio.run(websearch_service.search("q")) == {"provider": "tavily", "results": []}

    _patch_httpx(monkeypatch, _FakeResponse(status=401, text="unauthorized"))
    with pytest.raises(websearch_service.WebSearchError) as e:
        asyncio.run(websearch_service.search("q"))
    assert "HTTP 401" in str(e.value) and "unauthorized" in str(e.value)


def test_web_context_block(data_dir, monkeypatch):
    _enable_web("tavily")
    _patch_httpx(monkeypatch, _FakeResponse(payload={"results": [
        {"title": "T1", "url": "https://a.com", "content": "摘要一"},
    ]}))
    block = asyncio.run(websearch_service.web_context_block("q"))
    assert block.startswith("\n\n以下是联网搜索到的最新资料")
    assert "### T1" in block and "摘要一" in block and "来源：https://a.com" in block

    # maybe_web_context：use_web=False 或未启用 → 空串
    assert asyncio.run(websearch_service.maybe_web_context("q", False)) == ""
    update_settings("web_search", {"enabled": False})
    assert asyncio.run(websearch_service.maybe_web_context("q", True)) == ""


# ---------------------------------------------------------------- 网页抓取
PAGE = """<!doctype html><html><head><title>测试页面</title></head>
<body>
<nav>导航不要</nav>
<script>var secret = "SCRIPT_CONTENT";</script>
<h1>大标题</h1>
<p>第一段：特征值是矩阵的伸缩倍数。</p>
<p>第二段：同一段<br>换行后的内容。</p>
<ul><li>列表项一</li><li>列表项二</li></ul>
<blockquote>引用块内容</blockquote>
<footer>页脚不要</footer>
</body></html>"""


def test_fetch_webpage(data_dir, monkeypatch):
    resp = _FakeResponse(headers={"content-type": "text/html; charset=utf-8"},
                         url="https://example.com/final", content=PAGE.encode("utf-8"))
    calls = _patch_httpx(monkeypatch, resp)
    page = asyncio.run(websearch_service.fetch_webpage("https://example.com/page"))
    assert page["title"] == "测试页面"
    assert page["url"] == "https://example.com/final"  # 跟随重定向后的最终地址
    text = page["text"]
    assert "特征值是矩阵的伸缩倍数" in text
    assert "SCRIPT_CONTENT" not in text  # script 内容剔除
    assert "导航不要" not in text and "页脚不要" not in text
    assert "大标题" in text and "列表项一" in text and "引用块内容" in text
    assert "换行后的内容" in text  # br 后的文本仍提取
    assert "Chrome/120" in calls["get"]["headers"]["User-Agent"]
    assert calls["get"]["follow_redirects"] is True


def test_fetch_webpage_truncated(data_dir, monkeypatch):
    html = "<html><head><title>长页面</title></head><body><p>" + "长" * 20000 + "</p></body></html>"
    _patch_httpx(monkeypatch, _FakeResponse(headers={"content-type": "text/html"},
                                            content=html.encode("utf-8")))
    page = asyncio.run(websearch_service.fetch_webpage("https://example.com/long"))
    assert len(page["text"]) == 8000


def test_fetch_webpage_errors(data_dir, monkeypatch):
    with pytest.raises(websearch_service.WebSearchError):
        asyncio.run(websearch_service.fetch_webpage("ftp://example.com/x"))

    _patch_httpx(monkeypatch, _FakeResponse(status=404, text="not found"))
    with pytest.raises(websearch_service.WebSearchError) as e:
        asyncio.run(websearch_service.fetch_webpage("https://example.com/missing"))
    assert "HTTP 404" in str(e.value)

    _patch_httpx(monkeypatch, _FakeResponse(headers={"content-type": "application/json"}, content=b"{}"))
    with pytest.raises(websearch_service.WebSearchError) as e:
        asyncio.run(websearch_service.fetch_webpage("https://example.com/api"))
    assert "HTML" in str(e.value)

    _patch_httpx(monkeypatch, _FakeResponse(headers={"content-type": "text/html"},
                                            content="<html><body><p>太短</p></body></html>".encode("utf-8")))
    with pytest.raises(websearch_service.WebSearchError) as e:
        asyncio.run(websearch_service.fetch_webpage("https://example.com/empty"))
    assert "正文" in str(e.value)


# ---------------------------------------------------------------- 笔记参考链接
def test_note_links_vault(data_dir):
    vault.create_note("高数/极限.md", "# 极限")
    # 非法 url → 400
    with pytest.raises(Exception):
        vault.add_note_link("高数/极限.md", "x", "baike.com")

    out = vault.add_note_link("高数/极限.md", "百科", "https://baike.com/极限")
    links = out["links"]
    assert links == [{"title": "百科", "url": "https://baike.com/极限",
                      "added_at": links[0]["added_at"], "source": "manual"}]
    # 重复 url 去重
    out = vault.add_note_link("高数/极限.md", "百科", "https://baike.com/极限")
    assert len(out["links"]) == 1

    # 删除
    assert vault.remove_note_link("高数/极限.md", "https://baike.com/极限")["links"] == []
    with pytest.raises(Exception):  # 再删 → 404
        vault.remove_note_link("高数/极限.md", "https://baike.com/极限")


def test_note_links_backfill_title_and_filter(data_dir):
    # 手写的旧条目：title 为空时再次添加同 url 可补全标题
    vault.create_note("高数/极限.md", '---\nlinks:\n  - title: ""\n    url: "https://a.com"\n---\n# 极限')
    out = vault.add_note_link("高数/极限.md", "百科", "https://a.com")
    assert len(out["links"]) == 1 and out["links"][0]["title"] == "百科"

    # 非 dict / 无 url 的坏条目被过滤
    vault.create_note("高数/坏.md", '---\nlinks:\n  - "just a string"\n  - title: 没有链接\n---\n# 坏')
    assert vault.list_note_links("高数/坏.md") == []


def test_note_links_api(client):
    client.post("/api/topics", json={"name": "高数"})
    client.post("/api/notes", json={"path": "高数/极限.md", "content": "# 极限"})

    r = client.post("/api/notes/links", json={"path": "高数/极限.md", "title": "百科", "url": "https://baike.com/极限"})
    assert r.status_code == 200 and len(r.json()["links"]) == 1
    # 重复 url 去重
    r = client.post("/api/notes/links", json={"path": "高数/极限.md", "title": "百科", "url": "https://baike.com/极限"})
    assert len(r.json()["links"]) == 1

    # 列表与 frontmatter 落盘
    r = client.get("/api/notes/links", params={"path": "高数/极限.md"})
    assert r.json()["links"][0]["url"] == "https://baike.com/极限"
    fm = client.get("/api/notes", params={"path": "高数/极限.md"}).json()["frontmatter"]
    assert fm["links"][0]["title"] == "百科"

    # 非法 url → 400；不存在的笔记 → 404
    assert client.post("/api/notes/links", json={"path": "高数/极限.md", "url": "baike.com"}).status_code == 400
    assert client.post("/api/notes/links", json={"path": "高数/无.md", "url": "https://a.com"}).status_code == 404

    # 删除 → 再删 404
    r = client.post("/api/notes/links/remove", json={"path": "高数/极限.md", "url": "https://baike.com/极限"})
    assert r.json()["links"] == []
    assert client.post("/api/notes/links/remove",
                       json={"path": "高数/极限.md", "url": "https://baike.com/极限"}).status_code == 404


# ---------------------------------------------------------------- 设置与 web 路由
def test_web_search_settings_masking(client):
    r = client.put("/api/settings/web-search", json={
        "enabled": True, "provider": "brave", "api_key": "brave-secret", "max_results": 5})
    assert r.status_code == 200
    ws = r.json()["web_search"]
    assert ws["enabled"] is True and ws["provider"] == "brave" and ws["max_results"] == 5
    assert ws["api_key"] != "brave-secret" and ws["has_key"] is True

    # 真实 key 已落盘；回传打码值不会覆盖
    assert load_settings()["web_search"]["api_key"] == "brave-secret"
    client.put("/api/settings/web-search", json={"api_key": "••••••"})
    assert load_settings()["web_search"]["api_key"] == "brave-secret"

    assert client.put("/api/settings/web-search", json={"foo": 1}).status_code == 400


def test_web_endpoints(client, monkeypatch):
    # 未启用 → WebSearchError 全局转 502
    r = client.get("/api/web/search", params={"q": "极限"})
    assert r.status_code == 502 and "启用" in r.json()["detail"]

    _enable_web("tavily")

    async def fake_search(query, max_results=None):
        return {"provider": "tavily", "results": [{"title": "T", "url": "https://a.com", "snippet": "s"}]}

    monkeypatch.setattr(websearch_service, "search", fake_search)
    r = client.get("/api/web/search", params={"q": "极限", "max_results": 3})
    assert r.status_code == 200 and r.json()["results"][0]["url"] == "https://a.com"

    async def fake_fetch(url):
        return {"title": "T", "url": url, "text": "正文"}

    monkeypatch.setattr(websearch_service, "fetch_webpage", fake_fetch)
    r = client.post("/api/web/fetch", json={"url": "https://a.com"})
    assert r.status_code == 200 and r.json()["text"] == "正文"


# ---------------------------------------------------------------- chat agent 工具
def test_chat_agent_web_tools(data_dir, monkeypatch):
    vault.create_note("高数/极限.md", "# 极限")

    # 未启用：友好提示，不抛异常
    ok, result, summary = chat_agent.execute_tool({"tool": "web_search", "args": {"q": "极限"}})
    assert ok and "未启用" in result

    _enable_web("tavily")

    async def fake_search(query, max_results=None):
        return {"provider": "tavily", "results": [
            {"title": "极限百科", "url": "https://baike.com/极限", "snippet": "极限摘要"}]}

    monkeypatch.setattr(websearch_service, "search", fake_search)
    ok, result, summary = chat_agent.execute_tool({"tool": "web_search", "args": {"q": "极限"}})
    assert ok and "极限百科" in result and "https://baike.com/极限" in result
    assert "命中 1 条" in summary

    async def fake_fetch(url):
        return {"title": "极限百科", "url": url, "text": "极限是微积分的基础。"}

    monkeypatch.setattr(websearch_service, "fetch_webpage", fake_fetch)
    ok, result, _ = chat_agent.execute_tool({"tool": "fetch_webpage", "args": {"url": "https://baike.com/极限"}})
    assert ok and "极限百科" in result and "极限是微积分的基础。" in result

    ok, result, _ = chat_agent.execute_tool(
        {"tool": "add_note_link", "args": {"path": "高数/极限.md", "url": "https://baike.com/极限", "title": "百科"}})
    assert ok and vault.list_note_links("高数/极限.md")[0]["url"] == "https://baike.com/极限"

    # 抓取失败 → 「执行失败」结果而非异常中断会话
    async def fake_fetch_fail(url):
        raise websearch_service.WebSearchError("仅支持抓取 HTML 网页")

    monkeypatch.setattr(websearch_service, "fetch_webpage", fake_fetch_fail)
    ok, result, _ = chat_agent.execute_tool({"tool": "fetch_webpage", "args": {"url": "https://x.com/a.json"}})
    assert not ok and "执行失败" in result


# ---------------------------------------------------------------- use_web 注入
_WEB_RESULTS = [{"title": "极限百科", "url": "https://baike.com/极限", "snippet": "极限摘要"}]


def _enable_web_with_results(monkeypatch, results=_WEB_RESULTS):
    _enable_web("tavily")

    async def fake_search(query, max_results=None):
        return {"provider": "tavily", "results": results}

    monkeypatch.setattr(websearch_service, "search", fake_search)


def test_generate_note_use_web_backfills_links(client, monkeypatch):
    client.post("/api/topics", json={"name": "高数"})
    _enable_web_with_results(monkeypatch)

    seen = {}

    async def fake_complete(provider_id, messages, model="", temperature=None):
        seen["messages"] = messages
        return "## 极限\n定义参见 https://baike.com/极限 。"

    monkeypatch.setattr(llm_router, "complete", fake_complete)
    r = client.post("/api/llm/generate-note", json={
        "topic": "高数", "prompt": "写极限", "title": "极限", "stream": False,
        "save_path": "高数/极限.md", "use_web": True,
    })
    assert r.status_code == 200 and r.json()["saved_path"] == "高数/极限.md"
    # 搜索资料拼到了 user prompt 末尾
    assert "以下是联网搜索到的最新资料" in seen["messages"][-1]["content"]
    assert "https://baike.com/极限" in seen["messages"][-1]["content"]
    # 正文用到的来源回填为 frontmatter links
    note = client.get("/api/notes", params={"path": "高数/极限.md"}).json()
    links = note["frontmatter"]["links"]
    assert links == [{"title": "极限百科", "url": "https://baike.com/极限",
                      "added_at": links[0]["added_at"], "source": "web_search"}]


def test_generate_note_stream_use_web_backfills_links(client, monkeypatch):
    client.post("/api/topics", json={"name": "高数"})
    _enable_web_with_results(monkeypatch)

    async def fake_stream(provider_id, messages, model="", temperature=None):
        yield "定义参见 https://baike.com/极限"

    monkeypatch.setattr(llm_router, "stream_llm", fake_stream)
    r = client.post("/api/llm/generate-note", json={
        "topic": "高数", "prompt": "写极限", "stream": True,
        "save_path": "高数/极限.md", "use_web": True,
    })
    events = _sse_events(r.text)
    assert events[-1]["type"] == "done" and events[-1]["saved_path"] == "高数/极限.md"
    note = client.get("/api/notes", params={"path": "高数/极限.md"}).json()
    assert note["frontmatter"]["links"][0]["source"] == "web_search"


def test_generate_note_use_web_disabled_is_noop(client, monkeypatch):
    client.post("/api/topics", json={"name": "高数"})

    async def fake_complete(provider_id, messages, model="", temperature=None):
        return "纯本地生成"

    monkeypatch.setattr(llm_router, "complete", fake_complete)
    r = client.post("/api/llm/generate-note", json={
        "topic": "高数", "prompt": "写极限", "stream": False,
        "save_path": "高数/极限.md", "use_web": True,
    })
    assert r.status_code == 200
    note = client.get("/api/notes", params={"path": "高数/极限.md"}).json()
    assert "links" not in note["frontmatter"]  # 未启用：不注入、不回填


def test_tutor_chat_use_web_injects_system(client, monkeypatch):
    client.post("/api/topics", json={"name": "高数"})
    client.post("/api/notes", json={"path": "高数/极限.md", "content": "# 极限\n极限内容"})
    _enable_web_with_results(monkeypatch)

    seen = {}

    async def fake_complete(provider_id, messages, model="", temperature=None):
        seen["messages"] = messages
        return "答"

    monkeypatch.setattr(llm_router, "complete", fake_complete)
    r = client.post("/api/llm/tutor-chat", json={
        "paths": ["高数/极限.md"], "stream": False, "use_web": True,
        "messages": [{"role": "user", "content": "极限怎么理解"}],
    })
    assert r.status_code == 200
    system = seen["messages"][0]["content"]
    assert "极限内容" in system  # 原有资料在前
    assert "以下是联网搜索到的最新资料" in system  # 搜索块拼在资料之后


def test_study_guide_use_web_injects_messages(client, monkeypatch):
    client.post("/api/topics", json={"name": "高数"})
    client.post("/api/notes", json={"path": "高数/极限.md", "content": "# 极限\n极限内容"})
    _enable_web_with_results(monkeypatch)

    seen = {}

    async def fake_complete(provider_id, messages, model="", temperature=None):
        seen["messages"] = messages
        return "## 一页速览"

    monkeypatch.setattr(llm_router, "complete", fake_complete)
    # 非流式
    r = client.post("/api/llm/study-guide", json={
        "paths": ["高数/极限.md"], "use_web": True, "save_path": "高数/指南.md"})
    assert r.status_code == 200
    assert "以下是联网搜索到的最新资料" in seen["messages"][-1]["content"]

    # 流式
    async def fake_stream(provider_id, messages, model="", temperature=None):
        yield "## 一页速览"

    monkeypatch.setattr(llm_router, "stream_llm", fake_stream)
    r = client.post("/api/llm/study-guide/stream", json={"paths": ["高数/极限.md"], "use_web": True})
    assert r.status_code == 200
    assert _sse_events(r.text)[-1]["markdown"] == "## 一页速览"


def test_topic_architecture_use_web_injects_messages(client, monkeypatch):
    client.post("/api/topics", json={"name": "机器学习"})
    client.post("/api/notes", json={"path": "机器学习/矩阵.md", "content": "# 矩阵\n## 基础\n内容"})
    _enable_web_with_results(monkeypatch)

    seen = {}

    async def fake_stream(provider_id, messages, model="", temperature=None):
        seen["messages"] = messages
        yield "## 现有内容盘点"

    monkeypatch.setattr(llm_router, "stream_llm", fake_stream)
    r = client.post("/api/llm/topic-architecture/stream", json={"topic": "机器学习", "use_web": True})
    assert r.status_code == 200
    assert "以下是联网搜索到的最新资料" in seen["messages"][-1]["content"]
    # goal 为空时用 topic 作 query（fake_search 收到的 query 无法直接断言，至少验证不报错）
    assert _sse_events(r.text)[-1]["type"] == "done"

"""MCP 客户端（stdio）测试：握手 / tools/list / tools/call、注册表、设置校验、路由、
联网搜索 provider=mcp、AI 对话 mcp_tool 工具。

用一个 nl_mcp.MCPServer 搭的假 MCP server 子进程做真实 stdio JSON-RPC 交互。
"""
import asyncio
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import mcp_client, websearch_service
from app.services.chat_agent import TOOLS, execute_tool
from app.services.settings_store import load_settings, save_settings, update_settings
from app.services.websearch_service import WebSearchError

REPO_ROOT = Path(__file__).resolve().parents[2]
MCP_SERVERS_DIR = REPO_ROOT / "mcp_servers"

# 假 MCP server：注册 echo（回显）与 fake_search（返回固定 JSON 结果，含异构字段名）
FAKE_SERVER_PY = '''\
import sys
sys.path.insert(0, "__MCP_DIR__")
from nl_mcp import MCPServer, main

server = MCPServer("fake-mcp", "测试用假 MCP server")


@server.tool("echo", "回显输入")
def echo(text=""):
    return {"echo": text}


@server.tool("fake_search", "假搜索：返回固定 JSON 结果")
def fake_search(query="", max_results=5):
    return {"results": [
        {"title": "标题一", "url": "https://example.com/1", "snippet": "摘要一"},
        {"link": "https://example.com/2", "description": "摘要二"},
    ]}


@server.tool("garbage", "返回无法解析的纯文本")
def garbage(**kwargs):
    return "搜索完成，共找到若干结果（非结构化文本）"


main(server)
'''


def _configure_mcp_servers(servers):
    """直接写 settings.mcp_servers 并使客户端缓存失效（该段是列表，不走 update_settings）。"""
    s = load_settings()
    s["mcp_servers"] = servers
    save_settings(s)
    mcp_client.invalidate()


@pytest.fixture()
def fake_server(tmp_path):
    """把假 MCP server 写到临时目录，并配置为唯一启用的服务器。"""
    script = tmp_path / "fake_mcp_server.py"
    script.write_text(FAKE_SERVER_PY.replace("__MCP_DIR__", str(MCP_SERVERS_DIR)), encoding="utf-8")
    sid = "fakesrv1"
    _configure_mcp_servers([{
        "id": sid, "name": "假搜索", "command": sys.executable,
        "args": [str(script)], "env": {}, "enabled": True,
    }])
    yield {"id": sid, "script": str(script)}
    mcp_client.shutdown_all()


@pytest.fixture()
def client(data_dir):
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------- MCPClient 协议
def test_client_handshake_tools_and_call(data_dir, fake_server):
    c = mcp_client.MCPClient(sys.executable, [fake_server["script"]])
    c.start()
    try:
        names = {t["name"] for t in c.tools}
        assert names == {"echo", "fake_search", "garbage"}
        assert all(t["inputSchema"]["type"] == "object" for t in c.tools)
        r = c.call_tool("echo", {"text": "你好"})
        assert r["isError"] is False
        assert "你好" in r["content"][0]["text"]
        # 工具内错误（未知工具）不抛异常，原样返回 isError 结果
        r2 = c.call_tool("no_such_tool", {})
        assert r2["isError"] is True
    finally:
        c.close()
    assert c.proc is None


def test_client_start_failure_cleans_up(data_dir):
    c = mcp_client.MCPClient("definitely-not-a-real-command-xyz", [])
    with pytest.raises(mcp_client.MCPError):
        c.start()
    assert c.proc is None


# ---------------------------------------------------------------- 注册表
def test_get_client_requires_configured_and_enabled(data_dir, fake_server):
    # 未配置 / 不存在
    with pytest.raises(mcp_client.MCPError):
        mcp_client.get_client("no-such-server")
    # 未启用
    _configure_mcp_servers([{**{k: v for k, v in load_settings()["mcp_servers"][0].items()},
                             "enabled": False}])
    with pytest.raises(mcp_client.MCPError):
        mcp_client.call_tool(fake_server["id"], "echo", {"text": "x"})


def test_registry_reuses_client_and_invalidate(data_dir, fake_server):
    c1 = mcp_client.get_client(fake_server["id"])
    c2 = mcp_client.get_client(fake_server["id"])
    assert c1 is c2
    mcp_client.invalidate()
    assert fake_server["id"] not in mcp_client._clients
    assert c1.proc is None
    c3 = mcp_client.get_client(fake_server["id"])
    assert c3 is not c1 and c3.is_alive()


def test_list_server_tools_with_error_entry(data_dir, fake_server):
    # 加一个连不上的 server：不抛错，记 error
    servers = load_settings()["mcp_servers"]
    servers.append({"id": "broken", "name": "坏的", "command": "definitely-not-real-xyz",
                    "args": [], "env": {}, "enabled": True})
    _configure_mcp_servers(servers)
    out = {s["id"]: s for s in mcp_client.list_server_tools()}
    assert out[fake_server["id"]]["error"] == ""
    assert {t["name"] for t in out[fake_server["id"]]["tools"]} == {"echo", "fake_search", "garbage"}
    assert out["broken"]["tools"] == [] and "找不到" in out["broken"]["error"]


def test_sweep_idle_closes_clients(data_dir, fake_server, monkeypatch):
    c = mcp_client.get_client(fake_server["id"])
    assert fake_server["id"] in mcp_client._clients
    monkeypatch.setattr(mcp_client, "IDLE_SECONDS", -1)
    mcp_client._sweep_idle()
    assert fake_server["id"] not in mcp_client._clients
    assert c.proc is None


# ---------------------------------------------------------------- HTTP 路由
def test_api_servers_and_call(data_dir, fake_server, client):
    r = client.get("/api/mcp/servers")
    assert r.status_code == 200
    servers = r.json()["servers"]
    assert len(servers) == 1
    srv = servers[0]
    assert srv["id"] == fake_server["id"] and srv["enabled"] is True and srv["error"] == ""
    assert {t["name"] for t in srv["tools"]} == {"echo", "fake_search", "garbage"}

    r = client.post("/api/mcp/call", json={"server": fake_server["id"], "tool": "echo",
                                           "arguments": {"text": "hi"}})
    assert r.status_code == 200
    result = r.json()["result"]
    assert result["isError"] is False and "hi" in result["content"][0]["text"]

    # 未知 server → 400
    assert client.post("/api/mcp/call", json={"server": "nope", "tool": "echo"}).status_code == 400


def test_api_call_disabled_server_400(data_dir, fake_server, client):
    servers = load_settings()["mcp_servers"]
    _configure_mcp_servers([{**servers[0], "enabled": False}])
    r = client.post("/api/mcp/call", json={"server": fake_server["id"], "tool": "echo",
                                           "arguments": {"text": "hi"}})
    assert r.status_code == 400
    # 列表接口里 disabled 的 server 不尝试连接
    entry = client.get("/api/mcp/servers").json()["servers"][0]
    assert entry["enabled"] is False and entry["tools"] == [] and entry["error"] == ""


# ---------------------------------------------------------------- 设置保存
def test_settings_mcp_servers_put(data_dir, client):
    # 默认设置带 mcp_servers 段
    assert client.get("/api/settings").json()["mcp_servers"] == []

    # 结构错误 → 400
    assert client.put("/api/settings/mcp-servers", json={"mcp_servers": "x"}).status_code == 400
    assert client.put("/api/settings/mcp-servers", json={"foo": 1}).status_code == 400
    # command 为空 → 400
    assert client.put("/api/settings/mcp-servers",
                      json={"mcp_servers": [{"name": "s", "command": ""}]}).status_code == 400
    # id 重复 → 400
    assert client.put("/api/settings/mcp-servers",
                      json={"mcp_servers": [{"id": "d", "command": "a"}, {"id": "d", "command": "b"}]}
                      ).status_code == 400

    r = client.put("/api/settings/mcp-servers", json={"mcp_servers": [
        {"name": "web search", "command": "npx", "args": "a,b",
         "env": {"API_KEY": "secret", "PLAIN": "bar"}, "enabled": True},
    ]})
    assert r.status_code == 200
    srv = r.json()["mcp_servers"][0]
    assert srv["command"] == "npx" and srv["args"] == ["a", "b"] and srv["enabled"] is True
    assert len(srv["id"]) == 8  # 缺省 id 生成 uuid hex[:8]
    assert srv["env"] == {"API_KEY": "••••••", "PLAIN": "bar"}  # 含 KEY 的值打码，其余原样

    # 前端把打码值存回来：secret 沿用旧值
    r2 = client.put("/api/settings/mcp-servers", json={"mcp_servers": [srv]})
    assert r2.status_code == 200
    assert load_settings()["mcp_servers"][0]["env"]["API_KEY"] == "secret"


# ---------------------------------------------------------------- 联网搜索 provider=mcp
def _enable_mcp_search(server_id, tool="fake_search"):
    update_settings("web_search", {"enabled": True, "provider": "mcp",
                                   "mcp_server": server_id, "mcp_tool": tool})


def test_websearch_mcp_provider(data_dir, fake_server):
    _enable_mcp_search(fake_server["id"])
    data = asyncio.run(websearch_service.search("测试"))
    assert data["provider"] == "mcp"
    assert data["results"] == [
        {"title": "标题一", "url": "https://example.com/1", "snippet": "摘要一"},
        # 第二条没有 title：title 回退为 url；snippet 取 description
        {"title": "https://example.com/2", "url": "https://example.com/2", "snippet": "摘要二"},
    ]


def test_websearch_mcp_unparseable(data_dir, fake_server):
    # garbage 返回非结构化文本：完全解析不出 → WebSearchError
    _enable_mcp_search(fake_server["id"], tool="garbage")
    with pytest.raises(WebSearchError, match="无法解析"):
        asyncio.run(websearch_service.search("测试"))


def test_websearch_mcp_tool_error(data_dir, fake_server):
    # 工具内报错（isError）：原样转为搜索失败
    _enable_mcp_search(fake_server["id"], tool="echo")
    with pytest.raises(WebSearchError, match="执行失败"):
        asyncio.run(websearch_service.search("测试"))


def test_websearch_mcp_not_configured(data_dir, fake_server):
    update_settings("web_search", {"enabled": True, "provider": "mcp",
                                   "mcp_server": "", "mcp_tool": ""})
    with pytest.raises(WebSearchError, match="设置"):
        asyncio.run(websearch_service.search("测试"))


# ---------------------------------------------------------------- AI 对话工具
def test_chat_agent_mcp_tool(data_dir, fake_server):
    assert "mcp_tool" in TOOLS
    assert TOOLS["mcp_tool"][0] == ("server", "tool")
    ok, result, _ = execute_tool({"tool": "mcp_tool",
                                  "args": {"server": fake_server["id"], "tool": "echo",
                                           "args": {"text": "hi"}}})
    assert ok is True and "hi" in result
    # 缺少 server 参数 → ok=False
    ok2, msg, _ = execute_tool({"tool": "mcp_tool", "args": {"tool": "echo"}})
    assert ok2 is False and "server" in msg
    # server 不存在 → 友好失败文案（不抛异常中断会话）
    ok3, msg3, _ = execute_tool({"tool": "mcp_tool",
                                 "args": {"server": "nope", "tool": "echo"}})
    assert ok3 is True and "调用失败" in msg3 and "MCP" in msg3

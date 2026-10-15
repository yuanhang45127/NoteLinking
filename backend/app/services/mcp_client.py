"""MCP 客户端：连接用户配置的 stdio MCP server（web search MCP 等），供
- 内置联网搜索的 provider="mcp" 档
- AI 对话 agent 的 mcp_tool 工具

纯标准库实现 MCP stdio 传输（每行一条 JSON-RPC 2.0 消息），与服务端循环
（mcp_servers/nl_mcp.py 的 MCPServer.serve）对应：握手 initialize →
notifications/initialized → tools/list → tools/call。

进程管理：按 server id 缓存子进程，调用串行（每客户端一把 Lock）；
空闲超过 IDLE_SECONDS 的连接由守护线程回收；调用超时杀进程，下次重连。
"""
import json
import os
import select
import subprocess
import threading
import time
from typing import Dict, List, Optional

from .settings_store import load_settings

PROTOCOL_VERSION = "2025-06-18"
CLIENT_NAME = "notelink"
CLIENT_VERSION = "0.4.0"

INIT_TIMEOUT = 15.0    # initialize / tools/list 超时
CALL_TIMEOUT = 60.0    # 单次 tools/call 默认超时
IDLE_SECONDS = 600     # 空闲回收阈值（10 分钟）
SWEEP_INTERVAL = 60    # 回收线程扫描间隔（秒）


class MCPError(Exception):
    """MCP 连接 / 调用失败（server 未配置、进程起不来、握手失败、调用超时等）。"""


class MCPClient:
    """一个 stdio MCP server 子进程的连接：启动即完成握手并缓存工具列表。"""

    def __init__(self, command: str, args: Optional[List[str]] = None,
                 env: Optional[Dict[str, str]] = None):
        self.command = command
        self.args = [str(a) for a in (args or [])]
        self.env = {str(k): str(v) for k, v in (env or {}).items()}
        self.tools: List[dict] = []
        self.proc: Optional[subprocess.Popen] = None
        self.last_used = time.monotonic()
        self._id = 0
        self._lock = threading.Lock()

    # ---- 底层收发 ----
    def _write(self, msg: dict) -> None:
        if self.proc is None or self.proc.stdin is None:
            raise MCPError(f"MCP server 未启动：{self.command}")
        try:
            self.proc.stdin.write(json.dumps(msg, ensure_ascii=False) + "\n")
            self.proc.stdin.flush()
        except (BrokenPipeError, OSError) as e:
            raise MCPError(f"写入 MCP server 失败（{self.command}）：{e}")

    def _read_response(self, method: str, timeout: float) -> dict:
        """读一条带 id 的响应（select 等可读 + readline 收行，参考 mcp_servers/test_mcp.py）。"""
        if self.proc is None or self.proc.stdout is None:
            raise MCPError(f"MCP server 未启动：{self.command}")
        if self.proc.poll() is not None:
            raise MCPError(f"MCP server 进程已退出：{self.command}")
        ready, _, _ = select.select([self.proc.stdout], [], [], timeout)
        if not ready:
            raise MCPError(f"等待 MCP server 响应超时（{method}，{timeout:.0f}s）")
        line = self.proc.stdout.readline()
        if not line:
            err = ""
            try:
                err = (self.proc.stderr.read() or "")[:500] if self.proc.stderr else ""
            except Exception:  # noqa: BLE001 — stderr 读取失败不影响主错误
                pass
            raise MCPError(f"MCP server 退出（EOF）：{self.command}。{err}".rstrip())
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            raise MCPError(f"MCP server 返回了非法 JSON：{line[:200]}")
        if "error" in msg and msg["error"]:
            err = msg["error"] or {}
            raise MCPError(f"MCP server 返回错误（{method}）：{err.get('message', err)}")
        return msg.get("result") or {}

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    # ---- 生命周期 ----
    def is_alive(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def touch(self) -> None:
        self.last_used = time.monotonic()

    def start(self) -> None:
        """启动子进程并完成 MCP 握手（initialize → initialized → tools/list）。

        任何一步失败：杀进程、抛 MCPError。
        """
        with self._lock:
            try:
                self.proc = subprocess.Popen(
                    [self.command] + self.args,
                    stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                    text=True, bufsize=1,
                    # 合并用户 env，不覆盖系统 PATH
                    env={**os.environ, **self.env},
                )
            except FileNotFoundError:
                raise MCPError(f"找不到 MCP server 可执行文件：{self.command}")
            except OSError as e:
                raise MCPError(f"启动 MCP server 失败（{self.command}）：{e}")
            try:
                self._write({"jsonrpc": "2.0", "id": self._next_id(), "method": "initialize",
                             "params": {"protocolVersion": PROTOCOL_VERSION, "capabilities": {},
                                        "clientInfo": {"name": CLIENT_NAME, "version": CLIENT_VERSION}}})
                self._read_response("initialize", INIT_TIMEOUT)
                # 通知（无 id）不回包
                self._write({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
                self._write({"jsonrpc": "2.0", "id": self._next_id(), "method": "tools/list", "params": {}})
                self.tools = list(self._read_response("tools/list", INIT_TIMEOUT).get("tools") or [])
            except MCPError:
                self.close()
                raise
            except Exception as e:  # noqa: BLE001 — 统一转为 MCPError 并清理进程
                self.close()
                raise MCPError(f"MCP server 初始化失败（{self.command}）：{e}")
            self.last_used = time.monotonic()

    def list_tools(self) -> List[dict]:
        """返回握手时缓存的工具列表（name/description/inputSchema）。"""
        with self._lock:
            self.last_used = time.monotonic()
            return list(self.tools)

    def call_tool(self, name: str, arguments: Optional[dict] = None,
                  timeout: float = CALL_TIMEOUT) -> dict:
        """调用工具，原样返回 result（isError 为真时不抛异常，由调用方决定怎么展示）。

        超时 → 杀进程（下次 get_client 重连）并抛 MCPError。
        """
        with self._lock:
            if not self.is_alive():
                raise MCPError(f"MCP server 未连接（{self.command}），请重试")
            try:
                self._write({"jsonrpc": "2.0", "id": self._next_id(), "method": "tools/call",
                             "params": {"name": name, "arguments": arguments or {}}})
                result = self._read_response("tools/call", timeout)
            except MCPError as e:
                self.close()
                if "超时" in str(e):
                    raise MCPError(
                        f"调用 MCP 工具 {name} 超时（{timeout:.0f}s），连接已重置，请重试")
                raise
            self.last_used = time.monotonic()
            return result

    def close(self) -> None:
        """结束子进程：terminate，等最多 5s，超时 kill。"""
        proc, self.proc = self.proc, None
        if proc is None:
            return
        try:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        except Exception:  # noqa: BLE001 — 进程已退出等情况忽略
            pass
        try:
            if proc.stdin:
                proc.stdin.close()
            if proc.stdout:
                proc.stdout.close()
            if proc.stderr:
                proc.stderr.close()
        except Exception:  # noqa: BLE001
            pass


# ---------------------------------------------------------------- 进程注册表
_clients: Dict[str, MCPClient] = {}
_LOCK = threading.Lock()
_reaper_started = False


def _find_server(server_id: str) -> Optional[dict]:
    """从设置里找已启用的 MCP server 配置。"""
    for s in load_settings().get("mcp_servers") or []:
        if isinstance(s, dict) and s.get("id") == server_id and s.get("enabled"):
            return s
    return None


def get_client(server_id: str) -> MCPClient:
    """取（并按需启动/重连）server 对应的客户端；不存在或未启用抛 MCPError。"""
    cfg = _find_server(server_id)
    if cfg is None:
        raise MCPError(f"MCP server 不存在或未启用：{server_id}")
    with _LOCK:
        client = _clients.get(server_id)
        if client is not None and client.is_alive():
            client.touch()
            return client
        client = MCPClient(str(cfg.get("command") or ""), cfg.get("args") or [], cfg.get("env") or {})
        try:
            client.start()
        except MCPError:
            _clients.pop(server_id, None)
            raise
        _clients[server_id] = client
        _ensure_reaper()
        return client


def list_server_tools() -> List[dict]:
    """遍历设置里全部 MCP server（仅 enabled 尝试连接），返回工具列表。

    连不上的 server 不抛错：记 error 字段、tools 为 []。
    """
    out: List[dict] = []
    for s in load_settings().get("mcp_servers") or []:
        if not isinstance(s, dict):
            continue
        entry = {"id": str(s.get("id") or ""), "name": str(s.get("name") or ""),
                 "command": str(s.get("command") or ""), "enabled": bool(s.get("enabled", True)),
                 "tools": [], "error": ""}
        if entry["enabled"]:
            try:
                entry["tools"] = get_client(entry["id"]).list_tools()
            except MCPError as e:
                entry["error"] = str(e)
        out.append(entry)
    return out


def call_tool(server_id: str, name: str, arguments: Optional[dict] = None,
              timeout: float = CALL_TIMEOUT) -> dict:
    """调用指定 server 的工具（不存在/未启用抛 MCPError）。"""
    return get_client(server_id).call_tool(name, arguments or {}, timeout)


def invalidate(server_id: Optional[str] = None) -> None:
    """关闭并清除缓存的连接（设置保存后调用）；无参=全部。"""
    with _LOCK:
        if server_id is None:
            victims = list(_clients.values())
            _clients.clear()
        else:
            client = _clients.pop(server_id, None)
            victims = [client] if client else []
    for c in victims:
        c.close()


def shutdown_all() -> None:
    """lifespan 结束时调用：关闭全部 MCP server 子进程。"""
    invalidate()


# ---------------------------------------------------------------- 空闲回收
def _sweep_idle() -> None:
    """关闭空闲超过 IDLE_SECONDS 的 client（模块级函数，测试可直接调用）。"""
    now = time.monotonic()
    with _LOCK:
        stale = [c for c in _clients.values() if now - c.last_used > IDLE_SECONDS]
        for sid in [sid for sid, c in _clients.items() if c in stale]:
            del _clients[sid]
    for c in stale:
        c.close()


def _reaper_loop() -> None:
    while True:
        time.sleep(SWEEP_INTERVAL)
        try:
            _sweep_idle()
        except Exception:  # noqa: BLE001 — 回收失败不影响主流程
            pass


def _ensure_reaper() -> None:
    """懒启动空闲回收守护线程（持 _LOCK 调用）。"""
    global _reaper_started
    if _reaper_started:
        return
    _reaper_started = True
    threading.Thread(target=_reaper_loop, name="mcp-reaper", daemon=True).start()

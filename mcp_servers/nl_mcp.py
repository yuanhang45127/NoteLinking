"""NoteLink MCP 共享运行时（纯标准库，Python ≥ 3.9）。

为 NoteLink 的各 MCP 服务器提供：
- stdio JSON-RPC 2.0 循环（MCP stdio 传输：每行一条 JSON 消息）
- tools/list、tools/call、initialize、ping 等方法的最小实现
- 对 NoteLink HTTP API 的薄封装（GET/POST/PUT/PATCH/DELETE + multipart 上传 + SSE 消费）

环境变量：
- NOTELINK_BASE_URL  服务器地址，默认 http://127.0.0.1:8020（本机部署）；
                     自建远程服务时改成你的公网/内网入口
- NOTELINK_TOKEN     访问令牌（服务器开启访问令牌时必填，请求头 X-Notebook-Token）
- NOTELINK_SESSION   会话令牌（服务器多用户模式时必填，请求头 X-Session，
                     值为网页登录后的 nl_session cookie）
- NOTELINK_TIMEOUT   单请求超时秒数，默认 300（LLM 生成类调用较慢）
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE_URL = os.environ.get("NOTELINK_BASE_URL", "http://127.0.0.1:8020").rstrip("/")
TOKEN = os.environ.get("NOTELINK_TOKEN", "")
SESSION = os.environ.get("NOTELINK_SESSION", "")
DEFAULT_TIMEOUT = float(os.environ.get("NOTELINK_TIMEOUT", "300"))

PROTOCOL_VERSION = "2025-06-18"


# ---------------------------------------------------------------- HTTP 客户端

# 直连（不走系统代理）：macOS 上 urllib 默认读取系统代理设置，Tailscale/内网
# 地址会被 Clash 类代理拦截成 502 Bad Gateway，因此显式使用空 ProxyHandler。
_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def _headers(extra=None):
    h = {"Accept": "application/json"}
    if TOKEN:
        h["X-Notebook-Token"] = TOKEN
    if SESSION:
        h["X-Session"] = SESSION
    if extra:
        h.update(extra)
    return h


def _error_message(e):
    """把 HTTPError / URLError 转成可直接给模型看的中文错误。"""
    if isinstance(e, urllib.error.HTTPError):
        try:
            detail = json.loads(e.read().decode("utf-8", "replace")).get("detail")
        except Exception:  # noqa: BLE001
            detail = None
        if isinstance(detail, dict):
            detail = json.dumps(detail, ensure_ascii=False)
        return f"NoteLink API 返回 HTTP {e.code}：{detail or e.reason}"
    reason = getattr(e, "reason", e)
    return f"无法连接 NoteLink（{BASE_URL}）：{reason}。请检查 NOTELINK_BASE_URL 与网络（服务器是否在线）。"


def api(method, path, params=None, body=None, timeout=None, raw=False):
    """调用 NoteLink API。raw=True 时返回原始字节（下载 zip/pdf 用）。"""
    url = BASE_URL + path
    if params:
        params = {k: v for k, v in params.items() if v not in (None, "")}
        if params:
            url += "?" + urllib.parse.urlencode(params)
    data, extra = None, None
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        extra = {"Content-Type": "application/json"}
    req = urllib.request.Request(url, data=data, method=method, headers=_headers(extra))
    try:
        with _OPENER.open(req, timeout=timeout or DEFAULT_TIMEOUT) as r:
            payload = r.read()
    except (urllib.error.HTTPError, urllib.error.URLError) as e:
        raise RuntimeError(_error_message(e)) from None
    if raw:
        return payload
    return json.loads(payload) if payload else {}


def api_get(route, **params):
    return api("GET", route, params=params)


def api_post(route, body=None, **params):
    return api("POST", route, params=params, body=body if body is not None else {})


def api_put(route, body=None, **params):
    return api("PUT", route, params=params, body=body if body is not None else {})


def api_patch(route, body, **params):
    return api("PATCH", route, params=params, body=body)


def api_delete(route, **params):
    return api("DELETE", route, params=params)


def api_upload(path, fields, file_field, filename, content, timeout=None):
    """multipart/form-data 上传（PDF 导入用）。"""
    boundary = "----nlmcpboundary7d91a2f"
    parts = []
    for k, v in fields.items():
        parts.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode("utf-8")
        )
    parts.append(
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="{file_field}"; '
            f'filename="{filename}"\r\nContent-Type: application/pdf\r\n\r\n'
        ).encode("utf-8")
        + content
        + b"\r\n"
    )
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    data = b"".join(parts)
    req = urllib.request.Request(
        BASE_URL + path,
        data=data,
        method="POST",
        headers=_headers({"Content-Type": f"multipart/form-data; boundary={boundary}"}),
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout or DEFAULT_TIMEOUT) as r:
            return json.loads(r.read() or b"{}")
    except (urllib.error.HTTPError, urllib.error.URLError) as e:
        raise RuntimeError(_error_message(e)) from None


def api_sse(method, path, body, timeout=None):
    """消费 NoteLink 的 SSE 流式接口，yield 每个事件的 JSON dict。

    事件格式：{"type":"delta","text":..} → {"type":"done",..} / {"type":"error","message":..}
    """
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        BASE_URL + path,
        data=data,
        method=method,
        headers=_headers({"Content-Type": "application/json", "Accept": "text/event-stream"}),
    )
    try:
        resp = urllib.request.urlopen(req, timeout=timeout or DEFAULT_TIMEOUT)
    except (urllib.error.HTTPError, urllib.error.URLError) as e:
        raise RuntimeError(_error_message(e)) from None
    with resp:
        event = {}
        for raw_line in resp:
            line = raw_line.decode("utf-8", "replace").rstrip("\r\n")
            if line.startswith("data:"):
                try:
                    event = json.loads(line[5:].strip())
                except json.JSONDecodeError:
                    event = {}
                yield event


def sse_collect(method, path, body, timeout=None):
    """跑完一个 SSE 接口，拼接 delta 文本并返回 done 事件（出错抛 RuntimeError）。"""
    buf, done = [], {}
    for ev in api_sse(method, path, body, timeout=timeout):
        if ev.get("type") == "delta":
            buf.append(ev.get("text", ""))
        elif ev.get("type") == "error":
            raise RuntimeError(f"NoteLink 生成失败：{ev.get('message', '未知错误')}")
        elif ev.get("type") == "done":
            done = ev
    done.setdefault("text", "".join(buf))
    return done


# ---------------------------------------------------------------- JSON Schema 便捷构造

def P(type_, desc, enum=None, items=None):
    """构造 JSON Schema 属性。"""
    d = {"type": type_, "description": desc}
    if enum is not None:
        d["enum"] = enum
    if items is not None:
        d["items"] = items
    return d


STR = "string"
BOOL = "boolean"
NUM = "number"
ARR_STR = {"type": "array", "items": {"type": "string"}}
MESSAGE_ITEM = {
    "type": "object",
    "properties": {
        "role": P(STR, "角色：system / user / assistant"),
        "content": P(STR, "消息内容"),
    },
    "required": ["role", "content"],
}


# ---------------------------------------------------------------- MCP 服务器骨架

class MCPServer:
    """最小 MCP 服务器：stdio 传输 + tools 能力。"""

    def __init__(self, name, description):
        self.name = name
        self.description = description
        self.version = "0.1.0"
        self.tools = []

    def tool(self, name, description, properties=None, required=None):
        """装饰器：把函数注册为 MCP 工具。"""

        def deco(fn):
            self.tools.append(
                {
                    "name": name,
                    "description": description,
                    "inputSchema": {
                        "type": "object",
                        "properties": properties or {},
                        "required": required or [],
                        "additionalProperties": False,
                    },
                    "handler": fn,
                }
            )
            return fn

        return deco

    # ---- 协议处理 ----

    def _dispatch(self, method, params):
        if method == "initialize":
            return {
                "protocolVersion": (params or {}).get("protocolVersion") or PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": self.name, "version": self.version},
                "instructions": self.description,
            }
        if method == "ping":
            return {}
        if method == "tools/list":
            return {
                "tools": [
                    {k: t[k] for k in ("name", "description", "inputSchema")} for t in self.tools
                ]
            }
        if method == "tools/call":
            return self._call_tool((params or {}).get("name"), (params or {}).get("arguments"))
        if method in ("resources/list",):
            return {"resources": []}
        if method in ("prompts/list",):
            return {"prompts": []}
        if method in ("logging/setLevel",):
            return {}
        raise LookupError(method)

    def _call_tool(self, name, arguments):
        tool = next((t for t in self.tools if t["name"] == name), None)
        if tool is None:
            return _tool_error(f"未知工具：{name}")
        arguments = arguments or {}
        try:
            out = tool["handler"](**arguments)
        except TypeError as e:
            return _tool_error(f"参数错误：{e}")
        except Exception as e:  # noqa: BLE001 — 工具内错误以 isError 结果返回
            return _tool_error(str(e))
        text = out if isinstance(out, str) else json.dumps(out, ensure_ascii=False, indent=1)
        return {"content": [{"type": "text", "text": text}], "isError": False}

    def serve(self):
        """stdio 主循环：每行一条 JSON-RPC 消息，带 id 的才回包。"""
        for stream in (sys.stdin, sys.stdout):
            try:
                stream.reconfigure(encoding="utf-8")
            except Exception:  # noqa: BLE001
                pass
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                continue
            method = msg.get("method", "")
            if "id" not in msg:  # 通知（initialized/cancelled 等）不回包
                continue
            try:
                result = self._dispatch(method, msg.get("params"))
                resp = {"jsonrpc": "2.0", "id": msg["id"], "result": result}
            except LookupError:
                resp = {
                    "jsonrpc": "2.0",
                    "id": msg["id"],
                    "error": {"code": -32601, "message": f"方法不存在：{method}"},
                }
            except Exception as e:  # noqa: BLE001
                resp = {
                    "jsonrpc": "2.0",
                    "id": msg["id"],
                    "error": {"code": -32603, "message": str(e)},
                }
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()


def _tool_error(message):
    return {"content": [{"type": "text", "text": f"错误：{message}"}], "isError": True}


def health_tool(server):
    """给每个服务器挂一个 health 工具，方便客户端测连通。"""

    @server.tool("health", "测试与 NoteLink 服务器的连通性（GET /api/health）。")
    def health():
        return api_get("/api/health")


def main(server):
    server.serve()

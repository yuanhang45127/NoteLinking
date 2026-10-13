"""NoteLink MCP 服务器冒烟测试：协议握手 + 真实只读调用。

运行：python3 test_mcp.py [服务器文件 ...]
默认测全部 5 个服务器；连的是 NOTELINK_BASE_URL（默认 tailnet 入口），只做只读调用。
"""
import json
import os
import select
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ALL_SERVERS = [
    "notelink_notes.py",
    "notelink_knowledge.py",
    "notelink_exam.py",
    "notelink_ai.py",
    "notelink_papers.py",
]
READ_TIMEOUT = 60  # 单条响应最长等待（含真实 HTTP 调用）


class Client:
    def __init__(self, script):
        self.proc = subprocess.Popen(
            [sys.executable, os.path.join(HERE, script)],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, text=True, bufsize=1,
        )
        self._id = 0

    def notify(self, method, params=None):
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "method": method, "params": params or {}}) + "\n")
        self.proc.stdin.flush()

    def call(self, method, params=None):
        self._id += 1
        self.proc.stdin.write(json.dumps({"jsonrpc": "2.0", "id": self._id, "method": method, "params": params or {}}) + "\n")
        self.proc.stdin.flush()
        ready, _, _ = select.select([self.proc.stdout], [], [], READ_TIMEOUT)
        if not ready:
            raise TimeoutError(f"{READ_TIMEOUT}s 内没有等到 {method} 的响应")
        line = self.proc.stdout.readline()
        if not line:
            err = self.proc.stderr.read()
            raise RuntimeError(f"服务器退出（EOF）。stderr: {err[:500]}")
        return json.loads(line)

    def tool(self, name, arguments=None):
        r = self.call("tools/call", {"name": name, "arguments": arguments or {}})
        assert "result" in r, f"tools/call {name} 返回错误: {r}"
        return r["result"]

    def close(self):
        self.proc.terminate()
        self.proc.wait(timeout=5)


def check(script):
    c = Client(script)
    try:
        r = c.call("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                  "clientInfo": {"name": "smoke", "version": "0"}})
        info = r["result"]["serverInfo"]
        c.notify("notifications/initialized")  # 通知不回包

        tools = c.call("tools/list")["result"]["tools"]
        assert len(tools) >= 3, f"{script} 工具过少: {len(tools)}"
        names = {t["name"] for t in tools}
        assert "health" in names
        for t in tools:  # 每个工具的 schema 必须合法
            assert t["inputSchema"]["type"] == "object", t["name"]

        assert c.call("ping")["result"] == {}
        assert c.call("resources/list")["result"] == {"resources": []}
        unknown = c.call("bogus/method")
        assert unknown.get("error", {}).get("code") == -32601

        h = c.tool("health")
        assert h["isError"] is False and '"ok"' in h["content"][0]["text"] or '"ok": true' in h["content"][0]["text"]
        return info["name"], len(tools), c
    except Exception:
        c.close()
        raise


def main():
    scripts = sys.argv[1:] or ALL_SERVERS
    for s in scripts:
        name, n, c = check(s)
        # 各服务器挑一个只读工具真实调用
        probe = {"notelink-notes": ("list_topics", {}),
                 "notelink-knowledge": ("count_notes", {"topic": "高等数学"}),
                 "notelink-exam": ("list_exams", {}),
                 "notelink-ai": ("chat", {"messages": [{"role": "user", "content": "只回复两个字：正常"}]}),
                 "notelink-papers": ("list_papers", {"topic": "机器学习"})}.get(name)
        extra = ""
        if probe:
            res = c.tool(probe[0], probe[1])
            text = res["content"][0]["text"]
            flag = "OK" if not res["isError"] else "ERR(工具内)"
            extra = f"; {probe[0]} -> {flag}: {text[:80].strip()}"
        print(f"PASS {s}: server={name}, {n} tools{extra}", flush=True)
        c.close()
    print("ALL SMOKE TESTS PASSED")


if __name__ == "__main__":
    main()

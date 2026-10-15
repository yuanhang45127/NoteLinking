# NoteLink MCP 服务器（打包 5 个）

把 NoteLink 的能力打包成 5 个独立 MCP 服务器，供 ZCode、Claude Desktop、Cursor 等任何支持 MCP 的 AI 工具直接读写你的笔记库——让 AI 成为你的学习助教。
**纯 Python 标准库实现，零第三方依赖**——系统 `python3`（≥3.9）直接运行，无需 venv、无需 pip。

| 服务器 | 文件 | 工具数 | 职责 |
| --- | --- | --- | --- |
| `notelink-notes` | notelink_notes.py | 28 | 主题/目录树、笔记增删改查、搜索、反链、双链解析、置顶、高亮批注、参考链接、PDF 导入、全库导出 |
| `notelink-knowledge` | notelink_knowledge.py | 7 | 概念词条（查询/AI 生成）、知识图谱、局部邻域、主题规模统计 |
| `notelink-exam` | notelink_exam.py | 14 | AI 出卷、交卷判分、考点清单与掌握度、备考目标 |
| `notelink-ai` | notelink_ai.py | 10 | 通用对话、生成笔记落库、选段提问、备考助教、学习指南、主题整体架构、联网搜索、网页抓取 |
| `notelink-papers` | notelink_papers.py | 13 | 论文库管理、arXiv 检索、Zotero 同步、PDF 抓取与转笔记 |

每个服务器都带 `health` 工具用于测连通；`nl_mcp.py` 是共享运行时（stdio JSON-RPC + HTTP 客户端），勿单独运行。

## 环境变量（所有服务器通用）

| 变量 | 默认 | 说明 |
| --- | --- | --- |
| `NOTELINK_BASE_URL` | `http://127.0.0.1:8020` | NoteLink 服务器地址；本机部署用默认值，自建远程服务时改成你的入口 |
| `NOTELINK_TOKEN` | 空 | 服务器开启访问令牌（`NOTEBOOK_TOKEN`）时必填；本地默认部署不用设 |
| `NOTELINK_TIMEOUT` | `300` | 单请求超时秒数（LLM 生成/出卷较慢，别设太小） |

## 接入 MCP 客户端（Claude Desktop / ZCode / Cursor 等）

各客户端配置文件位置不同（Claude Desktop 是 `claude_desktop_config.json`），格式都是 `mcpServers`，
把下面的路径换成你克隆仓库的实际位置：

```json
{
  "mcpServers": {
    "notelink-notes": {
      "command": "/usr/bin/python3",
      "args": ["/path/to/notelink/mcp_servers/notelink_notes.py"]
    }
  }
}
```

只想要一个"全家桶"的话，把 5 个都配上也行——每个都是独立进程，互不影响。

## 测试

```bash
cd mcp_servers
python3 test_mcp.py                    # 全部 5 个：协议握手 + 工具清单 + 真实只读调用
python3 test_mcp.py notelink_notes.py  # 只测一个
```

测试对服务器只做只读调用（health/topics/exams 等）；`notelink-ai` 的探针会真实调用一次对话（走你在 NoteLink「设置 → AI 模型」里配置的服务商）。

## 设计说明

- **stdio 传输 + newline-delimited JSON-RPC**：`MCPServer.serve()` 处理 `initialize` / `tools/list` / `tools/call` / `ping`，未知方法回 `-32601`，通知不回包；工具内异常转成 `isError: true` 的结果而不是断连。
- **非流式优先**：LLM 类接口都用 `stream=false` 拿完整 JSON；`topic-architecture` 只有流式接口，由 `sse_collect()` 聚合后返回。
- **写入类工具需模型自己负责**：`save_note` 是整体覆盖，模型改笔记时应先 `read_note` 再保存，或用 `append_to_note` 追加。
- 新增工具：在对应服务器文件里用 `@server.tool(名称, 描述, properties, required)` 装饰一个函数即可，schema 自动生成。

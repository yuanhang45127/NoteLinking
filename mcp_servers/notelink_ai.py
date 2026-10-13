"""NoteLink MCP · AI 服务器（走 NoteLink「设置 → AI 模型」里配置的服务商）。

通用对话、AI 生成笔记并落库、选中提问、备考助教、学习指南、主题整体架构。
运行：python3 notelink_ai.py（stdio MCP）
"""
from nl_mcp import (
    ARR_STR, BOOL, NUM, STR, MCPServer, MESSAGE_ITEM, P, api_post, health_tool,
    main, sse_collect,
)

server = MCPServer(
    "notelink-ai",
    "NoteLink AI 服务器：用 NoteLink 里配置的大模型生成笔记/讲解/学习指南，并可直接保存进笔记库。"
    "服务商在 NoteLink 网页「设置 → AI 模型」配置。",
)
health_tool(server)


@server.tool("chat", "通用大模型对话（不进笔记库）。messages 为 [{role, content}]。", {
    "messages": {**ARR_STR, "description": "对话历史", "items": MESSAGE_ITEM},
    "provider": P(STR, "指定服务商 id（缺省用当前激活的服务商）"),
    "model": P(STR, "指定模型名（缺省用服务商默认）"),
    "temperature": P(NUM, "采样温度 0-2"),
}, ["messages"])
def chat(messages, provider="", model="", temperature=None):
    body = {"messages": messages, "stream": False}
    if provider:
        body["provider"] = provider
    if model:
        body["model"] = model
    if temperature is not None:
        body["temperature"] = temperature
    return api_post("/api/llm/chat", body)


@server.tool("generate_note", "AI 按大纲生成一篇结构化学习笔记（LaTeX 用 $…$、术语用 [[双链]]），"
                              "可指定 save_path 直接存入笔记库。耗时约 1-3 分钟。", {
    "topic": P(STR, "所属主题（需已存在）"),
    "prompt": P(STR, "要生成什么内容：主题描述/大纲/要求"),
    "title": P(STR, "笔记标题（缺省从 prompt 提取）"),
    "language": P(STR, "zh 或其他语言代码，默认 zh"),
    "save_path": P(STR, "保存路径，如 高等数学/泰勒公式.md（缺省只返回不保存）"),
}, ["topic", "prompt"])
def generate_note(topic, prompt, title="", language="zh", save_path=""):
    body = {"topic": topic, "prompt": prompt, "language": language, "stream": False}
    if title:
        body["title"] = title
    if save_path:
        body["save_path"] = save_path
    return api_post("/api/llm/generate-note", body)


@server.tool("ask_about_note", "针对某篇笔记的选段提问：结合全文上下文讲解，可把问答追加保存回笔记。", {
    "path": P(STR, "笔记路径（提供全文上下文）"),
    "selected_text": P(STR, "选中的原文片段"),
    "question": P(STR, "问题（缺省=讲解选段）"),
    "save_to_note": P(BOOL, "是否把这次问答追加到笔记末尾，默认 false"),
}, ["path", "selected_text"])
def ask_about_note(path, selected_text, question="", save_to_note=False):
    return api_post("/api/llm/ask", {
        "path": path, "selected_text": selected_text, "question": question,
        "stream": False, "save_to_note": save_to_note,
    })


@server.tool("tutor_chat", "备考 AI 助教：自动把勾选资料注入上下文后对话，回答直指考点。", {
    "paths": {**ARR_STR, "description": "助教可用的资料（笔记/概念文档）"},
    "messages": {**ARR_STR, "description": "对话历史（可只传本轮 user 消息）", "items": MESSAGE_ITEM},
    "language": P(STR, "zh 或其他，默认 zh"),
}, ["paths", "messages"])
def tutor_chat(paths, messages, language="zh"):
    return api_post("/api/llm/tutor-chat", {
        "paths": paths, "messages": messages, "language": language, "stream": False,
    })


@server.tool("study_guide", "基于勾选资料生成学习指南（Markdown），可存为笔记。", {
    "paths": {**ARR_STR, "description": "资料路径列表"},
    "language": P(STR, "zh 或其他，默认 zh"),
    "save_path": P(STR, "保存路径（缺省只返回不保存）"),
}, ["paths"])
def study_guide(paths, language="zh", save_path=""):
    body = {"paths": paths, "language": language}
    if save_path:
        body["save_path"] = save_path
    return api_post("/api/llm/study-guide", body)


@server.tool("topic_architecture", "AI 盘点整个主题，生成「整体架构」学习文档并落盘到 "
                                   "<主题>/_架构/整体架构.md（流式接口聚合后返回）。耗时可能较长。", {
    "topic": P(STR, "主题名"),
    "goal": P(STR, "备考目标/侧重方向（可选）"),
    "save_path": P(STR, "自定义保存路径（缺省 主题/_架构/整体架构.md）"),
}, ["topic"])
def topic_architecture(topic, goal="", save_path=""):
    body = {"topic": topic, "goal": goal}
    if save_path:
        body["save_path"] = save_path
    done = sse_collect("POST", "/api/llm/topic-architecture/stream", body)
    return {"saved_path": done.get("saved_path"), "text": done.get("text", "")}


@server.tool("scaffold_topic", "按主题已有的「整体架构」文档生成目录骨架（已存在的目录跳过），"
                                "返回创建的目录清单。", {
    "topic": P(STR, "主题名"),
}, ["topic"])
def scaffold_topic(topic):
    return api_post("/api/llm/topic-architecture/scaffold", {"topic": topic})


if __name__ == "__main__":
    main(server)

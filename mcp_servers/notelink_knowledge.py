"""NoteLink MCP · 知识服务器（概念词条 + 知识图谱）。

概念文档（terms/）的查询与 AI 生成、全库知识图谱、概念双链关系。
运行：python3 notelink_knowledge.py（stdio MCP）
"""
from nl_mcp import (
    BOOL, STR, MCPServer, P, api_get, api_post, health_tool, main,
)

server = MCPServer(
    "notelink-knowledge",
    "NoteLink 知识服务器：概念词条（双链解释文档）的查询与生成、全库知识图谱（[[双链]] 关系）。",
)
health_tool(server)


# ---------------------------------------------------------------- 概念词条

@server.tool("list_terms", "列出概念词条（含 origin 反链信息）。", {
    "topic": P(STR, "限定主题，缺省全库"),
})
def list_terms(topic=""):
    return api_get("/api/terms", topic=topic)


@server.tool("resolve_term", "按名称取概念文档（含一句话解释与完整 markdown）。", {
    "name": P(STR, "概念名，如 极限"),
    "topic": P(STR, "优先在哪个主题内解析"),
}, ["name"])
def resolve_term(name, topic=""):
    return api_get("/api/terms/resolve", name=name, topic=topic)


@server.tool("explain_term", "让大模型结合笔记上下文生成/更新概念文档，落在 <主题>/terms/<词>.md。"
                             "文档章节：一句话解释 / 在当前上下文中的含义 / 数学形式（可选）/ 延伸。"
                             "已存在时默认追加「出现于《原笔记》」章节，regenerate=true 才重写。", {
    "path": P(STR, "概念出处的笔记路径"),
    "term": P(STR, "要解释的词"),
    "context_before": P(STR, "该词前方的上下文（可选，提升解释质量）"),
    "context_after": P(STR, "该词后方的上下文（可选）"),
    "regenerate": P(BOOL, "已存在时是否重新生成（默认 false，追加出处）"),
}, ["path", "term"])
def explain_term(path, term, context_before="", context_after="", regenerate=False):
    return api_post("/api/terms", {
        "path": path, "term": term, "context_before": context_before,
        "context_after": context_after, "regenerate": regenerate,
    })


# ---------------------------------------------------------------- 知识图谱

@server.tool("get_graph", "取知识图谱：nodes（笔记蓝/概念紫/悬空 missing）与 edges，"
                          "由全库 [[双链]] 和概念 origin 关系推出。返回前附 summary 计数。", {
    "topic": P(STR, "限定主题，缺省全库"),
})
def get_graph(topic=""):
    graph = api_get("/api/graph", topic=topic)
    nodes = graph.get("nodes", [])
    edges = graph.get("edges", [])
    by_type = {}
    for n in nodes:
        by_type[n.get("type", "?")] = by_type.get(n.get("type", "?"), 0) + 1
    return {
        "summary": {"nodes": len(nodes), "edges": len(edges), "by_type": by_type},
        "nodes": nodes,
        "edges": edges,
    }


@server.tool("get_concept_neighborhood", "取某个概念/笔记在图谱里的局部邻域："
                                          "它直接链接和被链接的节点（比整图轻量）。", {
    "name": P(STR, "节点名（笔记或概念名）"),
    "topic": P(STR, "限定主题"),
}, ["name"])
def get_concept_neighborhood(name, topic=""):
    graph = api_get("/api/graph", topic=topic)
    nodes = {n.get("id") or n.get("label") or n.get("name"): n for n in graph.get("nodes", [])}
    if name not in nodes:
        close = [k for k in nodes if name and (name in k or k in name)]
        return {"error": f"图谱中找不到「{name}」", "similar": close[:10]}
    edges = [e for e in graph.get("edges", []) if name in (e.get("source"), e.get("target"))]
    ids = {name}
    for e in edges:
        ids.update((e.get("source"), e.get("target")))
    return {
        "center": nodes[name],
        "edges": edges,
        "neighbors": [nodes[i] for i in ids if i in nodes and i != name],
    }


@server.tool("count_notes", "统计某主题的规模：目录树中笔记/概念数量（轻量，不拉正文）。", {
    "topic": P(STR, "主题名"),
}, ["topic"])
def count_notes(topic):
    tree = api_get("/api/tree", path=topic)
    counts = {"note": 0, "term": 0, "dir": 0}

    def walk(n):
        counts[n.get("type", "dir")] = counts.get(n.get("type", "dir"), 0) + 1
        for c in n.get("children", []) or []:
            walk(c)

    if isinstance(tree, dict) and tree.get("type"):
        walk(tree)
    return {"topic": topic, **counts}


if __name__ == "__main__":
    main(server)

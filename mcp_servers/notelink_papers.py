"""NoteLink MCP · 文献服务器（论文库 / arXiv / Zotero）。

按主题管理论文、arXiv 检索与导入、Zotero 同步、论文 PDF 抓取与文本导入为笔记。
运行：python3 notelink_papers.py（stdio MCP）
"""
import os

from nl_mcp import (
    ARR_STR, BOOL, NUM, STR, MCPServer, P, api, api_delete, api_get, api_post, api_put,
    health_tool, main,
)

server = MCPServer(
    "notelink-papers",
    "NoteLink 文献服务器：按主题管理论文库、arXiv 检索导入、Zotero 同步、论文 PDF 下载与导入为笔记。",
)
health_tool(server)


@server.tool("list_papers", "列出某主题的论文。", {
    "topic": P(STR, "主题名"),
}, ["topic"])
def list_papers(topic):
    return api_get("/api/papers", topic=topic)


@server.tool("add_paper", "手工添加一条论文（元信息任意字段可缺省）。", {
    "topic": P(STR, "主题名"),
    "title": P(STR, "论文标题"),
    "authors": {**ARR_STR, "description": "作者列表"},
    "year": P(STR, "年份"),
    "venue": P(STR, "期刊/会议"),
    "abstract": P(STR, "摘要"),
    "doi": P(STR, "DOI"),
    "arxiv_id": P(STR, "arXiv 编号，如 2401.12345"),
    "url": P(STR, "链接"),
    "tags": {**ARR_STR, "description": "标签"},
}, ["topic", "title"])
def add_paper(topic, title, authors=None, year="", venue="", abstract="",
              doi="", arxiv_id="", url="", tags=None):
    body = {"title": title, "authors": authors or [], "year": year, "venue": venue,
            "abstract": abstract, "doi": doi, "arxiv_id": arxiv_id, "url": url,
            "tags": tags or []}
    return api_post("/api/papers", body, topic=topic)


@server.tool("update_paper", "改论文的阅读状态/标签/批注/所属主题（留空不改）。"
                             "status 常用值：todo / reading / done。", {
    "topic": P(STR, "当前所属主题"),
    "paper_id": P(STR, "论文 id"),
    "status": P(STR, "阅读状态，如 todo/reading/done"),
    "comment": P(STR, "我的批注"),
    "move_to_topic": P(STR, "移动到其他主题"),
}, ["topic", "paper_id"])
def update_paper(topic, paper_id, status="", comment="", move_to_topic=""):
    body = {}
    if status:
        body["status"] = status
    if comment:
        body["comment"] = comment
    if move_to_topic:
        body["topic"] = move_to_topic
    return api_put(f"/api/papers/{paper_id}", body, topic=topic)


@server.tool("delete_paper", "从文献库删除论文。", {
    "topic": P(STR, "主题名"),
    "paper_id": P(STR, "论文 id"),
}, ["topic", "paper_id"])
def delete_paper(topic, paper_id):
    return api_delete(f"/api/papers/{paper_id}", topic=topic)


@server.tool("search_arxiv", "检索 arXiv（返回题录，可配合 add_paper 入库）。", {
    "q": P(STR, "检索词（≥2 字符）"),
    "max_results": P(NUM, "最多返回条数，默认 15，上限 40"),
}, ["q"])
def search_arxiv(q, max_results=15):
    return api_get("/api/papers/search-arxiv", q=q, max_results=max_results)


@server.tool("fetch_paper_pdf", "抓取论文 PDF 到服务器文献库（有 DOI/arXiv id 或链接时可用）。", {
    "topic": P(STR, "主题名"),
    "paper_id": P(STR, "论文 id"),
}, ["topic", "paper_id"])
def fetch_paper_pdf(topic, paper_id):
    return api_post(f"/api/papers/{paper_id}/fetch-pdf", topic=topic)


@server.tool("download_paper_pdf", "把论文 PDF 下载到本机（需已 fetch 过）。", {
    "topic": P(STR, "主题名"),
    "paper_id": P(STR, "论文 id"),
    "save_dir": P(STR, "保存目录，默认 ~/Downloads"),
}, ["topic", "paper_id"])
def download_paper_pdf(topic, paper_id, save_dir=""):
    payload = api("GET", f"/api/papers/{paper_id}/pdf", params={"topic": topic}, raw=True)
    directory = os.path.expanduser(save_dir or "~/Downloads")
    out = os.path.join(directory, f"{paper_id}.pdf")
    with open(out, "wb") as f:
        f.write(payload)
    return {"saved_to": out, "size_bytes": len(payload)}


@server.tool("import_paper_text", "把论文 PDF 提取文本，生成一篇 md 笔记进该主题（扫描件不支持）。", {
    "topic": P(STR, "主题名"),
    "paper_id": P(STR, "论文 id"),
}, ["topic", "paper_id"])
def import_paper_text(topic, paper_id):
    return api_post(f"/api/papers/{paper_id}/import-text", topic=topic)


# ---------------------------------------------------------------- Zotero

@server.tool("zotero_status", "查看 Zotero 同步状态（是否已配置、上次同步等）。")
def zotero_status():
    return api_get("/api/papers/zotero/status")


@server.tool("zotero_config", "查看 Zotero 配置（API Key 打码）。")
def zotero_config():
    return api_get("/api/papers/zotero/config")


@server.tool("zotero_save_config", "保存 Zotero 配置（user_id / api_key / collection）。", {
    "user_id": P(STR, "Zotero 用户 id（zotero.org/settings/keys 里看）"),
    "api_key": P(STR, "Zotero API Key"),
    "collection": P(STR, "限定同步的 collection key（缺省全库）"),
    "download_pdf": P(BOOL, "同步时是否下载 PDF"),
})
def zotero_save_config(user_id="", api_key="", collection="", download_pdf=None):
    body = {"user_id": user_id, "api_key": api_key, "collection": collection}
    if download_pdf is not None:
        body["download_pdf"] = download_pdf
    return api_put("/api/papers/zotero/config", body)


@server.tool("zotero_sync", "立即从 Zotero 同步文献（可选限定 collection 与主题）。", {
    "topic": P(STR, "同步进的主题（缺省用配置默认）"),
    "collection": P(STR, "限定 collection key"),
    "download_pdf": P(BOOL, "是否下载 PDF"),
})
def zotero_sync(topic="", collection="", download_pdf=None):
    body = {"topic": topic, "collection": collection}
    if download_pdf is not None:
        body["download_pdf"] = download_pdf
    return api_post("/api/papers/zotero/sync", body)


if __name__ == "__main__":
    main(server)

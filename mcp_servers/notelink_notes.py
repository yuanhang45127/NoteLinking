"""NoteLink MCP · 笔记与标注服务器。

主题/目录树/笔记增删改查/搜索/反链/双链解析/置顶/收藏/高亮批注/PDF 导入/全库导出。
运行：python3 notelink_notes.py（stdio MCP，配置方法见同目录 README.md）
"""
import os
from datetime import date

from nl_mcp import (
    ARR_STR, BOOL, NUM, STR, MCPServer, P, api, api_delete, api_get, api_patch, api_post,
    api_put, api_upload, health_tool, main,
)

server = MCPServer(
    "notelink-notes",
    "NoteLink 笔记服务器：读写 Markdown 笔记、目录树、全文搜索、反链、高亮批注、PDF 导入与全库导出。",
)
health_tool(server)


# ---------------------------------------------------------------- 主题与目录

@server.tool("list_topics", "列出全部主题（侧边栏第一层），含笔记数与 emoji 图标。")
def list_topics():
    return api_get("/api/topics")


@server.tool("create_topic", "新建主题（笔记库顶层文件夹）。", {"name": P(STR, "主题名")}, ["name"])
def create_topic(name):
    return api_post("/api/topics", {"name": name})


@server.tool("rename_topic", "重命名主题。", {
    "name": P(STR, "当前主题名"),
    "new_name": P(STR, "新主题名"),
}, ["name", "new_name"])
def rename_topic(name, new_name):
    return api_patch(f"/api/topics/{name}", {"name": new_name})


@server.tool("set_topic_emoji", "设置主题 emoji 图标（空字符串清除）。", {
    "name": P(STR, "主题名"),
    "emoji": P(STR, "emoji，如 📐；空字符串清除"),
}, ["name"])
def set_topic_emoji(name, emoji):
    return api_put(f"/api/topics/{name}/emoji", {"emoji": emoji})


@server.tool("delete_topic", "删除主题。主题下有笔记时必须 recursive=true。", {
    "name": P(STR, "主题名"),
    "recursive": P(BOOL, "连同笔记一起删除（默认 false）"),
}, ["name"])
def delete_topic(name, recursive=False):
    return api_delete(f"/api/topics/{name}", recursive=recursive)


@server.tool("get_tree", "取目录树（缺省=全库）。节点 type: dir/note/term。", {
    "path": P(STR, "限定某目录，缺省全库"),
})
def get_tree(path=""):
    return api_get("/api/tree", path=path)


# ---------------------------------------------------------------- 笔记读写

@server.tool("read_note", "读取笔记：返回 content、frontmatter、annotations（高亮批注）、"
                          "backlinks（反链）、concept_refs（涉及概念）。路径相对笔记库根，如 高等数学/极限.md", {
    "path": P(STR, "笔记路径"),
    "include_content": P(BOOL, "是否返回正文，默认 true；只要元信息时可关"),
}, ["path"])
def read_note(path, include_content=True):
    note = api_get("/api/notes", path=path)
    if not include_content:
        note["content"] = f"（正文 {len(note.get('content', ''))} 字，已省略；需要时再次调用）"
    return note


@server.tool("create_note", "新建笔记（已存在且 overwrite=false 时报错）。", {
    "path": P(STR, "库内路径，如 主题/笔记名.md"),
    "content": P(STR, "Markdown 正文"),
    "overwrite": P(BOOL, "已存在时是否覆盖，默认 false"),
}, ["path"])
def create_note(path, content="", overwrite=False):
    return api_post("/api/notes", {"path": path, "content": content, "overwrite": overwrite})


@server.tool("save_note", "保存（整体覆盖）笔记正文。", {
    "path": P(STR, "笔记路径"),
    "content": P(STR, "完整 Markdown 正文"),
}, ["path", "content"])
def save_note(path, content):
    return api_put("/api/notes", {"path": path, "content": content})


@server.tool("append_to_note", "把一段内容追加到笔记末尾（比读-改-存省事，不动原文）。", {
    "path": P(STR, "笔记路径"),
    "text": P(STR, "要追加的 Markdown 片段"),
    "heading": P(STR, "可选的小节标题，如「AI 补充」"),
}, ["path", "text"])
def append_to_note(path, text, heading=""):
    note = api_get("/api/notes", path=path)
    block = text.strip() + "\n"
    if heading:
        block = f"\n## {heading}\n\n" + block
    return api_put("/api/notes", {"path": path, "content": note["content"].rstrip() + "\n\n" + block})


@server.tool("move_note", "移动/重命名笔记。", {
    "src": P(STR, "原路径"),
    "dst": P(STR, "新路径"),
}, ["src", "dst"])
def move_note(src, dst):
    return api_post("/api/notes/move", {"src": src, "dst": dst})


@server.tool("delete_note", "删除笔记。", {"path": P(STR, "笔记路径")}, ["path"])
def delete_note(path):
    return api_delete("/api/notes", path=path)


@server.tool("search_notes", "全库全文搜索。", {
    "q": P(STR, "关键词"),
    "topic": P(STR, "限定主题，缺省全库"),
    "limit": P(NUM, "最多返回条数，默认 50"),
}, ["q"])
def search_notes(q, topic="", limit=50):
    return api_get("/api/search", q=q, topic=topic, limit=limit)


@server.tool("get_backlinks", "查询哪些笔记通过 [[双链]] 链到了该笔记。", {
    "path": P(STR, "笔记路径"),
}, ["path"])
def get_backlinks(path):
    return api_get("/api/notes/backlinks", path=path)


@server.tool("resolve_link", "解析 [[双链]] 目标，返回匹配的文档（悬浮预览/跳转用）。", {
    "target": P(STR, "双链目标，如 极限与连续"),
    "topic": P(STR, "优先在哪个主题内解析"),
}, ["target"])
def resolve_link(target, topic=""):
    return api_get("/api/notes/resolve-link", target=target, topic=topic)


@server.tool("list_pinned", "列出全库置顶笔记。")
def list_pinned():
    return api_get("/api/pinned")


@server.tool("set_pinned", "设置/取消笔记置顶。", {
    "path": P(STR, "笔记路径"),
    "pinned": P(BOOL, "true 置顶 / false 取消"),
}, ["path", "pinned"])
def set_pinned(path, pinned):
    return api_post("/api/notes/pin", {"path": path, "pinned": pinned})


@server.tool("list_favorites", "列出全库收藏笔记。")
def list_favorites():
    return api_get("/api/favorites")


@server.tool("set_favorite", "设置/取消笔记收藏。", {
    "path": P(STR, "笔记路径"),
    "fav": P(BOOL, "true 收藏 / false 取消"),
}, ["path", "fav"])
def set_favorite(path, fav):
    return api_post("/api/notes/favorite", {"path": path, "fav": fav})


@server.tool("set_finished", "标记/取消笔记「看完」。", {
    "path": P(STR, "笔记路径"),
    "finished": P(BOOL, "true 标记看完 / false 取消"),
}, ["path", "finished"])
def set_finished(path, finished):
    return api_post("/api/notes/finish", {"path": path, "finished": finished})


@server.tool("batch_notes", "批量删除或移动笔记。", {
    "action": P(STR, "delete 或 move", enum=["delete", "move"]),
    "paths": {**ARR_STR, "description": "笔记路径列表"},
    "target": P(STR, "move 时的目标主题（根目录名）"),
}, ["action", "paths"])
def batch_notes(action, paths, target=""):
    return api_post("/api/notes/batch", {"action": action, "paths": paths, "target": target})


# ---------------------------------------------------------------- 高亮批注

@server.tool("list_annotations", "列出某笔记的全部高亮标注。", {
    "path": P(STR, "笔记路径"),
}, ["path"])
def list_annotations(path):
    return api_get("/api/annotations", path=path)


@server.tool("add_annotation", "给笔记加高亮标注（锚定：quote + 前后文 + 第几次出现）。", {
    "path": P(STR, "笔记路径"),
    "quote": P(STR, "要高亮的原文片段"),
    "prefix": P(STR, "片段前紧邻的几个字（帮助定位，可选）"),
    "suffix": P(STR, "片段后紧邻的几个字（可选）"),
    "occurrence": P(NUM, "quote 第几次出现，默认 1"),
    "comment": P(STR, "随高亮记录的想法/批注"),
    "color": P(STR, "颜色（缺省用设置默认）"),
    "style": P(STR, "background（背景高亮）或 font（字体高亮）", enum=["background", "font"]),
}, ["path", "quote"])
def add_annotation(path, quote, prefix="", suffix="", occurrence=1, comment="", color="", style=""):
    body = {"path": path, "quote": quote, "prefix": prefix, "suffix": suffix,
            "occurrence": occurrence, "comment": comment}
    if color:
        body["color"] = color
    if style:
        body["style"] = style
    return api_post("/api/annotations", body)


@server.tool("update_annotation", "改标注的颜色/样式/批注（留空表示不改）。", {
    "path": P(STR, "笔记路径"),
    "annotation_id": P(STR, "标注 id"),
    "comment": P(STR, "新批注内容"),
    "color": P(STR, "新颜色"),
    "style": P(STR, "background 或 font", enum=["background", "font"]),
}, ["path", "annotation_id"])
def update_annotation(path, annotation_id, comment="", color="", style=""):
    body = {}
    if comment:
        body["comment"] = comment
    if color:
        body["color"] = color
    if style:
        body["style"] = style
    return api_put(f"/api/annotations/{annotation_id}", body, path=path)


@server.tool("delete_annotation", "删除一条高亮标注。", {
    "path": P(STR, "笔记路径"),
    "annotation_id": P(STR, "标注 id"),
}, ["path", "annotation_id"])
def delete_annotation(path, annotation_id):
    return api_delete(f"/api/annotations/{annotation_id}", path=path)


# ---------------------------------------------------------------- 参考链接

@server.tool("add_note_link", "给笔记添加一条参考链接（写入笔记 frontmatter 的 links 列表，按 url 去重）。", {
    "path": P(STR, "笔记路径"),
    "url": P(STR, "网页地址（http/https）"),
    "title": P(STR, "链接标题，缺省用 url"),
    "source": P(STR, "来源标记：manual / web_search / ai，默认 manual"),
}, ["path", "url"])
def add_note_link(path, url, title="", source="manual"):
    return api_post("/api/notes/links", {"path": path, "url": url, "title": title, "source": source})


@server.tool("remove_note_link", "按 url 删除笔记的一条参考链接。", {
    "path": P(STR, "笔记路径"),
    "url": P(STR, "要删除的链接地址"),
}, ["path", "url"])
def remove_note_link(path, url):
    return api_post("/api/notes/links/remove", {"path": path, "url": url})


# ---------------------------------------------------------------- 导入导出

@server.tool("import_pdf", "导入本地 PDF：提取文本生成 md 笔记（扫描件不支持，≤50MB）。", {
    "local_path": P(STR, "本机 PDF 绝对路径"),
    "topic": P(STR, "目标主题（需已存在）"),
    "name": P(STR, "笔记名，缺省用文件名"),
}, ["local_path", "topic"])
def import_pdf(local_path, topic, name=""):
    with open(local_path, "rb") as f:
        content = f.read()
    return api_upload("/api/import/pdf",
                      {"topic": topic, "name": name},
                      "file", os.path.basename(local_path), content)


@server.tool("export_vault", "把全库导出为 zip 下载到本机，返回保存路径。", {
    "save_dir": P(STR, "保存目录，默认 ~/Downloads"),
})
def export_vault(save_dir=""):
    payload = api("GET", "/api/export/vault", raw=True)
    directory = os.path.expanduser(save_dir or "~/Downloads")
    out = os.path.join(directory, f"notelink-vault-{date.today().isoformat()}.zip")
    with open(out, "wb") as f:
        f.write(payload)
    return {"saved_to": out, "size_bytes": len(payload)}


if __name__ == "__main__":
    main(server)

"""AI 对话：会话存储、notes/append、agent 工具协议（不含真实大模型调用）。"""
import pytest
from fastapi.testclient import TestClient
from fastapi import HTTPException

from app.main import app
from app.services import chat_agent, chat_store, vault


@pytest.fixture()
def client(data_dir):
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------- chat_store
def test_session_crud_and_auto_title(data_dir):
    s = chat_store.create_session()
    assert s["title"] == "新对话"
    assert chat_store.list_sessions()[0]["id"] == s["id"]

    chat_store.append_message(s["id"], "user", "帮我整理 EDA 学习计划\n第二行")
    s2 = chat_store.get_session(s["id"])
    assert s2["title"] == "帮我整理 EDA 学习计划 第二行"
    assert len(s2["messages"]) == 1

    chat_store.append_message(s["id"], "assistant", "好的", tool_steps=[{"name": "search_notes", "args": {}, "summary": "x", "ok": True}])
    s3 = chat_store.get_session(s["id"])
    assert s3["messages"][-1]["tool_steps"][0]["name"] == "search_notes"

    chat_store.rename_session(s["id"], "自定义标题")
    assert chat_store.get_session(s["id"])["title"] == "自定义标题"

    chat_store.delete_session(s["id"])
    assert chat_store.list_sessions() == []
    with pytest.raises(HTTPException):
        chat_store.get_session(s["id"])


def test_drop_after_last_user(data_dir):
    s = chat_store.create_session()
    chat_store.append_message(s["id"], "user", "问题一")
    chat_store.append_message(s["id"], "assistant", "答一")
    chat_store.append_message(s["id"], "user", "问题二")
    chat_store.append_message(s["id"], "assistant", "答二")
    chat_store.drop_after_last_user(s["id"])
    msgs = chat_store.get_session(s["id"])["messages"]
    assert [m["role"] for m in msgs] == ["user", "assistant", "user"]
    assert msgs[-1]["content"] == "问题二"


# ---------------------------------------------------------------- notes/append
def test_notes_append_api(client):
    client.post("/api/topics", json={"name": "AI4EDA"})
    client.post("/api/notes", json={"path": "AI4EDA/大纲.md", "content": "# 大纲\n\n原有内容"})

    r = client.post("/api/notes/append", json={"path": "AI4EDA/大纲.md", "text": "新追加的一段"})
    assert r.status_code == 200
    body = client.get("/api/notes", params={"path": "AI4EDA/大纲.md"}).json()
    assert body["content"].startswith("# 大纲")
    assert "原有内容" in body["content"] and "新追加的一段" in body["content"]

    # 带小节标题
    client.post("/api/notes/append", json={"path": "AI4EDA/大纲.md", "text": "内容 B", "heading": "AI 补充"})
    body = client.get("/api/notes", params={"path": "AI4EDA/大纲.md"}).json()
    assert "## AI 补充" in body["content"] and "内容 B" in body["content"]

    # 不存在的笔记 → 404
    assert client.post("/api/notes/append", json={"path": "AI4EDA/不存在.md", "text": "x"}).status_code == 404


# ---------------------------------------------------------------- chat_agent 工具协议
def test_parse_and_strip_tool_call():
    text = "我先搜索一下。\n```json\n{\"tool\": \"search_notes\", \"args\": {\"q\": \"EDA\"}}\n```\n"
    call = chat_agent.parse_tool_call(text)
    assert call == {"tool": "search_notes", "args": {"q": "EDA"}}

    # 裸 JSON（没有代码围栏）也能解析；嵌套花括号不破坏边界
    bare = '好的。\n{"tool": "read_note", "args": {"path": "a.md"}}\n'
    assert chat_agent.parse_tool_call(bare)["tool"] == "read_note"

    # 白名单之外 / 非工具 json / 普通代码块都返回 None
    assert chat_agent.parse_tool_call("```json\n{\"tool\": \"delete_note\"}\n```") is None
    assert chat_agent.parse_tool_call("```json\n{\"a\": 1}\n```") is None
    assert chat_agent.parse_tool_call("没有工具调用") is None

    # strip 只去掉工具调用（连同围栏），保留普通代码块与正文
    mixed = "说明：\n```json\n{\"tool\": \"read_note\", \"args\": {\"path\": \"a.md\"}}\n```\n```python\nprint(1)\n```"
    stripped = chat_agent.strip_tool_calls(mixed)
    assert "read_note" not in stripped and "print(1)" in stripped and "说明：" in stripped
    assert "```json" not in stripped
    # 裸 JSON 也会被清掉
    assert chat_agent.strip_tool_calls(bare) == "好的。"


def test_execute_tool_whitelist_and_errors(data_dir):
    vault.create_note("机器学习/梯度下降.md", "# 梯度下降")

    ok, result, summary = chat_agent.execute_tool({"tool": "read_note", "args": {"path": "机器学习/梯度下降.md"}})
    assert ok and "梯度下降" in result

    ok, result, _ = chat_agent.execute_tool({"tool": "read_note", "args": {"path": "../etc/passwd"}})
    assert not ok and "执行失败" in result  # 越界路径 → 报错结果而非异常

    ok, result, _ = chat_agent.execute_tool({"tool": "search_notes", "args": {}})
    assert not ok and "参数缺失" in result

    # create → append → move 全链路
    chat_agent.execute_tool({"tool": "create_note", "args": {"path": "机器学习/新笔记.md", "content": "# 新"}})
    chat_agent.execute_tool({"tool": "append_to_note", "args": {"path": "机器学习/新笔记.md", "text": "追加", "heading": "AI"}})
    assert "追加" in vault.read_note("机器学习/新笔记.md")["content"]
    chat_agent.execute_tool({"tool": "move_note", "args": {"src": "机器学习/新笔记.md", "dst": "机器学习/改名.md"}})
    assert vault.read_note("机器学习/改名.md")["name"] == "改名"


def test_build_messages_injects_context(data_dir):
    vault.create_note("AI4EDA/大纲.md", "# 大纲正文")
    s = chat_store.create_session()
    chat_store.append_message(s["id"], "user", "这篇讲了什么？")
    msgs = chat_agent._build_messages(chat_store.get_session(s["id"]), ["AI4EDA/大纲.md", "不存在的笔记.md"])
    assert msgs[0]["role"] == "system" and "工具" in msgs[0]["content"]
    assert "大纲正文" in msgs[-1]["content"] and "这篇讲了什么" in msgs[-1]["content"]


def test_build_messages_injects_text_ref(data_dir):
    vault.create_note("AI4EDA/大纲.md", "# 大纲正文")
    s = chat_store.create_session()
    chat_store.append_message(s["id"], "user", "这段怎么理解？")
    good = 'text:{"t": "被选中的段落", "s": "AI4EDA/大纲"}'
    bad = "text:{broken json"
    msgs = chat_agent._build_messages(chat_store.get_session(s["id"]),
                                      ["AI4EDA/大纲.md", good, bad, "text:{\"t\": \"  \"}"])
    tail = msgs[-1]["content"]
    assert "大纲正文" in tail  # 笔记引用照常注入
    assert "被选中的段落" in tail and "来自《AI4EDA/大纲》" in tail  # 行内文字引用注入
    assert "broken json" not in tail  # 坏 JSON 引用被跳过
    assert "这段怎么理解" in tail


# ---------------------------------------------------------------- 章节（chunk）
SECTION_DOC = """# 学习大纲

## 模块一 基础

模块一的内容。

```
## 假标题在围栏里
```

围栏结束后回到正文。

## 模块二 进阶

模块二的内容。

### 模块二小节

小节内容。
"""


def test_extract_section():
    body = chat_agent._extract_section(SECTION_DOC, "模块一 基础")
    assert "模块一的内容" in body and "假标题在围栏里" in body  # 围栏内不算标题边界
    assert "模块二" not in body

    body2 = chat_agent._extract_section(SECTION_DOC, "模块二 进阶")
    assert "模块二的内容" in body2 and "小节内容" in body2  # 低级标题不截断

    assert chat_agent._extract_section(SECTION_DOC, "不存在的章节") == ""


def test_tools_read_sections(data_dir):
    vault.create_note("AI4EDA/大纲.md", SECTION_DOC)

    ok, result, _ = chat_agent.execute_tool({"tool": "list_sections", "args": {"path": "AI4EDA/大纲.md"}})
    assert ok and "模块一 基础" in result and "模块二小节" in result

    ok, result, summary = chat_agent.execute_tool(
        {"tool": "read_note", "args": {"path": "AI4EDA/大纲.md", "section": "模块二 进阶"}})
    assert ok and "模块二的内容" in result and "小节内容" in result
    assert "模块二 进阶" in summary

    ok, result, _ = chat_agent.execute_tool(
        {"tool": "read_note", "args": {"path": "AI4EDA/大纲.md", "section": "没有这节"}})
    assert not ok and "未找到章节" in result


def test_build_messages_section_context(data_dir):
    vault.create_note("AI4EDA/大纲.md", SECTION_DOC)
    s = chat_store.create_session()
    chat_store.append_message(s["id"], "user", "模块二讲什么？")
    msgs = chat_agent._build_messages(chat_store.get_session(s["id"]), ["AI4EDA/大纲.md#模块二 进阶"])
    tail = msgs[-1]["content"]
    assert "模块二的内容" in tail and "AI4EDA/大纲.md · 模块二 进阶" in tail
    assert "模块一的内容" not in tail  # 只注入该章节


"""AI 对话的 agent 层：白名单工具（对齐 mcp_servers 已有接口语义）+ 流式轮次循环。

工具协议与 provider 无关：系统提示约定模型用 ```json {"tool": "...", "args": {...}}```
发起调用，本层解析、执行（白名单，无删除类工具），把结果以 [TOOL_RESULT] 回灌，
直到模型给出最终回答或达到轮次上限。
"""
import json
import re
from typing import AsyncIterator, Dict, List, Optional, Tuple

from fastapi import HTTPException

from . import chat_store, vault
from .llm_service import stream_llm

MAX_TOOL_ROUNDS = 6
HISTORY_WINDOW = 20          # 送入模型的历史消息条数
CONTEXT_NOTE_CHARS = 6000    # 单篇引用笔记注入上限
TOOL_RESULT_CHARS = 4000     # 单次工具结果回灌上限
MAX_CONTEXT_NOTES = 4        # 单轮最多引用笔记篇数
TEXT_REF_PREFIX = "text:"    # 行内文字引用前缀（阅读器划选「加入对话」），后缀为 JSON
MAX_CONTEXT_SNIPPETS = 4     # 单轮最多行内文字引用条数
CONTEXT_TEXT_CHARS = 4000    # 单条行内文字注入上限

TOOL_DOCS = """\
- list_topics(): 列出笔记库全部主题（名称、笔记数）。
- search_notes(q, topic?, limit?): 全文搜索笔记，返回路径、标题与摘要。
- list_sections(path): 列出一篇笔记的章节标题（h2/h3，即内容分块 chunk）。
- read_note(path, section?): 读取笔记全文；给 section（章节标题）时只返回该章节内容，省 token。
- create_note(path, content, overwrite=false): 新建笔记，path 形如「主题/标题.md」。
- append_to_note(path, text, heading?): 把一段 Markdown 追加到笔记末尾，heading 为可选小节标题。
- move_note(src, dst): 移动或重命名笔记。"""

SYSTEM_PROMPT = f"""你是 NoteLink 笔记库中的 AI 助手。回答使用 GitHub 风格 Markdown，数学公式用 LaTeX（$...$ / $$...$$）。你可以使用以下工具读写笔记库：

{TOOL_DOCS}

工具调用协议：
- 需要获取库内信息或执行操作时，在回复中单独输出一个完整的 json 代码块（必须闭合）：
  ```json
  {{"tool": "工具名", "args": {{"参数": "值"}}}}
  ```
- 输出该代码块后立即停笔，等待系统把 [TOOL_RESULT] 结果回给你，再继续回答；不要在同一条消息里既调用工具又给出最终结论。
- 系统会执行该工具，并以 [TOOL_RESULT] 开头的消息把结果回给你，之后请继续回答或发起下一次调用。
- 单轮对话最多连续调用 {MAX_TOOL_ROUNDS} 次工具。执行写操作（新建/追加/移动）前，先用一句话向用户说明你要做什么。
- 不需要工具时直接回答，不要输出 json 代码块。"""

# ---------------------------------------------------------------- 工具白名单
def _t_list_topics(args: Dict) -> Tuple[str, str]:
    topics = vault.list_topics()
    lines = [f"- {t['name']}（{t['note_count']} 篇）" for t in topics]
    return "\n".join(lines) or "（库内还没有主题）", f"共 {len(topics)} 个主题"


def _t_search_notes(args: Dict) -> Tuple[str, str]:
    q = str(args.get("q") or "").strip()
    if not q:
        raise ValueError("缺少参数 q")
    topic = str(args.get("topic") or "")
    limit = min(int(args.get("limit") or 8), 20)
    results = vault.search_vault(q, topic, limit)
    if not results:
        return "（无搜索结果）", f"「{q}」无结果"
    lines = [f"- {r['path']}（{r['title']}）：{r['snippet'][:120]}" for r in results]
    return "\n".join(lines), f"命中 {len(results)} 条"


def _t_read_note(args: Dict) -> Tuple[str, str]:
    path = str(args.get("path") or "").strip()
    if not path:
        raise ValueError("缺少参数 path")
    note = vault.read_note(path)
    section = str(args.get("section") or "").strip()
    if section:
        body = _extract_section(note["content"], section)
        if not body:
            raise ValueError(f"未找到章节「{section}」，可先用 list_sections 查看章节列表")
        return body[:TOOL_RESULT_CHARS], f"读取 {note['path']} · {section}（{len(body)} 字）"
    content = note["content"][:TOOL_RESULT_CHARS]
    if len(note["content"]) > TOOL_RESULT_CHARS:
        content += "\n…（内容过长已截断，可用 list_sections 按章节读取）"
    return content, f"读取 {note['path']}（{len(note['content'])} 字）"


_HEADING_RX = re.compile(r"^(#{2,3})\s+(.+?)\s*#*\s*$")


def _extract_section(content: str, title: str) -> str:
    """取 h2/h3 章节的完整内容（标题行到下一个同级/更高级标题之前），跳过代码围栏。"""
    lines = content.split("\n")
    in_code = False
    start, level = -1, 2
    for i, line in enumerate(lines):
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = _HEADING_RX.match(line)
        if not m:
            continue
        if start == -1:
            if m.group(2).strip() == title.strip():
                start, level = i, len(m.group(1))
        elif len(m.group(1)) <= level:
            return "\n".join(lines[start:i]).rstrip()
    return "\n".join(lines[start:]).rstrip() if start >= 0 else ""


def _t_list_sections(args: Dict) -> Tuple[str, str]:
    path = str(args.get("path") or "").strip()
    if not path:
        raise ValueError("缺少参数 path")
    note = vault.read_note(path)
    in_code = False
    heads = []
    for line in note["content"].split("\n"):
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        m = _HEADING_RX.match(line)
        if m:
            heads.append(f"- {'  ' * (len(m.group(1)) - 2)}{m.group(2).strip()}")
    if not heads:
        return "（该笔记没有 h2/h3 章节标题）", f"{path} 无章节"
    return "\n".join(heads), f"{path} 共 {len(heads)} 个章节"


def _t_create_note(args: Dict) -> Tuple[str, str]:
    path = str(args.get("path") or "").strip()
    if not path:
        raise ValueError("缺少参数 path")
    note = vault.create_note(path, str(args.get("content") or ""), overwrite=bool(args.get("overwrite")))
    return f"已创建 {note['path']}", f"已创建 {note['path']}"


def _t_append_to_note(args: Dict) -> Tuple[str, str]:
    path = str(args.get("path") or "").strip()
    text = str(args.get("text") or "").strip()
    if not path or not text:
        raise ValueError("缺少参数 path / text")
    note = vault.append_to_note(path, text, str(args.get("heading") or ""))
    return f"已追加到 {note['path']}", f"已追加 {len(text)} 字到 {note['path']}"


def _t_move_note(args: Dict) -> Tuple[str, str]:
    src = str(args.get("src") or "").strip()
    dst = str(args.get("dst") or "").strip()
    if not src or not dst:
        raise ValueError("缺少参数 src / dst")
    note = vault.move_note(src, dst)
    return f"已移动到 {note['path']}", f"{src} → {note['path']}"


# name → (必填参数, 执行函数)
TOOLS = {
    "list_topics": ((), _t_list_topics),
    "search_notes": (("q",), _t_search_notes),
    "list_sections": (("path",), _t_list_sections),
    "read_note": (("path",), _t_read_note),
    "create_note": (("path",), _t_create_note),
    "append_to_note": (("path", "text"), _t_append_to_note),
    "move_note": (("src", "dst"), _t_move_note),
}


def _find_tool_call(text: str) -> Optional[Dict]:
    """定位最后一个工具调用：从 '"tool"' 反推 JSON 对象边界（括号配平，容忍嵌套与裸 JSON）。"""
    key = text.rfind('"tool"')
    if key < 0:
        return None
    start = text.rfind("{", 0, key)
    if start < 0:
        return None
    depth, in_str, esc = 0, False, False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    data = json.loads(text[start: i + 1])
                except json.JSONDecodeError:
                    return None
                if isinstance(data, dict) and data.get("tool") in TOOLS:
                    args = data.get("args")
                    return {"tool": data["tool"], "args": args if isinstance(args, dict) else {},
                            "span": (start, i + 1)}
                return None
    return None


def _span_with_fences(text: str, span: Tuple[int, int]) -> Tuple[int, int]:
    """把 JSON span 向两侧扩展到相邻的代码围栏（```json ... ```）。"""
    s, e = span
    m = re.search(r"```(?:json)?\s*$", text[:s])
    if m:
        s = m.start()
    m2 = re.match(r"\s*```", text[e:])
    if m2:
        e += m2.end()
    return s, e


def parse_tool_call(text: str) -> Optional[Dict]:
    """从模型输出里解析最后一个合法的工具调用（容忍围栏缺失、嵌套花括号）。"""
    found = _find_tool_call(text)
    if not found:
        return None
    return {"tool": found["tool"], "args": found["args"]}


def strip_tool_calls(text: str) -> str:
    """去掉已执行的工具调用 JSON（连同相邻围栏），保留其余内容（普通代码示例不受影响）。"""
    for _ in range(8):
        found = _find_tool_call(text)
        if not found:
            break
        s, e = _span_with_fences(text, found["span"])
        text = text[:s] + text[e:]
    # 清掉删除后残留的空围栏与多余空行
    text = re.sub(r"```(?:json)?\s*```", "", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


def execute_tool(call: Dict) -> Tuple[bool, str, str]:
    """执行白名单工具，返回 (是否成功, 给模型的结果, 给用户看的摘要)。工具报错不中断会话。"""
    name, args = call["tool"], call["args"]
    required, fn = TOOLS[name]
    missing = [k for k in required if not str(args.get(k) or "").strip()]
    if missing:
        return False, f"参数缺失：{', '.join(missing)}", f"{name} 参数缺失"
    try:
        result, summary = fn(args)
        return True, result[:TOOL_RESULT_CHARS], summary
    except HTTPException as e:
        return False, f"执行失败：{e.detail}", f"{name} 失败：{e.detail}"
    except ValueError as e:
        return False, f"执行失败：{e}", f"{name} 失败：{e}"
    except Exception as e:  # noqa: BLE001
        return False, f"执行失败：{e}", f"{name} 失败"


# ---------------------------------------------------------------- 轮次循环
def parse_text_ref(ref: str) -> Optional[Dict]:
    """解析行内文字引用：text:{"t": 选中文字, "s": 来源笔记}。坏 JSON / 空文本返回 None。"""
    if not ref.startswith(TEXT_REF_PREFIX):
        return None
    try:
        data = json.loads(ref[len(TEXT_REF_PREFIX):])
        text = str(data.get("t") or "")
        if not text.strip():
            return None
        return {"text": text, "source": str(data.get("s") or "")}
    except (json.JSONDecodeError, ValueError, TypeError):
        return None


def _build_messages(session: Dict, context_paths: List[str]) -> List[Dict]:
    """系统提示 + 历史窗口 + 引用内容注入后的当前提问。最后一条须为用户消息。

    引用格式：笔记路径 / 路径#章节标题（只注入该章节 chunk）/
    text:{"t": 选中文字, "s": 来源}（阅读器划选「加入对话」的原文）。
    """
    msgs = session["messages"]
    if not msgs or msgs[-1]["role"] != "user":
        raise HTTPException(status_code=400, detail="会话末尾不是用户提问")
    out: List[Dict] = [{"role": "system", "content": SYSTEM_PROMPT}]
    for m in msgs[-HISTORY_WINDOW - 1: -1]:
        out.append({"role": m["role"], "content": m["content"]})
    ctx_blocks = []
    note_refs = [r for r in context_paths if not r.startswith(TEXT_REF_PREFIX)]
    for ref in note_refs[:MAX_CONTEXT_NOTES]:
        # 引用格式：笔记路径 或 路径#章节标题（只注入该章节 chunk）
        path, _, section = ref.partition("#")
        path = path.strip()
        section = section.strip()
        try:
            note = vault.read_note(path)
        except HTTPException:
            continue  # 引用的笔记被删了就跳过，不阻塞对话
        body = note["content"]
        label = note["path"]
        if section:
            body = _extract_section(body, section)
            if not body:
                continue  # 章节不存在（可能已被删）就跳过
            label = f"{note['path']} · {section}"
        ctx_blocks.append(f"### {label}\n\n{body[:CONTEXT_NOTE_CHARS]}")
    text_refs = [parse_text_ref(r) for r in context_paths]
    for snip in [s for s in text_refs if s][:MAX_CONTEXT_SNIPPETS]:
        label = "### 用户选中的文字"
        if snip["source"]:
            label += f"（来自《{snip['source']}》）"
        ctx_blocks.append(f"{label}\n\n{snip['text'][:CONTEXT_TEXT_CHARS]}")
    content = msgs[-1]["content"]
    if ctx_blocks:
        preamble = "以下是用户引用的内容：\n\n" + "\n\n---\n\n".join(ctx_blocks) + "\n\n---\n\n用户的问题："
        content = preamble + content
    out.append({"role": "user", "content": content})
    return out


async def run_turn(session_id: str, context_paths: List[str],
                   provider_id: str = "", model: str = "",
                   temperature: Optional[float] = None) -> AsyncIterator[Dict]:
    """执行一轮对话：流式输出 → 检出工具调用则执行回灌 → 循环 → 落库 → done。

    事件：delta（增量文本）/ tool（status=start|done）/ done（带会话元信息与新消息）/ error。
    """
    session = chat_store.get_session(session_id)
    messages = _build_messages(session, context_paths)

    full_text = ""
    tool_steps: List[Dict] = []
    for round_no in range(MAX_TOOL_ROUNDS + 1):
        buf = ""
        async for delta in stream_llm(provider_id, messages, model, temperature):
            buf += delta
            yield {"type": "delta", "text": delta}
        full_text += buf
        call = parse_tool_call(buf)
        if call is None or round_no == MAX_TOOL_ROUNDS:
            break
        yield {"type": "tool", "name": call["tool"], "args": call["args"], "status": "start"}
        ok, result, summary = execute_tool(call)
        tool_steps.append({"name": call["tool"], "args": call["args"], "summary": summary, "ok": ok})
        yield {"type": "tool", "name": call["tool"], "args": call["args"],
               "status": "done", "ok": ok, "summary": summary}
        messages.append({"role": "assistant", "content": buf})
        messages.append({"role": "user", "content": f"[TOOL_RESULT] {call['tool']} →\n{result}\n\n请继续。"})

    display = strip_tool_calls(full_text).strip()
    session = chat_store.append_message(session_id, "assistant", display, tool_steps=tool_steps or None)
    yield {
        "type": "done",
        "session": chat_store._meta(session),
        "message": session["messages"][-1],
    }

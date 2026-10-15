"""AI 对话的 agent 层：白名单工具（对齐 mcp_servers 已有接口语义）+ 流式轮次循环。

工具协议与 provider 无关：系统提示约定模型用 ```json {"tool": "...", "args": {...}}```
发起调用，本层解析、执行（白名单，无删除类工具），把结果以 [TOOL_RESULT] 回灌，
直到模型给出最终回答或达到轮次上限。
"""
import asyncio
import json
import re
from concurrent.futures import ThreadPoolExecutor
from typing import AsyncIterator, Dict, List, Optional, Tuple

from fastapi import HTTPException

from . import chat_store, mcp_client, vault, websearch_service
from .llm_service import complete, stream_llm

MAX_TOOL_ROUNDS = 6
HISTORY_WINDOW = 20          # 送入模型的历史消息条数
CONTEXT_NOTE_CHARS = 6000    # 单篇引用笔记注入上限
TOOL_RESULT_CHARS = 4000     # 单次工具结果回灌上限
MAX_CONTEXT_NOTES = 4        # 单轮最多引用笔记篇数
TEXT_REF_PREFIX = "text:"    # 行内文字引用前缀（阅读器划选「加入对话」），后缀为 JSON
MAX_CONTEXT_SNIPPETS = 4     # 单轮最多行内文字引用条数
CONTEXT_TEXT_CHARS = 4000    # 单条行内文字注入上限
TITLE_MAX_CHARS = 24         # 建议笔记标题长度上限（对齐文件名习惯）
NOTE_TITLE_TIMEOUT = 12      # 标题生成兜底超时（秒），超时/失败静默降级

TOOL_DOCS = """\
- list_topics(): 列出笔记库全部主题（名称、笔记数）。
- search_notes(q, topic?, limit?): 全文搜索笔记，返回路径、标题与摘要。
- list_sections(path): 列出一篇笔记的章节标题（h2/h3，即内容分块 chunk）。
- read_note(path, section?): 读取笔记全文；给 section（章节标题）时只返回该章节内容，省 token。
- create_note(path, content, overwrite=false): 新建笔记，path 形如「主题/标题.md」。
- append_to_note(path, text, heading?): 把一段 Markdown 追加到笔记末尾，heading 为可选小节标题。
- move_note(src, dst): 移动或重命名笔记。
- web_search(q): 联网搜索最新资料（需在「设置 → 联网搜索」启用并配置服务商），返回标题、链接与摘要。
- mcp_tool(server, tool, args?): 调用「设置 → MCP 服务器」里已配置且启用的外部 MCP 工具（典型：web search MCP）；server 为服务器 id，args 为可选的 JSON 对象参数。
- fetch_webpage(url): 抓取一个网页的正文文本，用于展开搜索结果里的链接。
- add_note_link(path, url, title?, source?): 把参考链接存入一篇笔记的 frontmatter（写操作，执行前先告知用户）。"""

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


def _run_async(coro) -> dict:
    """在同步工具里跑异步协程：工具执行发生在事件循环线程内，不能直接
    run_until_complete，放到工作线程用 asyncio.run 执行。"""
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(asyncio.run, coro).result()


def _t_web_search(args: Dict) -> Tuple[str, str]:
    q = str(args.get("q") or "").strip()
    if not q:
        raise ValueError("缺少参数 q")
    if not websearch_service.is_enabled():
        return "联网搜索未启用：请先在「设置 → 联网搜索」中启用并配置搜索服务商。", "web_search 未启用"
    data = _run_async(websearch_service.search(q))
    results = data.get("results") or []
    if not results:
        return f"（「{q}」没有搜索结果）", f"「{q}」无结果"
    lines = [
        f"- {r.get('title') or r.get('url')}\n  {r.get('url')}\n  {(r.get('snippet') or '').strip()}"
        for r in results
    ]
    return "\n".join(lines)[:TOOL_RESULT_CHARS], f"命中 {len(results)} 条"


def _t_fetch_webpage(args: Dict) -> Tuple[str, str]:
    url = str(args.get("url") or "").strip()
    if not url:
        raise ValueError("缺少参数 url")
    page = _run_async(websearch_service.fetch_webpage(url))
    text = f"标题：{page.get('title')}\n\n正文：\n{page.get('text')}"
    return text[:TOOL_RESULT_CHARS], f"抓取 {url}"


def _t_mcp_tool(args: Dict) -> Tuple[str, str]:
    server = str(args.get("server") or "").strip()
    tool = str(args.get("tool") or "").strip()
    extra = args.get("args") if isinstance(args.get("args"), dict) else {}
    if not server or not tool:
        raise ValueError("缺少参数 server / tool")
    try:
        result = mcp_client.call_tool(server, tool, extra)
    except mcp_client.MCPError as e:
        return (f"调用失败：{e}。请检查「设置 → MCP 服务器」里该服务器已配置、启用且命令可启动。",
                f"mcp_tool 失败：{tool}")
    text = "\n".join(c.get("text", "") for c in result.get("content") or [] if isinstance(c, dict))
    if result.get("isError"):
        return text or "（MCP 工具返回错误，但没有给出内容）", f"mcp_tool 错误：{tool}"
    return text or "（MCP 工具无返回）", f"mcp_tool {tool} 完成"


def _t_add_note_link(args: Dict) -> Tuple[str, str]:
    path = str(args.get("path") or "").strip()
    url = str(args.get("url") or "").strip()
    if not path or not url:
        raise ValueError("缺少参数 path / url")
    vault.add_note_link(path, str(args.get("title") or ""), url, str(args.get("source") or "manual"))
    return f"已添加参考链接：{url}（{path}）", f"已添加链接到 {path}"


# name → (必填参数, 执行函数)
TOOLS = {
    "list_topics": ((), _t_list_topics),
    "search_notes": (("q",), _t_search_notes),
    "list_sections": (("path",), _t_list_sections),
    "read_note": (("path",), _t_read_note),
    "create_note": (("path",), _t_create_note),
    "append_to_note": (("path", "text"), _t_append_to_note),
    "move_note": (("src", "dst"), _t_move_note),
    "web_search": (("q",), _t_web_search),
    "fetch_webpage": (("url",), _t_fetch_webpage),
    "mcp_tool": (("server", "tool"), _t_mcp_tool),
    "add_note_link": (("path", "url"), _t_add_note_link),
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
async def generate_note_title(question: str, provider_id: str = "", model: str = "",
                              temperature: Optional[float] = None) -> str:
    """把用户提问浓缩成一句笔记标题，用于预填「存为笔记」的标题框。

    只依据提问（与回答流并行生成，不增加回答等待）；超时或失败返回空串。
    """
    prompt = (
        "请根据下面的提问为对应回答起一个笔记标题：16 字以内、名词式的词条名"
        "（像百科词条，不要照抄提问的问句），适合直接当文件名——"
        "不要书名号、引号、句末标点和斜杠，只输出标题本身，不要任何解释或前缀。"
        "例：提问「用一句话说明什么是极限」→ 标题「极限的定义」。\n\n提问：" + question[:500]
    )
    try:
        text = await asyncio.wait_for(
            complete(provider_id, [{"role": "user", "content": prompt}], model, temperature),
            timeout=NOTE_TITLE_TIMEOUT,
        )
    except Exception:  # noqa: BLE001 — 标题只是建议，失败静默
        return ""
    line = text.strip().splitlines()[0].strip() if text.strip() else ""
    line = re.sub(r"^(?:标题|题目|建议标题)\s*[:：]\s*", "", line)
    line = line.strip(" \t# 《》「」『』“”\"'。．.！!？?…、，,/\\")
    return line[:TITLE_MAX_CHARS]


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
    done 的 message 带 note_title（依据提问并行生成的建议笔记标题，可为空）。
    """
    session = chat_store.get_session(session_id)
    messages = _build_messages(session, context_paths)

    # 提问一落地就并行发起建议标题生成（与回答流同跑），done 事件带回给前端预填「存为笔记」
    question = session["messages"][-1]["content"]
    title_task = (asyncio.create_task(generate_note_title(question, provider_id, model, temperature))
                  if question.strip() else None)

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
    note_title = ""
    if title_task is not None:
        try:
            note_title = await title_task
        except Exception:  # noqa: BLE001 — 标题失败不影响回答落库
            note_title = ""
    session = chat_store.append_message(session_id, "assistant", display,
                                        tool_steps=tool_steps or None, note_title=note_title)
    yield {
        "type": "done",
        "session": chat_store._meta(session),
        "message": session["messages"][-1],
    }

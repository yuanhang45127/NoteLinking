"""共享的 AI 生成流程：产出统一「调用过程」事件流。

每条流程都是一个 async generator，依次 yield process 约定的事件
（llm_start/delta/llm_done/tool/step/done/error）。供三处复用：
    1. 各路由的 SSE 端点（llm.py / terms.py / exams.py）
    2. 服务端后台任务（routers/ai_tasks.py 的 op 注册表）
    3. 未来新增入口（保证过程展示行为一致）

done 事件的字段保持与旧版一致（saved_path / markdown / created / failed …），
前端旧逻辑不受影响，只是额外多了过程事件。
"""
import datetime
from typing import AsyncIterator, Dict, List

from ..markdown_utils import append_section, ensure_frontmatter
from . import arch_service, term_service, vault
from . import process

NOTE_SYSTEM = (
    "你是专业的学习笔记作者。请输出 GitHub 风格 Markdown 笔记正文（不要输出 frontmatter，"
    "不要用代码围栏包住全文）。要求：结构清晰（用 ## 分节）、重点突出、"
    "数学公式用 LaTeX（行内 $...$、独立 $$...$$）、代码用代码块、"
    "关键术语首次出现可用 [[术语]] 双链语法标注。"
    "若用户开启联网搜索，可适当补充资料中的最新进展，并在文末用 `## 参考来源` 小节"
    "以 Markdown 列表列出用到的来源 URL。"
    "事实红线：涉及论文/技术归属（谁提出、哪个团队）、引用关系（谁引用谁）、发表会议或期刊与年份、"
    "数据集规模数字，以及“首个/最大/SOTA/显著优于”类结论时，必须只依据用户提供的资料或联网来源的原文，"
    "不得凭常识推断或补全；资料中没有依据的，明确写「资料未提供依据」并标注 [待核]，"
    "不要用模糊表述掩盖不确定。"
)

ASK_SYSTEM = (
    "你是耐心的学习助手。用户在阅读笔记时选中了一段看不懂的内容，"
    "请结合上下文用平实的语言讲解，必要时举例或补充背景。"
    "涉及论文归属、引用关系、venue/年份、规模数字等事实时，只依据资料原文，"
    "资料中没有的注明「资料未提供依据」，不要推断。"
)


def _lang(language: str) -> str:
    return "中文" if language == "zh" else language


def _web_query_from_paths(paths: List[str]) -> str:
    """由笔记路径提取主题词作联网搜索 query（去掉目录与 .md 后缀）。"""
    names = [p.rsplit("/", 1)[-1] for p in paths]
    query = " ".join(n[:-3] if n.lower().endswith(".md") else n for n in names)
    return query.strip()[:100]


def save_generated(title: str, text: str, save_path: str, language: str) -> Dict:
    fm = {"title": title.strip() or "未命名笔记", "generated": True,
          "created": datetime.date.today().isoformat()}
    content = ensure_frontmatter(f"# {fm['title']}\n", fm) + text.strip() + "\n"
    return vault.create_note(save_path, content, overwrite=False)


def _backfill_web_links(saved_path: str, text: str, web_results: List[Dict]) -> None:
    """生成正文里用到的搜索来源，回填为笔记参考链接（frontmatter links）；失败不影响生成。"""
    for r in web_results:
        url = r.get("url") or ""
        if url and url in text:
            try:
                vault.add_note_link(saved_path, r.get("title") or url, url, source="web_search")
            except Exception:  # noqa: BLE001
                pass


async def _web_block(payload: Dict, query: str, sink: List):
    """按 payload.use_web 执行联网搜索步骤；sink = [block, results] 供调用方回传取用。"""
    sink.clear()
    sink.extend(["", []])
    async for ev in process.web_context_step(query, bool(payload.get("use_web"))):
        if ev.get("type") == "tool" and ev.get("status") == "done":
            p = process.take_payload(ev)
            sink[0], sink[1] = p.get("_block", ""), p.get("_results", [])
        yield process.strip_internal(ev)


# ---------------------------------------------------------------- 通用对话
async def chat_stream_events(payload: Dict) -> AsyncIterator[Dict]:
    messages = [{"role": m.get("role") if m.get("role") in ("system", "user", "assistant") else "user",
                 "content": m.get("content") or ""}
                for m in payload.get("messages") or []]
    async for ev in process.llm_call(payload.get("provider") or "", messages,
                                     payload.get("model") or "", payload.get("temperature"),
                                     purpose="对话"):
        yield ev
    yield {"type": "done"}


# ---------------------------------------------------------------- 笔记生成
async def note_events(payload: Dict) -> AsyncIterator[Dict]:
    title = (payload.get("title") or "").strip()
    prompt = payload.get("prompt") or ""
    language = _lang(payload.get("language") or "zh")
    user = (f"笔记标题：《{title}》\n" if title else "") + \
        f"请围绕以下要求写一篇{language}学习笔记：\n\n{prompt}"

    web_sink: List = ["", []]
    q = f"{title} {prompt}".strip()
    async for ev in _web_block(payload, q, web_sink):
        yield ev
    if web_sink[0]:
        user += web_sink[0]
    messages = [
        {"role": "system", "content": NOTE_SYSTEM + f"全文使用{language}。"},
        {"role": "user", "content": user},
    ]
    buf = ""
    async for ev in process.llm_call(payload.get("provider") or "", messages,
                                     payload.get("model") or "", None,
                                     purpose="生成笔记正文"):
        if ev["type"] == "delta":
            buf += ev["text"]
        yield ev
    save_path = payload.get("save_path") or ""
    if save_path:
        yield process.step("save", "start", "保存笔记", save_path)
        saved = save_generated(title or prompt[:30], buf, save_path, payload.get("language") or "zh")
        _backfill_web_links(saved["path"], buf, web_sink[1])
        yield process.step("save", "done", "保存笔记", saved["path"])
        yield {"type": "done", "saved_path": saved["path"]}
        return
    yield {"type": "done"}


# ---------------------------------------------------------------- 划选提问
async def ask_events(payload: Dict) -> AsyncIterator[Dict]:
    path = payload.get("path") or ""
    note = vault.read_note(path)
    language = payload.get("language") or "zh"
    lang = "请用中文回答。" if language == "zh" else f"请用 {language} 回答。"
    before = (payload.get("context_before") or "").strip()[-800:]
    after = (payload.get("context_after") or "").strip()[:800]
    question = (payload.get("question") or "").strip()
    selected = (payload.get("selected_text") or "").strip()
    q = f"（针对选中内容的）问题：{question}" if question else "请讲解选中的内容。"
    user = (
        f"我在读笔记《{note['name']}》。选中内容的前后文如下：\n\n"
        f"……{before}\n【选中】{selected}\n{after}……\n\n{q}\n\n{lang}"
    )
    messages = [
        {"role": "system", "content": ASK_SYSTEM + lang},
        {"role": "user", "content": user},
    ]
    buf = ""
    async for ev in process.llm_call(payload.get("provider") or "", messages,
                                     payload.get("model") or "", None,
                                     purpose="讲解选中内容"):
        if ev["type"] == "delta":
            buf += ev["text"]
        yield ev
    if payload.get("save_to_note"):
        heading = f"问答记录（{datetime.datetime.now().isoformat(timespec='seconds')}）"
        qa = (f"**问：** {question or '讲解选中内容'}\n\n> {selected}\n\n"
              f"**答：**\n\n{buf.strip()}")
        saved = vault.save_note(path, append_section(note["content"], heading, qa), _force=True)
        yield {"type": "done", "saved_path": saved["path"]}
        return
    yield {"type": "done"}


# ---------------------------------------------------------------- 备考助教
async def tutor_events(payload: Dict) -> AsyncIterator[Dict]:
    from .exam_service import gather_context

    context, used = gather_context(payload.get("paths") or [])
    language = _lang(payload.get("language") or "zh")
    system = (
        f"你是学生的备考 AI 助教。以下是学生勾选的资料（{', '.join(used)}），"
        f"回答务必基于资料、直指考点，使用{language}，公式用 LaTeX。\n\n{context}"
    )
    last_user = ""
    for m in reversed(payload.get("messages") or []):
        if m.get("role") == "user":
            last_user = m.get("content") or ""
            break
    web_sink: List = ["", []]
    async for ev in _web_block(payload, last_user.strip()[:100], web_sink):
        yield ev
    if web_sink[0]:
        system += web_sink[0]
    history = [{"role": m.get("role") if m.get("role") in ("system", "user", "assistant") else "user",
                "content": m.get("content") or ""}
               for m in (payload.get("messages") or [])][-12:]
    messages = [{"role": "system", "content": system}] + history
    async for ev in process.llm_call(payload.get("provider") or "", messages,
                                     payload.get("model") or "", payload.get("temperature"),
                                     purpose="备考助教"):
        yield ev
    yield {"type": "done"}


# ---------------------------------------------------------------- 学习指南
async def study_guide_events(payload: Dict) -> AsyncIterator[Dict]:
    from .exam_service import _guide_messages

    messages = _guide_messages(payload.get("paths") or [], payload.get("language") or "zh")
    web_sink: List = ["", []]
    async for ev in _web_block(payload, _web_query_from_paths(payload.get("paths") or []), web_sink):
        yield ev
    if web_sink[0]:
        messages[-1]["content"] += web_sink[0]
    buf = ""
    async for ev in process.llm_call(payload.get("provider") or "", messages,
                                     payload.get("model") or "", None,
                                     purpose="生成学习指南"):
        if ev["type"] == "delta":
            buf += ev["text"]
        yield ev
    done: Dict = {"type": "done", "markdown": buf}
    save_path = payload.get("save_path") or ""
    if save_path:
        yield process.step("save", "start", "保存学习指南", save_path)
        fm = {"generated": True, "created": datetime.date.today().isoformat()}
        saved = vault.create_note(save_path, ensure_frontmatter(buf, fm), overwrite=False)
        yield process.step("save", "done", "保存学习指南", saved["path"])
        done["saved_path"] = saved["path"]
    yield done


# ---------------------------------------------------------------- 主题架构
async def arch_events(payload: Dict) -> AsyncIterator[Dict]:
    topic = payload.get("topic") or ""
    overview = arch_service.topic_overview(topic)
    messages = arch_service.arch_messages(overview, payload.get("goal") or "")
    web_sink: List = ["", []]
    async for ev in _web_block(payload, (payload.get("goal") or "").strip() or topic, web_sink):
        yield ev
    if web_sink[0]:
        messages[-1]["content"] += web_sink[0]
    title = f"{topic} · 整体架构"
    save_path = payload.get("save_path") or f"{topic}/_架构/整体架构.md"
    buf = ""
    async for ev in process.llm_call(payload.get("provider") or "", messages,
                                     payload.get("model") or "", None,
                                     purpose="生成整体架构"):
        if ev["type"] == "delta":
            buf += ev["text"]
        yield ev
    yield process.step("save", "start", "保存架构文档", save_path)
    fm = {"title": title, "generated": True, "created": datetime.date.today().isoformat()}
    content = ensure_frontmatter(f"# {title}\n", fm) + buf.strip() + "\n"
    saved = vault.create_note(save_path, content, overwrite=True)
    yield process.step("save", "done", "保存架构文档", saved["path"])
    yield {"type": "done", "saved_path": saved["path"]}


async def arch_notes_events(payload: Dict) -> AsyncIterator[Dict]:
    """按整体架构提纲逐篇生成笔记（note_start/note_done 事件保持旧协议）。"""
    from fastapi import HTTPException

    topic = payload.get("topic") or ""
    chains = arch_service.arch_leaf_chains(topic, payload.get("save_path") or "")
    provider, model = payload.get("provider") or "", payload.get("model") or ""
    total = len(chains)
    yield {"type": "start", "total": total}
    created = failed = 0
    for i, chain in enumerate(chains):
        title = chain[-1]
        rel = f"{topic}/{'/'.join(chain)}/{title}.md"
        yield {"type": "note_start", "index": i, "total": total, "title": title}
        try:
            try:
                vault.read_note(rel)
                yield {"type": "note_skip", "index": i, "title": title, "reason": "已存在，跳过"}
                continue
            except HTTPException as e:
                if e.status_code != 404:
                    raise
            legacy = f"{topic}/{'/'.join(chain)}.md"
            try:
                vault.move_note(legacy, rel)
                yield {"type": "note_skip", "index": i, "title": title, "reason": "旧位置笔记已移入文件夹"}
                continue
            except HTTPException:
                pass
            messages = arch_service.leaf_note_messages(topic, chain)
            text = ""
            async for ev in process.llm_call(provider, messages, model, None,
                                             purpose=f"生成《{title}》"):
                if ev["type"] == "delta":
                    text += ev["text"]
                yield ev
            saved = save_generated(title, text, rel, "zh")
            created += 1
            yield {"type": "note_done", "index": i, "title": title, "path": saved["path"]}
        except Exception as e:  # noqa: BLE001 单篇失败不中断整批
            failed += 1
            yield {"type": "note_error", "index": i, "title": title, "message": str(e)}
    yield {"type": "done", "created": created, "failed": failed}


# ---------------------------------------------------------------- 概念词条
async def term_events(payload: Dict) -> AsyncIterator[Dict]:
    plan = payload.get("_plan")
    if plan is None:
        plan = await term_service.prepare_term(
            payload.get("path") or "", payload.get("term") or "",
            payload.get("context_before") or "", payload.get("context_after") or "",
            payload.get("language") or "zh",
        )
    buf = ""
    async for ev in process.llm_call(payload.get("provider") or "", plan["messages"],
                                     payload.get("model") or "", None,
                                     purpose=f"解释「{payload.get('term')}」"):
        if ev["type"] == "delta":
            buf += ev["text"]
        yield ev
    saved = term_service.save_term_doc(plan, buf, regenerate=bool(payload.get("regenerate")))
    done = {"type": "done", "saved_path": saved["path"]}
    for k in ("is_new", "regenerated", "appended"):
        if k in saved:
            done[k] = saved[k]
    yield done


async def term_to_note_events(payload: Dict) -> AsyncIterator[Dict]:
    plan = payload.get("_plan") or term_service.prepare_to_note(
        payload.get("path") or "", payload.get("language") or "zh")
    buf = ""
    async for ev in process.llm_call(payload.get("provider") or "", plan["messages"],
                                     payload.get("model") or "", None,
                                     purpose="概念转完整笔记"):
        if ev["type"] == "delta":
            buf += ev["text"]
        yield ev
    saved = term_service.save_to_note(plan, buf)
    yield {"type": "done", "saved_path": saved["path"]}

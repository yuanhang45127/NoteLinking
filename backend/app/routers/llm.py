"""LLM 路由：通用对话、笔记生成、选中文本提问、学习指南（支持 SSE 流式）。

流式协议：text/event-stream，每条消息为
    data: {"type": "delta", "text": "..."}   # 增量文本
    data: {"type": "done"}                    # 结束（generate-note 会附带 saved_path）
    data: {"type": "error", "message": "..."} # 出错
此外还穿插「调用过程」事件（llm_start / llm_done / tool / step），
协议见 services/process.py，前端据此展示模型与工具调用过程。
"""
import datetime
import json
from typing import Dict, List

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse

from ..markdown_utils import append_section, ensure_frontmatter
from ..schemas import (
    AskRequest, ChatRequest, GenerateNoteRequest, StudyGuideRequest,
    TopicArchitectureRequest, TopicScaffoldRequest, TutorChatRequest,
)
from ..services import call_log_store, gen_flows, vault, websearch_service
from ..services.gen_flows import (
    ASK_SYSTEM, NOTE_SYSTEM, save_generated,  # noqa: F401 (re-export 兼容旧引用)
)
from ..services.llm_service import LLMError, complete, get_provider
from ..services.process import clear_session, set_session, strip_internal

router = APIRouter(prefix="/api/llm", tags=["llm"])


def sse_response(gen, flow: str = ""):
    """SSE 包装；flow = 调用日志流程名（llm.py 各端点显式传入，
    其余调用方缺省记 unknown——不猜测流程名）。

    调用日志在 SSE 边界统一收口：每条事件（含流程直接 yield 的 tool 等）
    在 yield 给客户端前记录一次；记录失败绝不影响流式输出。
    """

    async def wrapper():
        sid = ""
        try:
            # 先建会话再迭代生成器：生成器及其派生的子任务才会归入同一条记录
            sid = await set_session(flow or "unknown")
        except Exception:  # noqa: BLE001 — 开会话失败不影响流式输出
            pass

        async def _log(ev: dict) -> None:
            if not sid:
                return
            try:
                await call_log_store.record_event(sid, ev)
            except Exception:  # noqa: BLE001 — 日志失败不影响流式输出
                pass

        try:
            async for event in gen:
                ev = strip_internal(event)
                await _log(ev)
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
        except LLMError as e:
            err = {"type": "error", "message": str(e)}
            await _log(err)
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"
        except Exception as e:  # noqa: BLE001
            err = {"type": "error", "message": f"生成失败：{e}"}
            await _log(err)
            yield f"data: {json.dumps(err, ensure_ascii=False)}\n\n"
        finally:
            await clear_session()

    return StreamingResponse(
        wrapper(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _msg_list(messages: List[Dict]) -> List[Dict]:
    out = []
    for m in messages:
        role = m.role if m.role in ("system", "user", "assistant") else "user"
        out.append({"role": role, "content": m.content})
    return out


@router.get("/models")
async def list_models(provider: str = ""):
    """拉取服务商的可用模型列表（OpenAI 兼容 / Anthropic / Gemini 三类协议）。"""
    import httpx

    from ..services.llm_service import DEFAULT_BASE_URLS

    try:
        p = get_provider(provider)
    except LLMError as e:
        raise HTTPException(status_code=400, detail=str(e))
    ptype = (p.get("type") or "openai").lower()
    base = (p.get("base_url") or DEFAULT_BASE_URLS.get(ptype, "")).rstrip("/")
    key = p.get("api_key") or ""
    if not base:
        raise HTTPException(status_code=400, detail="服务商未配置 Base URL")
    if ptype == "openai":
        url, headers = f"{base}/models", {"Authorization": f"Bearer {key}"} if key else {}
    elif ptype == "anthropic":
        url = f"{base}/v1/models"
        headers = {"x-api-key": key, "anthropic-version": "2023-06-01"}
    else:  # gemini
        url = f"{base}/v1beta/models"
        headers = {"x-goog-api-key": key}
    try:
        async with httpx.AsyncClient(timeout=20) as client:
            resp = await client.get(url, headers=headers)
        if resp.status_code >= 400:
            raise HTTPException(status_code=502, detail=f"拉取模型列表失败：HTTP {resp.status_code} {resp.text[:200]}")
        data = resp.json()
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=502, detail=f"拉取模型列表失败：{e}")
    if ptype == "gemini":
        models = [m.get("name", "").removeprefix("models/") for m in data.get("models") or []]
    else:
        models = [m.get("id", "") for m in data.get("data") or []]
    models = sorted({m for m in models if m})
    return {"models": models}


@router.post("/chat")
async def chat(body: ChatRequest):
    if body.stream:
        return sse_response(gen_flows.chat_stream_events(body.model_dump()), "chat")
    text = await complete(body.provider or "", _msg_list(body.messages), body.model or "", body.temperature)
    return {"text": text}


@router.post("/generate-note")
async def generate_note(body: GenerateNoteRequest):
    lang = "中文" if body.language == "zh" else body.language
    title = (body.title or "").strip()
    user = (
        (f"笔记标题：《{title}》\n" if title else "")
        + f"请围绕以下要求写一篇{lang}学习笔记：\n\n{body.prompt}"
    )
    web_results: List[Dict] = []
    if body.use_web and websearch_service.is_enabled():
        web_results, block = await websearch_service.search_and_block(f"{title} {body.prompt}".strip())
        if block:
            user += block
    messages = [
        {"role": "system", "content": NOTE_SYSTEM + f"全文使用{lang}。"},
        {"role": "user", "content": user},
    ]

    if body.stream:
        return sse_response(gen_flows.note_events(body.model_dump()), "generate-note")

    text = await complete(body.provider or "", messages, body.model or "")
    result = {"text": text}
    if body.save_path:
        saved = save_generated(title or body.prompt[:30], text, body.save_path, body.language)
        gen_flows._backfill_web_links(saved["path"], text, web_results)
        result["saved_path"] = saved["path"]
    return result


@router.post("/ask")
async def ask(body: AskRequest):
    if body.stream:
        return sse_response(gen_flows.ask_events(body.model_dump()), "ask")

    note = vault.read_note(body.path)
    lang = "请用中文回答。" if body.language == "zh" else f"请用 {body.language} 回答。"
    before = body.context_before.strip()[-800:]
    after = body.context_after.strip()[:800]
    question = f"（针对选中内容的）问题：{body.question}" if body.question.strip() else "请讲解选中的内容。"
    user = (
        f"我在读笔记《{note['name']}》。选中内容的前后文如下：\n\n"
        f"……{before}\n【选中】{body.selected_text.strip()}\n{after}……\n\n{question}\n\n{lang}"
    )
    messages = [
        {"role": "system", "content": ASK_SYSTEM + lang},
        {"role": "user", "content": user},
    ]
    text = await complete(body.provider or "", messages, body.model or "")
    result: Dict = {"text": text}
    if body.save_to_note:
        heading = f"问答记录（{datetime.datetime.now().isoformat(timespec='seconds')}）"
        saved = vault.save_note(body.path, append_section(note["content"], heading, text), _force=True)
        result["saved_path"] = saved["path"]
    return result


@router.post("/tutor-chat")
async def tutor_chat(body: TutorChatRequest):
    """备考 AI 助教：把勾选的资料注入 system 上下文后对话（支持流式）。"""
    if body.stream:
        return sse_response(gen_flows.tutor_events(body.model_dump()), "tutor-chat")
    from ..services.exam_service import gather_context

    context, used = gather_context(body.paths)
    lang = "中文" if body.language == "zh" else body.language
    system = (
        f"你是学生的备考 AI 助教。以下是学生勾选的资料（{', '.join(used)}），"
        f"回答务必基于资料、直指考点，使用{lang}，公式用 LaTeX。\n\n{context}"
    )
    if body.use_web:
        last_user = next((m.content for m in reversed(body.messages) if m.role == "user"), "")
        block = await websearch_service.maybe_web_context(last_user.strip()[:100], True)
        if block:
            system += block
    history = _msg_list(body.messages)[-12:]
    messages = [{"role": "system", "content": system}] + history
    text = await complete(body.provider or "", messages, body.model or "", body.temperature)
    return {"text": text}


@router.post("/study-guide")
async def study_guide(body: StudyGuideRequest):
    from ..services.exam_service import _guide_messages

    messages = _guide_messages(body.paths, body.language)
    if body.use_web:
        block = await websearch_service.maybe_web_context(gen_flows._web_query_from_paths(body.paths), True)
        if block:
            messages[-1]["content"] += block
    md = await complete(body.provider or "", messages, body.model or "")
    result = {"markdown": md}
    if body.save_path:
        fm = {"generated": True, "created": datetime.date.today().isoformat()}
        saved = vault.create_note(body.save_path, ensure_frontmatter(md, fm), overwrite=False)
        result["saved_path"] = saved["path"]
    return result


@router.post("/topic-architecture/stream")
async def topic_architecture_stream(body: TopicArchitectureRequest):
    """主题整体架构：盘点主题内容 → 流式生成学习架构文档 → 落盘为主题下笔记。"""
    return sse_response(gen_flows.arch_events(body.model_dump()), "topic-architecture")


@router.post("/topic-architecture/scaffold")
def topic_architecture_scaffold(body: TopicScaffoldRequest):
    """按整体架构「建议知识架构」的最小等级生成主题目录骨架（已存在的目录跳过）。"""
    from ..services import arch_service

    return arch_service.scaffold_from_architecture(body.topic, body.save_path)


@router.post("/topic-architecture/generate-notes/stream")
async def topic_architecture_generate_notes(body: TopicScaffoldRequest):
    """按整体架构提纲，从最小等级逐篇用大模型生成笔记（SSE 汇报进度）。

    事件：start(total) → note_start/note_done/note_skip/note_error(index, title) → done(created, failed)。
    单篇失败不中断整批；笔记已存在时跳过（旧版落盘在叶子上一层目录的直接移入文件夹，不重复生成）；
    客户端断开即中止后续生成。
    """
    return sse_response(gen_flows.arch_notes_events(body.model_dump()), "generate-notes")


@router.post("/study-guide/stream")
async def study_guide_stream(body: StudyGuideRequest):
    """学习指南流式：SSE 增量输出 Markdown，结束时可选落盘。"""
    return sse_response(gen_flows.study_guide_events(body.model_dump()), "study-guide")

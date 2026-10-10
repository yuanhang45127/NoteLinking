"""LLM 路由：通用对话、笔记生成、选中文本提问、学习指南（支持 SSE 流式）。

流式协议：text/event-stream，每条消息为
    data: {"type": "delta", "text": "..."}   # 增量文本
    data: {"type": "done"}                    # 结束（generate-note 会附带 saved_path）
    data: {"type": "error", "message": "..."} # 出错
"""
import datetime
import json
from typing import AsyncIterator, Dict, List, Optional

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from ..markdown_utils import append_section, ensure_frontmatter
from ..schemas import AskRequest, ChatRequest, GenerateNoteRequest, StudyGuideRequest, TutorChatRequest
from ..services import vault
from ..services.llm_service import LLMError, complete, stream_llm

router = APIRouter(prefix="/api/llm", tags=["llm"])


def _sse(gen):
    async def wrapper():
        try:
            async for event in gen:
                yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
        except LLMError as e:
            yield f"data: {json.dumps({'type': 'error', 'message': str(e)}, ensure_ascii=False)}\n\n"
        except Exception as e:  # noqa: BLE001
            yield f"data: {json.dumps({'type': 'error', 'message': f'生成失败：{e}'}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        wrapper(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


async def _delta_gen(agen) -> AsyncIterator[Dict]:
    async for text in agen:
        yield {"type": "delta", "text": text}
    yield {"type": "done"}


def _msg_list(messages: List[Dict]) -> List[Dict]:
    out = []
    for m in messages:
        role = m.role if m.role in ("system", "user", "assistant") else "user"
        out.append({"role": role, "content": m.content})
    return out


@router.post("/chat")
async def chat(body: ChatRequest):
    messages = _msg_list(body.messages)
    if body.stream:
        return _sse(_delta_gen(stream_llm(body.provider or "", messages, body.model or "", body.temperature)))
    text = await complete(body.provider or "", messages, body.model or "", body.temperature)
    return {"text": text}


NOTE_SYSTEM = (
    "你是专业的学习笔记作者。请输出 GitHub 风格 Markdown 笔记正文（不要输出 frontmatter，"
    "不要用代码围栏包住全文）。要求：结构清晰（用 ## 分节）、重点突出、"
    "数学公式用 LaTeX（行内 $...$、独立 $$...$$）、代码用代码块、"
    "关键术语首次出现可用 [[术语]] 双链语法标注。"
)


@router.post("/generate-note")
async def generate_note(body: GenerateNoteRequest):
    lang = "中文" if body.language == "zh" else body.language
    title = (body.title or "").strip()
    user = (
        (f"笔记标题：《{title}》\n" if title else "")
        + f"请围绕以下要求写一篇{lang}学习笔记：\n\n{body.prompt}"
    )
    messages = [
        {"role": "system", "content": NOTE_SYSTEM + f"全文使用{lang}。"},
        {"role": "user", "content": user},
    ]

    if body.stream:
        async def gen():
            buf = []
            async for delta in stream_llm("", messages):
                buf.append(delta)
                yield {"type": "delta", "text": delta}
            if body.save_path:
                saved = _save_generated(title or body.prompt[:30], "".join(buf), body.save_path, body.language)
                yield {"type": "done", "saved_path": saved["path"]}
                return
            yield {"type": "done"}

        return _sse(gen())

    text = await complete("", messages)
    result = {"text": text}
    if body.save_path:
        saved = _save_generated(title or body.prompt[:30], text, body.save_path, body.language)
        result["saved_path"] = saved["path"]
    return result


def _save_generated(title: str, text: str, save_path: str, language: str) -> Dict:
    fm = {"title": title.strip() or "未命名笔记", "generated": True, "created": datetime.date.today().isoformat()}
    content = ensure_frontmatter(f"# {fm['title']}\n", fm) + text.strip() + "\n"
    return vault.create_note(save_path, content, overwrite=False)


ASK_SYSTEM = (
    "你是耐心的学习助手。用户在阅读笔记时选中了一段看不懂的内容，"
    "请结合上下文用平实的语言讲解，必要时举例或补充背景。"
)


@router.post("/ask")
async def ask(body: AskRequest):
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

    if body.stream:
        async def gen():
            buf = []
            async for delta in stream_llm("", messages):
                buf.append(delta)
                yield {"type": "delta", "text": delta}
            if body.save_to_note:
                heading = f"问答记录（{datetime.datetime.now().isoformat(timespec='seconds')}）"
                qa = f"**问：** {body.question.strip() or '讲解选中内容'}\n\n> {body.selected_text.strip()}\n\n**答：**\n\n{''.join(buf).strip()}"
                saved = vault.save_note(body.path, append_section(note["content"], heading, qa))
                yield {"type": "done", "saved_path": saved["path"]}
                return
            yield {"type": "done"}

        return _sse(gen())

    text = await complete("", messages)
    result: Dict = {"text": text}
    if body.save_to_note:
        heading = f"问答记录（{datetime.datetime.now().isoformat(timespec='seconds')}）"
        saved = vault.save_note(body.path, append_section(note["content"], heading, text))
        result["saved_path"] = saved["path"]
    return result


@router.post("/tutor-chat")
async def tutor_chat(body: TutorChatRequest):
    """备考 AI 助教：把勾选的资料注入 system 上下文后对话（支持流式）。"""
    from ..services.exam_service import gather_context

    context, used = gather_context(body.paths)
    lang = "中文" if body.language == "zh" else body.language
    system = (
        f"你是学生的备考 AI 助教。以下是学生勾选的资料（{', '.join(used)}），"
        f"回答务必基于资料、直指考点，使用{lang}，公式用 LaTeX。\n\n{context}"
    )
    history = _msg_list(body.messages)[-12:]
    messages = [{"role": "system", "content": system}] + history

    if body.stream:
        return _sse(_delta_gen(stream_llm(body.provider or "", messages, body.model or "", body.temperature)))
    text = await complete(body.provider or "", messages, body.model or "", body.temperature)
    return {"text": text}


@router.post("/study-guide")
async def study_guide(body: StudyGuideRequest):
    from ..services.exam_service import generate_study_guide

    md = await generate_study_guide(body.paths, body.language, body.provider or "", body.model or "")
    result = {"markdown": md}
    if body.save_path:
        saved = vault.create_note(body.save_path, md, overwrite=False)
        result["saved_path"] = saved["path"]
    return result

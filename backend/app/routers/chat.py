"""AI 对话路由：会话 CRUD + 流式对话（SSE，支持工具调用步骤事件）。

流式事件格式沿用 llm.py 约定（data: {json}\n\n）：
    {"type": "delta", "text": "..."}                       # 增量文本
    {"type": "tool", "name", "args", "status": "start"|"done", "ok"?, "summary"?}
    {"type": "done", "session": {...}, "message": {...}}   # 回答已落库
    {"type": "error", "message": "..."}
"""
from fastapi import APIRouter, HTTPException

from ..schemas import ChatSessionCreate, ChatSessionRename, ChatTurnRequest
from ..services import chat_agent, chat_store
from .llm import sse_response

router = APIRouter(prefix="/api/chat", tags=["chat"])


@router.get("/sessions")
def list_sessions():
    return {"sessions": chat_store.list_sessions()}


@router.post("/sessions")
def create_session(body: ChatSessionCreate):
    return chat_store.create_session(body.title)


@router.get("/sessions/{session_id}")
def get_session(session_id: str):
    return chat_store.get_session(session_id)


@router.patch("/sessions/{session_id}")
def rename_session(session_id: str, body: ChatSessionRename):
    return chat_store.rename_session(session_id, body.title)


@router.delete("/sessions/{session_id}")
def delete_session(session_id: str):
    chat_store.delete_session(session_id)
    return {"ok": True}


@router.post("/sessions/{session_id}/turn")
async def turn(session_id: str, body: ChatTurnRequest):
    """一轮对话：先落库提问（或回退上一次回答），再进入流式工具循环。"""
    chat_store.get_session(session_id)  # 不存在早退 404
    if body.regenerate:
        chat_store.drop_after_last_user(session_id)
    elif not body.content.strip():
        raise HTTPException(status_code=400, detail="内容不能为空")
    else:
        chat_store.append_message(session_id, "user", body.content)
    return sse_response(chat_agent.run_turn(
        session_id, body.context_paths, body.provider or "", body.model or "", body.temperature,
    ))

"""服务端后台 AI 任务路由：启动 / 列表 / 取消 / 事件流（SSE）。

前端 lib/aiTasks.ts 的 streamTrackedDetached / restoreAiTasks 调这些接口：
生成切到后台或刷新页面后，任务在服务器继续跑，事件流可重连重放。

op 注册表映射到 gen_flows 的共享流程生成器，过程事件协议见 services/process.py。
"""
import asyncio
import json

from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..services import ai_task_store, gen_flows
from ..services.process import strip_internal

router = APIRouter(prefix="/api/ai-tasks", tags=["ai-tasks"])


def _flow_for(op: str):
    """op 名 → 事件流生成器工厂；未知 op 返回直接报错的流程。"""
    known = {
        "term": gen_flows.term_events,
        "term-to-note": gen_flows.term_to_note_events,
        "generate-note": gen_flows.note_events,
        "chat": gen_flows.chat_stream_events,
        "study-guide": gen_flows.study_guide_events,
    }
    if op in known:
        return known[op]

    def _unknown(_payload):
        async def _gen():
            yield {"type": "error", "message": f"未知任务类型：{op}"}
        return _gen()
    return _unknown


class TaskStart(BaseModel):
    title: str
    kind: str = "note"
    op: str
    payload: dict = {}


@router.post("")
async def start(body: TaskStart):
    return ai_task_store.start_task(body.title, body.kind, body.op, body.payload, _flow_for(body.op))


@router.get("")
async def list_all():
    return {"tasks": ai_task_store.list_tasks()}


@router.post("/{task_id}/cancel")
async def cancel(task_id: str):
    return {"ok": ai_task_store.cancel_task(task_id)}


async def _events_stream(task_id: str):
    task = ai_task_store.get_task(task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="任务不存在")
    # 状态在回放期间可能变化：先拿引用，快照式推进
    have = 0
    try:
        while True:
            while have < len(task["events"]):
                ev = strip_internal(task["events"][have])
                have += 1
                yield f"data: {json.dumps(ev, ensure_ascii=False)}\n\n"
                if ev.get("type") in ("done", "error"):
                    return
            if task["status"] != "running":
                return
            await ai_task_store.wait_events(task, have)
            if len(task["events"]) == have and task["status"] == "running":
                yield ": ping\n\n"  # 心跳：防止代理断开空闲连接
    except asyncio.CancelledError:  # 客户端断开
        return


@router.api_route("/{task_id}/events", methods=["GET", "POST"])
async def events(task_id: str):
    return StreamingResponse(
        _events_stream(task_id),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )

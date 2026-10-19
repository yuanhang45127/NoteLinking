"""服务端托管的后台 AI 任务：生成在服务器协程里跑并缓冲事件。

- 前端把生成切到后台/刷新页面后，可经 GET /api/ai-tasks 重连（悬浮窗恢复、事件流重放）。
- 事件缓冲与流式 SSE 同构（delta 合并连续片段），见 services/process.py 协议。
- 任务按用户隔离，落盘 ai_tasks.json；重启后 running 的任务标记为中断。
"""
import asyncio
import json
import time
from pathlib import Path
from typing import Dict, Iterator, List, Optional

from .. import config
from . import call_log_store

MAX_TASKS_PER_USER = 50        # 每用户保留的历史任务上限
PRUNE_AFTER = 24 * 3600        # 已结束任务保留时长（秒）
PERSIST_EVERY = 25             # 每累计 N 次事件追加落盘一次

# 全部用户共享的运行态：{user: {task_id: task}}；task 见 _new_task
_tasks: Dict[str, Dict[str, dict]] = {}


def _file() -> Path:
    return config.get_user_data_dir() / "ai_tasks.json"


def _new_task(task_id: str, title: str, kind: str, op: str, payload: dict) -> dict:
    return {
        "id": task_id, "title": title, "kind": kind, "op": op,
        "status": "running", "chars": 0, "error": "", "result": None,
        "created_at": time.time(), "updated_at": time.time(),
        "events": [], "payload": payload,
        "cond": asyncio.Condition(),      # 订阅者等待新事件
        "runner": None,                   # asyncio.Task
        "_appends": 0,
    }


def _pub(task: dict) -> dict:
    """对外信息（不含事件缓冲与运行态对象）。"""
    return {k: task.get(k) for k in
            ("id", "title", "kind", "op", "status", "chars", "created_at", "updated_at", "error", "result")}


def _user_tasks() -> Dict[str, dict]:
    user = config.get_current_user() or "default"
    return _tasks.setdefault(user, {})


def load_persisted() -> None:
    """启动时恢复落盘任务：running 的一律标记中断（协程已不在）。"""
    f = _file()
    if not f.exists():
        return
    try:
        rows = json.loads(f.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return
    for row in rows or []:
        t = _new_task(row["id"], row.get("title", ""), row.get("kind", ""),
                      row.get("op", ""), row.get("payload") or {})
        for k in ("status", "chars", "error", "result", "created_at", "updated_at"):
            t[k] = row.get(k)
        t["events"] = list(row.get("events") or [])
        if t["status"] == "running":
            t["status"] = "error"
            t["error"] = "服务重启，任务中断"
            t["events"].append({"type": "error", "message": t["error"]})
        _user_tasks()[t["id"]] = t


def _persist() -> None:
    try:
        rows = [{k: t[k] for k in ("id", "title", "kind", "op", "status", "chars",
                                   "error", "result", "created_at", "updated_at", "events", "payload")}
                for t in _user_tasks().values()]
        _file().write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")
    except Exception:  # noqa: BLE001 — 落盘失败不影响运行
        pass


def _prune() -> None:
    now = time.time()
    bucket = _user_tasks()
    stale = [tid for tid, t in bucket.items()
             if t["status"] != "running" and now - t["updated_at"] > PRUNE_AFTER]
    for tid in stale:
        del bucket[tid]
    if len(bucket) > MAX_TASKS_PER_USER:
        extra = sorted(bucket.values(), key=lambda t: t["updated_at"])[: len(bucket) - MAX_TASKS_PER_USER]
        for t in extra:
            if t["status"] != "running":
                del bucket[t["id"]]


def list_tasks() -> List[dict]:
    _prune()
    rows = sorted(_user_tasks().values(), key=lambda t: -t["created_at"])
    return [_pub(t) for t in rows]


def get_task(task_id: str) -> Optional[dict]:
    return _user_tasks().get(task_id)


async def append_event(task: dict, ev: dict) -> None:
    """追加事件（连续 delta 合并为一条），并按需通知订阅者。"""
    ev = dict(ev)
    events = task["events"]
    if ev.get("type") == "delta" and events and events[-1].get("type") == "delta":
        events[-1]["text"] += ev.get("text", "")
    else:
        events.append(ev)
    if ev.get("type") == "delta":
        task["chars"] += len(ev.get("text") or "")
    if ev.get("type") == "done":
        task["status"] = "done"
        task["result"] = {"saved_path": ev.get("saved_path")} if ev.get("saved_path") else {}
    elif ev.get("type") == "error":
        task["status"] = "error"
        task["error"] = ev.get("message") or "生成失败"
    task["updated_at"] = time.time()
    task["_appends"] += 1
    # 旁路记录到调用日志（后台任务的事件唯一汇点；SSE 回放不经过这里，不会双记）
    try:
        await call_log_store.record_event(f"task-{task['id']}", ev)
    except Exception:  # noqa: BLE001 — 日志失败不影响任务运行
        pass
    if task["status"] != "running" or task["_appends"] % PERSIST_EVERY == 0:
        _persist()
    async with task["cond"]:
        task["cond"].notify_all()


async def wait_events(task: dict, have: int, timeout: float = 15.0) -> bool:
    """等待事件数超过 have；超时返回 False（供 SSE 心跳）。"""
    async with task["cond"]:
        if len(task["events"]) > have or task["status"] != "running":
            return True
        try:
            await asyncio.wait_for(task["cond"].wait(), timeout)
        except asyncio.TimeoutError:
            pass
    return len(task["events"]) > have or task["status"] != "running"


def iter_events(task: dict, start: int = 0) -> Iterator[dict]:
    return iter(task["events"][start:])


def start_task(title: str, kind: str, op: str, payload: dict, gen_factory) -> dict:
    """创建并启动后台任务；gen_factory(payload) 需返回事件 async generator。"""
    _prune()
    task_id = f"t{int(time.time() * 1000):x}{len(_user_tasks()) % 1000:02x}"
    task = _new_task(task_id, title, kind, op, payload)
    _user_tasks()[task_id] = task
    task["runner"] = asyncio.get_running_loop().create_task(_run(task, gen_factory))
    _persist()
    return _pub(task)


async def _run(task: dict, gen_factory) -> None:
    try:
        # 调用日志会话：id 由 task_id 确定性派生，流程名取任务 op
        await call_log_store.start_session(task["op"], session_id=f"task-{task['id']}")
        gen = gen_factory(task["payload"])
        async for ev in gen:
            await append_event(task, ev)
        if task["status"] == "running":  # 流结束但没有 done/error 事件
            await append_event(task, {"type": "error", "message": "生成流程提前结束"})
    except asyncio.CancelledError:
        task["status"] = "stopped"
        task["updated_at"] = time.time()
        _persist()
    except Exception as e:  # noqa: BLE001 — 后台任务异常转成 error 事件
        await append_event(task, {"type": "error", "message": f"生成失败：{e}"})
    finally:
        task["runner"] = None
        if task["status"] == "running":
            task["status"] = "error"
        _persist()
        try:
            await call_log_store.end_session(f"task-{task['id']}")
        except Exception:  # noqa: BLE001 — 日志收尾失败不影响任务状态
            pass
        async with task["cond"]:
            task["cond"].notify_all()


def cancel_task(task_id: str) -> bool:
    task = get_task(task_id)
    if not task or task["status"] != "running":
        return False
    if task["runner"] is not None:
        task["runner"].cancel()
    else:
        task["status"] = "stopped"
        _persist()
    return True

"""调用日志存储：把「调用过程」事件旁路落盘，供设置页回看历史调用记录。

- 一次生成流程 = 一条记录（会话）：llm_start / delta / llm_done / tool / step 事件全量留痕，
  连续 delta 合并为一条（与 services/ai_task_store.append_event 同规则）；
  summary 与 llm 统计由事件列表整体重算（事件量小，重算比增量匹配更可靠）。
- 记录入口（两处，互不重叠，避免双记）：
    1. SSE 边界：routers/llm.py sse_response 每 yield 一条事件前记录一次——
       覆盖 llm/chat/terms/exams/books 全部流式端点，含流程直接 yield 的
       tool / note_start 等未经 process 助手的事件；
    2. 后台任务：services/ai_task_store.append_event（事件唯一汇点），
       会话 id 由 task_id 派生、流程名取任务 op；回放（ai_tasks._events_stream）不记录。
- 落盘：用户数据目录下 call_logs.jsonl（JSONL，一行一条记录），整体原子重写
  （临时文件 + os.replace）；每用户最多保留 MAX_RECORDS 条，超出丢最旧。
  快照在事件循环线程完成，序列化 + 写入放线程池（asyncio.to_thread），不阻塞流式。
- 落盘时机：会话结束（end_session）立即重写；进行中的会话走防抖循环
  （事件停止 FLUSH_DELAY 秒且自上次落盘没有新变更才退出）——惰性会话没有结束钩子，
  靠它兜底，同时不无限重排。
- delta 正文截断到 DELTA_MAX_CHARS 字符（前端时间线不渲染 delta 文本，记录保持小巧）。
- 运行态：内存 {用户: {id: 记录}}（dict 保序 = 时间序），按用户懒加载。
- 并发：asyncio 锁按事件循环分配——asyncio.Lock 会绑定首次使用它的事件循环，
  模块级单锁在测试（asyncio.run / TestClient 各自成环）里会跨环报错。
  所有落盘（防抖循环 / end_session）都在锁内完成，防止并发写互相覆盖。
"""
import asyncio
import datetime
import itertools
import json
import os
import re
import time
import weakref
from pathlib import Path
from typing import Dict, List, Optional

from .. import config

MAX_RECORDS = 2000          # 每用户保留的调用记录上限（超出丢最旧）
FLUSH_DELAY = 1.5           # 防抖落盘间隔（秒）
LIST_LIMIT_MAX = 200        # 列表接口单页条数上限
DELTA_MAX_CHARS = 1000      # delta 事件正文截断长度（前端不渲染，仅留痕）

_TRUNC_RE = re.compile(r" …\[截断，共\d+字符\]$")   # 截断标记（幂等判断用）

_seq = itertools.count(1)                                   # 会话 id 序号（同毫秒内去重）
_by_user: Dict[str, Dict[str, dict]] = {}                   # 用户 → {id: 记录}（插入序 = 时间序）
_loaded: set = set()                                        # 已从磁盘加载的用户
_locks: "weakref.WeakKeyDictionary" = weakref.WeakKeyDictionary()   # 事件循环 → asyncio.Lock
_dirty: Dict[str, bool] = {}                                # 用户 → 有自上次落盘以来的新变更
_flush_pending: set = set()                                 # 已有防抖循环的用户（不重排）
_flush_tasks: set = set()                                   # 防抖循环任务强引用，防止被 GC


def _get_lock() -> asyncio.Lock:
    """取当前事件循环的锁（按环隔离，避免跨事件循环复用报错）。"""
    loop = asyncio.get_running_loop()
    lock = _locks.get(loop)
    if lock is None:
        lock = asyncio.Lock()
        _locks[loop] = lock
    return lock


def _file() -> Path:
    return config.get_user_data_dir() / "call_logs.jsonl"


def _strip_internal(ev: dict) -> dict:
    """剔除 `_` 前缀的内部键（与 process.strip_internal 同规则；此处避免循环导入）。"""
    return {k: v for k, v in ev.items() if not k.startswith("_")}


def _clip_events(events: List[dict]) -> List[dict]:
    """对外/落盘前的事件列表：delta 正文截断（内存保留全文，落盘与 API 只给截断版）。

    幂等：已带截断标记的（落盘后读回的）不再二次截断。
    """
    out = []
    for ev in events:
        ev = dict(ev)
        if ev.get("type") == "delta":
            text = ev.get("text") or ""
            if len(text) > DELTA_MAX_CHARS and not _TRUNC_RE.search(text):
                ev["text"] = text[:DELTA_MAX_CHARS] + f" …[截断，共{len(text)}字符]"
        out.append(ev)
    return out


def _new_record(record_id: str, flow: str) -> dict:
    return {
        "id": record_id,
        "ts": datetime.datetime.now().isoformat(timespec="milliseconds"),
        "flow": flow, "purpose": "",
        "summary": {"llm_calls": 0, "tool_calls": 0, "steps": 0},
        "llm": [], "events": [],
    }


def _row(rec: dict) -> dict:
    """落盘/对外行（显式取键，内部状态不外泄；delta 正文截断）。"""
    return {"id": rec["id"], "ts": rec["ts"], "flow": rec["flow"], "purpose": rec["purpose"],
            "summary": dict(rec["summary"]), "llm": [dict(x) for x in rec["llm"]],
            "events": _clip_events(rec["events"])}


def _full(rec: dict) -> dict:
    """完整记录对外形状（get_record 用，含 events）。"""
    return _row(rec)


def _entry(rec: dict) -> dict:
    """列表项对外形状（list_records 用，不含 events，带统计与模型清单）。"""
    return {"id": rec["id"], "ts": rec["ts"], "flow": rec["flow"], "purpose": rec["purpose"],
            "llm_calls": rec["summary"]["llm_calls"],
            "tool_calls": rec["summary"]["tool_calls"],
            "steps": rec["summary"]["steps"],
            "models": [f"{x.get('provider') or ''}/{x.get('model') or ''}"
                       for x in rec["llm"] if x.get("provider") or x.get("model")]}


def _recompute(rec: dict) -> None:
    """由事件列表重算 purpose / summary / llm 统计。

    llm_done 按 seq 回填到对应 llm_start 的条目（取该 seq 最后一个未闭合的）；
    seq 对不上（并发调用等）时退化为最后一个未闭合条目。
    """
    llm: List[dict] = []
    open_idx: Dict[int, List[int]] = {}   # seq → 未闭合的 llm 条目下标（栈）
    llm_calls = tool_calls = steps = 0
    purpose = ""
    for ev in rec["events"]:
        t = ev.get("type")
        if t == "llm_start":
            llm_calls += 1
            if not purpose and ev.get("purpose"):
                purpose = ev["purpose"]
            llm.append({"provider": ev.get("provider") or "", "model": ev.get("model") or "",
                        "prompt_chars": ev.get("prompt_chars") or 0,
                        "output_chars": 0, "elapsed_ms": 0})
            open_idx.setdefault(ev.get("seq") or 0, []).append(len(llm) - 1)
        elif t == "llm_done":
            stack = open_idx.get(ev.get("seq") or 0)
            idx = stack.pop() if stack else None
            if idx is None:  # seq 对不上：取任意一个未闭合条目
                for s in open_idx.values():
                    if s:
                        idx = s.pop()
                        break
            if idx is not None:
                llm[idx]["output_chars"] = ev.get("chars") or 0
                llm[idx]["elapsed_ms"] = int(round((ev.get("elapsed") or 0) * 1000))
        elif t == "tool" and ev.get("status") == "done":
            tool_calls += 1
        elif t == "step" and ev.get("status") == "start":
            steps += 1
    rec["purpose"] = purpose
    rec["summary"] = {"llm_calls": llm_calls, "tool_calls": tool_calls, "steps": steps}
    rec["llm"] = llm


def _prune(bucket: Dict[str, dict]) -> None:
    """超出上限丢最旧（按 ts + id 升序；id 内含毫秒时间戳与序号，与 ts 同序）。"""
    if len(bucket) <= MAX_RECORDS:
        return
    oldest = sorted(bucket.values(), key=lambda r: (r["ts"], r["id"]))[: len(bucket) - MAX_RECORDS]
    for rec in oldest:
        del bucket[rec["id"]]


def _write_jsonl(rows: List[dict], f: Path) -> None:
    """线程池执行：序列化 + 临时文件 + os.replace（原子替换）。"""
    lines = [json.dumps(row, ensure_ascii=False) for row in rows]
    tmp = f.with_suffix(".jsonl.tmp")
    tmp.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")
    os.replace(tmp, f)


async def _persist(bucket: Dict[str, dict], f: Optional[Path] = None) -> None:
    """整体重写 JSONL：循环线程内快照，序列化与写入放线程池（不阻塞流式）。

    调用方须持有锁：防止两个落盘路径（防抖循环 / end_session）交叉写坏文件。
    """
    try:
        f = f or _file()
        f.parent.mkdir(parents=True, exist_ok=True)
        rows = [_row(rec) for rec in bucket.values()]   # 快照：循环线程，毫秒级
        await asyncio.to_thread(_write_jsonl, rows, f)
    except Exception:  # noqa: BLE001 — 落盘失败不影响运行
        pass


def _load_rows(f: Path) -> List[dict]:
    """线程池执行：读取 JSONL；坏行跳过，不让一条脏数据毁掉整个文件。"""
    if not f.exists():
        return []
    rows: List[dict] = []
    try:
        for line in f.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if isinstance(row, dict) and row.get("id"):
                row.setdefault("ts", "")
                row.setdefault("flow", "")
                row.setdefault("purpose", "")
                row.setdefault("summary", {"llm_calls": 0, "tool_calls": 0, "steps": 0})
                row.setdefault("llm", [])
                row.setdefault("events", [])
                rows.append(row)
    except Exception:  # noqa: BLE001
        return []
    return rows


async def _bucket() -> Dict[str, dict]:
    """当前用户的记录表（首次访问时懒加载落盘数据，读取放线程池）。"""
    user = config.get_current_user() or "default"
    bucket = _by_user.setdefault(user, {})
    if user not in _loaded:
        for row in await asyncio.to_thread(_load_rows, _file()):
            bucket[row["id"]] = row
        _loaded.add(user)
        _prune(bucket)
    return bucket


def _schedule_flush(bucket: Dict[str, dict]) -> None:
    """防抖落盘：为当前用户维持一个落盘循环，自上次落盘没有新变更就退出。

    调度时锁定文件路径——回调执行时数据目录可能已变（测试按用例隔离目录）。
    """
    user = config.get_current_user() or "default"
    _dirty[user] = True
    if user in _flush_pending:   # 循环已在跑：它下次醒来会看到新变更
        return
    _flush_pending.add(user)
    f = _file()

    async def _run() -> None:
        while True:
            try:
                await asyncio.sleep(FLUSH_DELAY)
                async with _get_lock():
                    if not _dirty.get(user):
                        return              # 无新变更：收工，不再自我重排
                    await _persist(bucket, f)
                    _dirty[user] = False
            except Exception:  # noqa: BLE001 — 落盘失败不影响运行
                return

    task = asyncio.get_running_loop().create_task(_run())
    _flush_tasks.add(task)

    def _done(t):
        _flush_pending.discard(user)
        _flush_tasks.discard(t)

    task.add_done_callback(_done)


# ---------------------------------------------------------------- 对外 API
async def start_session(flow: str, session_id: str = "") -> str:
    """开启一个调用会话，返回记录 id（flow 由调用方给出，不猜测流程名）。

    session_id 供后台任务按 task_id 确定性派生；缺省自动生成。
    id 已存在（同 id 任务重启等）时沿用旧记录继续追加。
    """
    async with _get_lock():
        bucket = await _bucket()
        _prune(bucket)
        sid = session_id or f"c{int(time.time() * 1000):x}{next(_seq) % 0x1000:03x}"
        if sid not in bucket:
            bucket[sid] = _new_record(sid, flow)
        return sid


async def record_event(session_id: str, event: dict) -> None:
    """追加一条过程事件（连续 delta 合并为一条），重算统计并标记待落盘。"""
    async with _get_lock():
        bucket = await _bucket()
        rec = bucket.get(session_id)
        if rec is None:   # 会话已结束/被裁剪：静默丢弃
            return
        ev = _strip_internal(dict(event))
        events = rec["events"]
        if ev.get("type") == "delta" and events and events[-1].get("type") == "delta":
            events[-1]["text"] += ev.get("text", "")
        else:
            events.append(ev)
        _recompute(rec)
        _schedule_flush(bucket)


async def end_session(session_id: str) -> None:
    """结束会话并落盘；没有任何事件的空会话直接丢弃（不产生噪音记录）。"""
    async with _get_lock():
        bucket = await _bucket()
        rec = bucket.get(session_id)
        if rec is None:
            return
        if not rec["events"]:
            del bucket[session_id]
        _prune(bucket)
        await _persist(bucket)
        _dirty[config.get_current_user() or "default"] = False


async def list_records(limit: int = 50, offset: int = 0, q: str = "") -> List[dict]:
    """调用记录列表（新→旧），不含 events；q 大小写不敏感匹配 flow + purpose。"""
    limit = max(1, min(int(limit or 50), LIST_LIMIT_MAX))
    offset = max(0, int(offset or 0))
    rows = sorted((await _bucket()).values(), key=lambda r: (r["ts"], r["id"]), reverse=True)
    kw = (q or "").strip().lower()
    if kw:
        rows = [r for r in rows if kw in (r["flow"] + "\n" + r["purpose"]).lower()]
    return [_entry(r) for r in rows[offset: offset + limit]]


async def get_record(record_id: str) -> Optional[dict]:
    """完整记录（含 events，delta 截断版）；不存在返回 None。"""
    rec = (await _bucket()).get(record_id)
    return _full(rec) if rec else None

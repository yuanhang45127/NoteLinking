"""AI 对话会话存储：一会话一 JSON，落盘在用户数据目录 chats/ 下。

会话结构：
    {id, title, created_at, updated_at,
     messages: [{role, content, created_at, tool_steps?: [{name, args, summary, ok}]}]}
"""
import datetime
import json
import uuid
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import HTTPException

from ..config import get_chats_dir

DEFAULT_TITLE = "新对话"


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _session_file(session_id: str) -> Path:
    # 只取文件名部分，防路径穿越
    return get_chats_dir() / f"{Path(session_id).name}.json"


def _read(f: Path) -> Optional[Dict]:
    if not f.exists():
        return None
    try:
        return json.loads(f.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def _write(session: Dict) -> None:
    f = _session_file(session["id"])
    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(session, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(f)


def _meta(session: Dict) -> Dict:
    return {
        "id": session["id"],
        "title": session["title"],
        "created_at": session["created_at"],
        "updated_at": session["updated_at"],
        "message_count": len(session.get("messages") or []),
    }


def list_sessions() -> List[Dict]:
    out = []
    for f in get_chats_dir().glob("*.json"):
        s = _read(f)
        if s:
            out.append(_meta(s))
    out.sort(key=lambda x: x.get("updated_at", ""), reverse=True)
    return out


def create_session(title: str = "") -> Dict:
    session = {
        "id": datetime.datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:6],
        "title": title.strip() or DEFAULT_TITLE,
        "created_at": _now(),
        "updated_at": _now(),
        "messages": [],
    }
    _write(session)
    return session


def get_session(session_id: str) -> Dict:
    s = _read(_session_file(session_id))
    if s is None:
        raise HTTPException(status_code=404, detail=f"会话不存在：{session_id}")
    return s


def rename_session(session_id: str, title: str) -> Dict:
    s = get_session(session_id)
    s["title"] = title.strip() or s["title"]
    _write(s)
    return s


def delete_session(session_id: str) -> None:
    f = _session_file(session_id)
    if not f.exists():
        raise HTTPException(status_code=404, detail=f"会话不存在：{session_id}")
    f.unlink()


def append_message(session_id: str, role: str, content: str,
                   tool_steps: Optional[List[Dict]] = None) -> Dict:
    """追加一条消息并触碰 updated_at；首条用户消息自动生成会话标题。"""
    s = get_session(session_id)
    msg: Dict = {"role": role, "content": content, "created_at": _now()}
    if tool_steps:
        msg["tool_steps"] = tool_steps
    s["messages"].append(msg)
    s["updated_at"] = _now()
    if role == "user" and s.get("title", DEFAULT_TITLE) == DEFAULT_TITLE:
        s["title"] = content.strip().replace("\n", " ")[:24] or DEFAULT_TITLE
    _write(s)
    return s


def drop_after_last_user(session_id: str) -> Dict:
    """重新生成前调用：去掉末尾的上一次回答（及任何非用户消息），保留最后一问。"""
    s = get_session(session_id)
    msgs = s["messages"]
    while msgs and msgs[-1]["role"] != "user":
        msgs.pop()
    if not msgs:
        raise HTTPException(status_code=400, detail="没有可重新生成的提问")
    s["updated_at"] = _now()
    _write(s)
    return s

"""备考目标存储：users/<用户>/goals.json，如「机器学习期末 · 6 月 28 日」。"""
import datetime
import json
import uuid
from typing import Dict, List

from fastapi import HTTPException

from ..config import get_user_data_dir


def _file():
    return get_user_data_dir() / "goals.json"


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def list_goals() -> List[Dict]:
    f = _file()
    if not f.exists():
        return []
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        return data if isinstance(data, list) else []
    except (json.JSONDecodeError, OSError):
        return []


def _save(items: List[Dict]) -> None:
    f = _file()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(items, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(f)


def add_goal(title: str, date: str = "", topic: str = "") -> Dict:
    title = (title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="目标标题不能为空")
    goal = {"id": uuid.uuid4().hex[:10], "title": title, "date": date or "", "topic": topic or "", "created_at": _now()}
    items = list_goals()
    items.append(goal)
    _save(items)
    return goal


def update_goal(goal_id: str, updates: Dict) -> Dict:
    items = list_goals()
    for g in items:
        if g["id"] == goal_id:
            for k in ("title", "date", "topic"):
                if updates.get(k) is not None:
                    g[k] = updates[k]
            _save(items)
            return g
    raise HTTPException(status_code=404, detail=f"目标不存在：{goal_id}")


def delete_goal(goal_id: str) -> None:
    items = [g for g in list_goals() if g["id"] != goal_id]
    if len(items) == len(list_goals()):
        raise HTTPException(status_code=404, detail=f"目标不存在：{goal_id}")
    _save(items)

"""阅读进度存储：每个用户一份 read_positions.json，记住每篇笔记读到的位置。

结构：{ <笔记路径>: {"ratio": 0~1, "heading": "当时可见的最近小节标题 id", "updated_at": iso} }
服务端记忆（跨设备/浏览器生效）；前端打开笔记时拉取定位，滚动时节流回写。
超量按 updated_at 淘汰最旧条目，笔记删除/移动后的残留进度会自然过期。
"""
import datetime
import json
from pathlib import Path
from typing import Dict

from ..config import get_user_data_dir
from ..utils import safe_rel_parts

MAX_ENTRIES = 5000  # 防止无限膨胀


def _file() -> Path:
    return get_user_data_dir() / "read_positions.json"


def _now() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _read_all() -> Dict:
    f = _file()
    if not f.exists():
        return {}
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def _write_all(data: Dict) -> None:
    if len(data) > MAX_ENTRIES:
        oldest = sorted(data.items(), key=lambda kv: kv[1].get("updated_at", ""))
        for key, _ in oldest[: len(data) - MAX_ENTRIES]:
            del data[key]
    f = _file()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(f)


def get_position(note_rel: str) -> Dict:
    """取一篇笔记的上次阅读位置；没有记录时返回零位。"""
    return _read_all().get(str(safe_rel_parts(note_rel))) or {
        "ratio": 0, "heading": "", "updated_at": "",
    }


def save_position(note_rel: str, ratio: float, heading: str = "") -> Dict:
    pos = {
        "ratio": round(max(0.0, min(1.0, float(ratio or 0))), 4),
        "heading": (heading or "").strip()[:80],
        "updated_at": _now(),
    }
    data = _read_all()
    data[str(safe_rel_parts(note_rel))] = pos
    _write_all(data)
    return pos


def clear_position(note_rel: str) -> None:
    """笔记删除/移动后清掉旧路径的进度。"""
    data = _read_all()
    if data.pop(str(safe_rel_parts(note_rel)), None) is not None:
        _write_all(data)

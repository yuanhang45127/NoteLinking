"""知识图谱：扫描全库 md 的 [[双链]]（含 frontmatter 里的 origin/sources），
自动生成 节点（笔记/词条）+ 边（引用关系）。无需手动维护。
"""
import datetime
from typing import Dict, List, Optional

from .vault import build_link_index


def build_graph(topic: str = "") -> Dict:
    index = build_link_index()
    items = list(index.values())
    if topic:
        items = [i for i in items if i["topic"] == topic]

    # 名称 → 节点 id（同名词优先取同主题内的）
    name_to_id: Dict[str, str] = {}
    for info in items:
        name_to_id.setdefault(info["name"], info["id"])

    nodes: List[Dict] = []
    for info in items:
        nodes.append(
            {
                "id": info["id"],
                "label": info["title"],
                "name": info["name"],
                "type": info["type"],
                "topic": info["topic"],
                "path": info["path"],
                "degree": 0,
            }
        )
    node_by_id = {n["id"]: n for n in nodes}

    edges: List[Dict] = []
    seen = set()
    for info in items:
        for target_name in info["outgoing"]:
            target_id = name_to_id.get(target_name)
            if target_id is None:
                # 链接目标尚不存在 —— 生成占位节点，图谱中可见（虚位以待）
                ghost_id = f"missing:{target_name}"
                if ghost_id not in node_by_id:
                    ghost = {
                        "id": ghost_id,
                        "label": target_name,
                        "name": target_name,
                        "type": "missing",
                        "topic": "",
                        "path": "",
                        "degree": 0,
                    }
                    nodes.append(ghost)
                    node_by_id[ghost_id] = ghost
                target_id = ghost_id
            key = (info["id"], target_id)
            if key in seen or info["id"] == target_id:
                continue
            seen.add(key)
            edges.append(
                {
                    "source": info["id"],
                    "source_name": info["name"],
                    "target": target_id,
                    "target_name": target_name,
                }
            )
            node_by_id[info["id"]]["degree"] += 1
            node_by_id[target_id]["degree"] += 1

    return {
        "topic": topic,
        "generated_at": datetime.datetime.now().isoformat(timespec="seconds"),
        "nodes": nodes,
        "edges": edges,
    }

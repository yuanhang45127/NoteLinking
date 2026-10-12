"""主题整体架构：盘点主题现有内容（目录树 / 笔记标题 / 小节 / 概念），
交给大模型生成「整体学习架构」文档——内容盘点、建议架构、学习路径、缺口补充。
"""
import re
from typing import Dict, List

from ..markdown_utils import strip_frontmatter
from . import vault


def topic_overview(topic: str) -> Dict:
    """收集主题的结构化概览。只取标题层级不读全文，控制上下文规模。"""
    tree = vault.get_tree(topic)
    lines: List[str] = []
    counts = {"note": 0, "term": 0}

    def headings(rel_path: str) -> List[str]:
        try:
            note = vault.read_note(rel_path)
        except Exception:  # noqa: BLE001 单篇损坏不影响整体盘点
            return []
        body = strip_frontmatter(note.get("content", ""))
        return re.findall(r"^#{1,3}\s+(.+?)\s*$", body, re.M)[:8]

    def walk(node: Dict, depth: int):
        for child in node.get("children") or []:
            t = child.get("type")
            pad = "  " * depth
            if t == "dir":
                lines.append(f"{pad}- 📁 {child['name']}/")
                walk(child, depth + 1)
            elif t == "term":
                counts["term"] += 1
                lines.append(f"{pad}    - [概念] {child.get('title') or child['name']}")
            else:
                counts["note"] += 1
                lines.append(f"{pad}    - 《{child.get('title') or child['name']}》")
                for h in headings(child["path"]):
                    lines.append(f"{pad}        · {h}")

    walk(tree, 0)
    return {"topic": topic, "outline": "\n".join(lines), **counts}


def arch_messages(overview: Dict, goal: str = "") -> List[Dict[str, str]]:
    """构造整体架构生成 prompt。"""
    system = (
        "你是学习架构师。基于给出的主题内容盘点，输出 GitHub 风格 Markdown 的"
        "「主题整体架构」文档（不要 frontmatter，不要用代码围栏包住全文），"
        "严格包含以下章节：\n\n"
        "## 现有内容盘点\n简评当前已有笔记的覆盖面与组织方式（5-8 行）\n\n"
        "## 建议知识架构\n分模块/章节的树状结构（嵌套列表），每个模块一句话说明；"
        "已有内容标 ✅，建议新增的标 🆕\n\n"
        "## 推荐学习路径\n按顺序列出学习步骤，说明前后依赖与每步的产出目标\n\n"
        "## 缺口与补充建议\n指出缺失的关键知识点与具体补齐方式\n"
    )
    goal_part = f"\n用户的学习目标：{goal}\n" if goal.strip() else ""
    user = (
        f"主题：{overview['topic']}（笔记 {overview['note']} 篇，概念 {overview['term']} 个）。{goal_part}\n\n"
        f"内容盘点：\n{overview['outline'] or '（该主题还没有笔记，请从零设计一套完整的知识架构）'}\n\n"
        "请生成这个主题的整体学习架构（中文）。"
    )
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]

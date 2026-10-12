"""主题整体架构：盘点主题现有内容（目录树 / 笔记标题 / 小节 / 概念），
交给大模型生成「整体学习架构」文档——内容盘点、建议架构、学习路径、缺口补充。
另提供按「建议知识架构」最小等级生成主题目录骨架（scaffold）。
"""
import re
from typing import Dict, List, Tuple

from fastapi import HTTPException

from ..markdown_utils import strip_frontmatter
from ..utils import resolve_in, sanitize_filename
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


# ---------------------------------------------------------------- 目录骨架
_LIST_MARK = re.compile(r"^[-*+]\s+")
_NAME_SEPS = ("：", ":", "——", "—", "（", "(")


def _arch_section(body: str, title: str) -> List[str]:
    """截取指定二级标题下的正文行（到下一个同级/更高级标题为止；### 子标题保留参与解析）。"""
    out: List[str] = []
    on = False
    for ln in body.split("\n"):
        head = re.match(r"^(#{1,6})\s+(.*?)\s*$", ln)
        if head:
            level = len(head.group(1))
            if on and level <= 2:
                break
            if on and level >= 3:
                out.append(ln)  # 子标题视为模块行
                continue
            if not on:
                on = head.group(2).strip().startswith(title)
            continue
        if on:
            out.append(ln)
    return out


def _clean_node_name(line: str) -> str:
    """列表行 → 纯目录名：去列表符/✅🆕标记/加粗，截掉冒号后的一句话说明。"""
    s = _LIST_MARK.sub("", line.strip())
    s = s.replace("🆕", "").replace("✅", "").replace("**", "").replace("`", "").strip()
    cuts = [i for i in (s.find(sep) for sep in _NAME_SEPS) if i > 0]
    if cuts:
        s = s[: min(cuts)]
    return sanitize_filename(s.strip(" 　-_·."), "") or ""


def parse_arch_chains(arch_content: str) -> List[List[str]]:
    """解析「建议知识架构」→ 各节点目录名链（顶层模块 → … → 最小等级）。

    兼容两种格式：纯嵌套列表（缩进分层）；### 子标题作模块 + 其下平铺列表作子级。
    """
    section = _arch_section(strip_frontmatter(arch_content), "建议知识架构")
    chains: List[List[str]] = []
    stack: List[Tuple[int, str]] = []
    under_sub = False  # 是否处于 ### 子标题下（其后的顶层列表视为二级）
    for raw in section:
        stripped = raw.strip()
        head3 = re.match(r"^###\s+(.*)$", stripped)
        if head3:
            name = _clean_node_name(head3.group(1))
            if name:
                del stack[:]
                stack.append((0, name))
                chains.append([name])
                under_sub = True
            continue
        if not stripped or not _LIST_MARK.match(stripped):
            continue  # 空行 / 说明文字跳过
        base = 1 if under_sub else 0
        indent = base + (len(raw) - len(raw.lstrip(" "))) // 2
        name = _clean_node_name(stripped)
        if not name:
            continue
        while stack and stack[-1][0] >= indent:
            stack.pop()
        chains.append([n for _, n in stack] + [name])
        stack.append((indent, name))
    return chains


def scaffold_from_architecture(topic: str, save_path: str = "") -> Dict:
    """按整体架构「建议知识架构」的最小等级生成主题目录骨架；已存在的目录跳过。"""
    vault_dir = vault.get_vault_dir()
    topic_dir = resolve_in(vault_dir, topic)
    if not topic_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"主题不存在：{topic}")
    arch_rel = save_path or f"{topic}/_架构/整体架构.md"
    try:
        note = vault.read_note(arch_rel)
    except HTTPException:
        raise HTTPException(status_code=404, detail="未找到整体架构文档，请先生成架构")
    chains = parse_arch_chains(note.get("content", ""))
    if not chains:
        raise HTTPException(status_code=400, detail="架构文档中未解析到「建议知识架构」目录结构")

    created: List[str] = []
    skipped: List[str] = []
    for chain in chains:
        parts = [sanitize_filename(c, "") for c in chain]
        if any(not p for p in parts):
            continue
        target = topic_dir.joinpath(*parts)
        rel = target.relative_to(vault_dir).as_posix()
        if target.exists():
            skipped.append(rel)
            continue
        target.mkdir(parents=True, exist_ok=True)
        created.append(rel)
    return {"created": created, "skipped": skipped}


def arch_leaf_chains(topic: str, save_path: str = "") -> List[List[str]]:
    """读取整体架构文档，返回「建议知识架构」中最小等级（叶子）的目录链。"""
    vault_dir = vault.get_vault_dir()
    topic_dir = resolve_in(vault_dir, topic)
    if not topic_dir.is_dir():
        raise HTTPException(status_code=404, detail=f"主题不存在：{topic}")
    arch_rel = save_path or f"{topic}/_架构/整体架构.md"
    note = vault.read_note(arch_rel)
    chains = parse_arch_chains(note.get("content", ""))
    if not chains:
        raise HTTPException(status_code=400, detail="架构文档中未解析到「建议知识架构」目录结构")
    return [c for c in chains if not any(len(o) > len(c) and o[:len(c)] == c for o in chains)]


def leaf_note_messages(topic: str, chain: List[str]) -> List[Dict[str, str]]:
    """按提纲位置（主题 → 模块 → … → 最小等级）构造单篇笔记的生成 prompt。"""
    module, title = chain[0], chain[-1]
    loc = " / ".join(chain)
    user = (
        f"笔记标题：《{title}》\n"
        f"请为《{topic}》主题撰写一篇中文学习笔记。该笔记属于「{module}」模块，在知识架构中的位置：{loc}。\n"
        "要求：\n"
        "1. 直接输出 Markdown 正文（正文从二级标题开始，不要输出一级标题）；\n"
        "2. 内容系统完整：把该小节应覆盖的核心概念讲清楚，配必要的例子；数学内容用 LaTeX 公式；\n"
        "3. 结尾加「## 小结」章节；篇幅约 800~1500 字。"
    )
    return [
        {"role": "system",
         "content": "你是专业的学习笔记作者，这篇笔记会与同主题的其他笔记组成一套完整教程，"
                    "注意与模块主题保持连贯，不要重复其他章节的展开内容。全文使用中文。"},
        {"role": "user", "content": user},
    ]

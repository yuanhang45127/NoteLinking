"""词条解释文档：选中文本 →「什么意思」→ 大模型结合上下文生成解释文档，
存放于主题的 terms/ 目录，frontmatter 记录 origin（反向链接、出处章节、原句），
与普通笔记的 [[双链]] 一起构成 Obsidian 风格的双向链接。

文档结构（供前端渲染「概念页」）：
    ## 一句话解释
    ## 在当前上下文中的含义
    ## 数学形式        （仅当术语有数学表达时）
    ## 延伸
"""
import datetime
import re
from typing import Dict, Optional, Tuple

from fastapi import HTTPException

from ..markdown_utils import append_section, ensure_frontmatter, make_excerpt, parse_frontmatter, strip_frontmatter
from ..utils import sanitize_filename
from . import vault
from .llm_service import complete

SYSTEM_PROMPT = (
    "你是术语解释助手。请解释用户给出的术语/词组，输出 GitHub 风格 Markdown"
    "（不要输出 frontmatter，不要用代码围栏包住全文），严格使用以下章节结构：\n\n"
    "## 一句话解释\n用一句话给出简明准确的定义（不超过 60 字）\n\n"
    "## 在当前上下文中的含义\n结合给出的上下文解释它在这里的含义与作用（2-4 句）\n\n"
    "## 数学形式\n仅当该术语有数学表达时书写本节，用 LaTeX（行内 $...$、独立 $$...$$）并逐个解释符号含义；"
    "与数学无关的术语请整节省略。\n\n"
    "## 延伸\n相关背景与易混淆点，最后一行固定为「相关概念：」开头，列出 2-4 个相关术语，"
    "例如：相关概念：[[损失函数]]、[[梯度下降]]\n"
)

_SENTENCE_END = "。！？!?\n"


def locate_in_note(content: str, keyword: str) -> Tuple[str, str]:
    """在笔记中定位关键词，返回 (所在章节标题, 包含关键词的原句)。"""
    body = strip_frontmatter(content)
    pos = body.find(keyword)
    section, quote = "开头", ""
    if pos < 0:
        return section, body.strip()[:120]
    for m in re.finditer(r"^#{1,4}\s+(.+?)\s*$", body[:pos], re.M):
        section = m.group(1).strip() or section
    start = max(body.rfind(ch, 0, pos) for ch in _SENTENCE_END)
    end_candidates = [i for i in (body.find(ch, pos + len(keyword)) for ch in _SENTENCE_END) if i != -1]
    end = min(end_candidates) if end_candidates else min(len(body), pos + 200)
    quote = body[start + 1: end].strip().lstrip("-*·> ").strip()
    return section or "开头", (quote or body.strip()[:120])


async def prepare_term(
    note_rel: str,
    term: str,
    context_before: str = "",
    context_after: str = "",
    language: str = "zh",
) -> Dict:
    """校验并构造概念解释生成所需的 prompt 与落盘元数据（流式/非流式共用）。"""
    term = term.strip()
    if not term:
        raise HTTPException(status_code=400, detail="词条不能为空")
    note = vault.read_note(note_rel)
    if not context_before and not context_after:
        context_before, context_after = make_excerpt(note["content"], term)
    origin_section, context_quote = locate_in_note(note["content"], term)

    lang_note = "请用中文回答。" if language == "zh" else f"请用 {language} 回答。"
    user_msg = (
        f"以下是笔记《{note['name']}》中的一段：\n\n"
        f"……{context_before.strip()[-600:]}【{term}】{context_after.strip()[:600]}……\n\n"
        f"请解释词组/术语「{term}」在这段上下文中的意思。{lang_note}"
    )
    return {
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT + lang_note},
            {"role": "user", "content": user_msg},
        ],
        "note": note,
        "term": term,
        "origin_section": origin_section,
        "context_quote": context_quote,
    }


def save_term_doc(plan: Dict, explanation: str, regenerate: bool = False) -> Dict:
    """把生成的解释落盘（新建 / 重生成 / 追加出处），返回结果结构。"""
    note = plan["note"]
    term = plan["term"]
    origin_section = plan["origin_section"]
    context_quote = plan["context_quote"]

    # 词条文档放在主题根的 terms/ 下
    topic = note["topic"]
    target_rel = f"{topic}/terms/{sanitize_filename(term, '词条')}.md"
    today = datetime.date.today().isoformat()
    source_name = note["name"]

    try:
        existing = vault.read_note(target_rel)
    except HTTPException:
        existing = None

    if existing is None:
        fm = {
            "type": "term",
            "title": term,
            "generated": True,
            "aliases": [term],
            "origin": f"[[{source_name}]]",
            "origin_path": note["path"],
            "origin_section": origin_section,
            "context_quote": context_quote,
            "sources": [source_name],
            "created": today,
        }
        content = ensure_frontmatter(f"# {term}\n", fm) + explanation.strip() + "\n"
        created = vault.create_note(target_rel, content, overwrite=True)
        return {**created, "is_new": True}

    fm, _body = parse_frontmatter(existing["content"])
    if regenerate:
        fm.update(
            {
                "origin": f"[[{source_name}]]",
                "origin_path": note["path"],
                "origin_section": origin_section,
                "context_quote": context_quote,
                "updated": today,
            }
        )
        sources = list(fm.get("sources") or [])
        if source_name not in sources:
            sources.append(source_name)
        fm["sources"] = sources
        content = ensure_frontmatter(f"# {term}\n\n" + explanation.strip() + "\n", fm)
        saved = vault.save_note(target_rel, content, _force=True)
        return {**saved, "is_new": False, "regenerated": True}

    heading = f"出现于《{source_name}》（{today}）"
    updated = append_section(existing["content"], heading, explanation.strip())
    sources = list(fm.get("sources") or [])
    if source_name not in sources:
        sources.append(source_name)
    updated = ensure_frontmatter(updated, {"sources": sources, "updated": today})
    saved = vault.save_note(target_rel, updated, _force=True)
    return {**saved, "is_new": False, "appended": True}


async def create_term_doc(
    note_rel: str,
    term: str,
    context_before: str = "",
    context_after: str = "",
    language: str = "zh",
    regenerate: bool = False,
    provider_id: str = "",
    model: str = "",
) -> Dict:
    plan = await prepare_term(note_rel, term, context_before, context_after, language)
    explanation = await complete(provider_id, plan["messages"], model)
    return save_term_doc(plan, explanation, regenerate=regenerate)


# ---- 概念 → 完整笔记 ----

CONVERT_SYSTEM_PROMPT = (
    "你是专业的学习笔记作者。用户会给出一个概念及其已有的简短解释文档，"
    "请从这个概念出发写一篇完整、深入的 Markdown 学习笔记，重点讲清"
    "「这个概念具体是什么」和「它有什么用」，严格使用以下章节结构：\n\n"
    "## 是什么\n给出准确定义，再用通俗语言/类比讲出直观理解，并交代它出现的背景与动机；"
    "若有数学表达，用 LaTeX（行内 $...$、独立 $$...$$）书写并逐个解释符号含义。\n\n"
    "## 解决什么问题\n没有它会怎样？它相比朴素做法改进在哪里。\n\n"
    "## 具体用处\n典型用法与代表性应用场景，尽量给一个可操作的小例子（代码用代码块，"
    "计算用具体数字算一遍）。\n\n"
    "## 易混淆点与常见误区\n与相近概念的边界、使用时容易踩的坑。\n\n"
    "## 相关概念\n围绕本概念梳理 3-5 个相关术语，每个用 [[双链]] 语法标注并一句话说明关系，"
    "例如：[[损失函数]] —— 衡量……\n\n"
    "正文中关键术语首次出现也用 [[术语]] 双链语法标注。"
    "不要输出 frontmatter，不要用代码围栏包住全文。"
)


def prepare_to_note(term_rel: str, language: str = "zh") -> Dict:
    """概念转笔记：读取概念文档并构造生成 prompt 与落盘目标（流式生成前调用）。"""
    concept = vault.read_note(term_rel)
    fm = concept.get("frontmatter", {})
    if fm.get("type") != "term":
        raise HTTPException(status_code=400, detail="只有概念文档（terms/ 下）才能转换为笔记")

    term = (fm.get("title") or concept["name"]).strip()
    body = strip_frontmatter(concept["content"]).strip()

    # 出处笔记的相关段落作为背景（拿不到就跳过，不影响生成）
    origin_path = fm.get("origin_path") or ""
    origin_name, origin_section, origin_quote = "", "", ""
    if origin_path:
        try:
            origin = vault.read_note(origin_path)
            origin_name = origin["name"]
            origin_section = fm.get("origin_section") or ""
            origin_quote = fm.get("context_quote") or ""
            if not origin_quote:
                _, origin_quote = make_excerpt(origin["content"], term)
        except HTTPException:
            pass

    lang_note = "全文使用中文。" if language == "zh" else f"全文使用 {language}。"
    parts = [f"概念：「{term}」"]
    if origin_name:
        parts.append(f"出处：笔记《{origin_name}》{('的「%s」一节' % origin_section) if origin_section else ''}")
    parts.append("已有的概念解释文档：\n---\n" + (body[:4000] or "（暂无内容，请依据你对该概念的理解撰写）") + "\n---")
    if origin_quote:
        parts.append(f"它在原文中的语境：……{origin_quote.strip()[:400]}……")
    parts.append(f"请从该概念出发写一篇完整的学习笔记，深入讲述它的具体解释和用处。{lang_note}")
    messages = [
        {"role": "system", "content": CONVERT_SYSTEM_PROMPT},
        {"role": "user", "content": "\n\n".join(parts)},
    ]

    target_rel, overwrite = resolve_to_note_target(concept["topic"], term, term_rel)
    return {"messages": messages, "term": term, "term_rel": term_rel, "target_rel": target_rel, "overwrite": overwrite}


def resolve_to_note_target(topic: str, term: str, term_rel: str) -> Tuple[str, bool]:
    """决定转换后笔记的落盘路径：主题根下与概念同名优先，已被占用时依次回退。

    返回 (路径, 是否覆盖)。仅当已有笔记的 frontmatter 标明由同一概念生成
    （source_term_path 一致）时才允许覆盖；否则继续回退，全部被无关笔记占用则报错。
    """
    base = sanitize_filename(term, "概念")
    for suffix in ("", "（详解）", "（详解2）", "（详解3）"):
        rel = f"{topic}/{base}{suffix}.md"
        try:
            existing = vault.read_note(rel)
        except HTTPException:
            return rel, False
        efm, _ = parse_frontmatter(existing["content"])
        if efm.get("source_term_path") == term_rel:
            return rel, True
    raise HTTPException(
        status_code=409,
        detail=f"主题下已有与「{term}」同名的笔记且并非本概念生成，请先重命名或删除后再转换",
    )


def save_to_note(plan: Dict, text: str) -> Dict:
    """把生成的完整笔记落盘，frontmatter 记录来源概念（双链 + 路径）。"""
    term = plan["term"]
    fm = {
        "title": term,
        "generated": True,
        "created": datetime.date.today().isoformat(),
        "source_term": f"[[{term}]]",
        "source_term_path": plan["term_rel"],
    }
    content = ensure_frontmatter(f"# {term}\n", fm) + text.strip() + "\n"
    return vault.create_note(plan["target_rel"], content, overwrite=plan["overwrite"])


def list_terms(topic: str = "") -> list:
    """列出词条文档（可按主题过滤），附带 origin 信息。"""
    items = []
    for info in vault.build_link_index().values():
        if info["type"] != "term":
            continue
        if topic and info["topic"] != topic:
            continue
        note = vault.read_note(info["path"])
        fm = note.get("frontmatter", {})
        origin = fm.get("origin") or ""
        if isinstance(origin, str) and origin.startswith("[[") and origin.endswith("]]"):
            origin = origin[2:-2]
        items.append(
            {
                "path": info["path"],
                "name": info["name"],
                "title": info["title"],
                "topic": info["topic"],
                "origin": origin,
                "origin_path": fm.get("origin_path") or "",
                "origin_section": fm.get("origin_section") or "",
                "sources": fm.get("sources") or [],
                "updated_at": note.get("updated_at"),
            }
        )
    return sorted(items, key=lambda x: x.get("updated_at") or "", reverse=True)


def resolve_term_reference(term_name: str, topic: str = "") -> Optional[Dict]:
    """按名称找词条文档（悬浮解释/跳转用）。"""
    for info in vault.build_link_index().values():
        if info["type"] == "term" and info["name"] == term_name:
            if not topic or info["topic"] == topic:
                return vault.read_note(info["path"])
    return None

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
    explanation = await complete(
        provider_id,
        [
            {"role": "system", "content": SYSTEM_PROMPT + lang_note},
            {"role": "user", "content": user_msg},
        ],
        model,
    )

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
        saved = vault.save_note(target_rel, content)
        return {**saved, "is_new": False, "regenerated": True}

    heading = f"出现于《{source_name}》（{today}）"
    updated = append_section(existing["content"], heading, explanation.strip())
    sources = list(fm.get("sources") or [])
    if source_name not in sources:
        sources.append(source_name)
    updated = ensure_frontmatter(updated, {"sources": sources, "updated": today})
    saved = vault.save_note(target_rel, updated)
    return {**saved, "is_new": False, "appended": True}


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

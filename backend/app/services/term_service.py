"""词条解释文档：选中文本 →「什么意思」→ 大模型结合上下文生成解释文档，
存放于主题的 terms/ 目录，frontmatter 记录 origin（反向链接），
与普通笔记的 [[双链]] 一起构成 Obsidian 风格的双向链接。
"""
import datetime
from typing import Dict, Optional

from fastapi import HTTPException

from ..markdown_utils import append_section, ensure_frontmatter, make_excerpt, parse_frontmatter
from ..utils import sanitize_filename, unique_path
from . import vault
from .llm_service import complete

SYSTEM_PROMPT = (
    "你是学习助手。请解释用户给出的术语/词组，输出 GitHub 风格 Markdown（不要输出 frontmatter），"
    "使用以下结构：\n\n"
    "## 释义\n简明准确的定义\n\n"
    "## 在当前上下文中的含义\n结合给出的上下文解释它在这里的含义与作用\n\n"
    "## 延伸\n相关概念与背景，可用 [[双链]] 指向相关术语（Obsidian 语法）\n"
)


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
    terms_dir = f"{topic}/terms"
    target_rel = f"{terms_dir}/{sanitize_filename(term, '词条')}.md"
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
            "sources": [source_name],
            "created": today,
        }
        content = ensure_frontmatter(f"# {term}\n", fm) + explanation.strip() + "\n"
        created = vault.create_note(target_rel, content, overwrite=True)
        return {**created, "is_new": True}

    fm, body = parse_frontmatter(existing["content"])
    if regenerate:
        fm.update({"origin": f"[[{source_name}]]", "updated": today})
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

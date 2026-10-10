"""Markdown 工具：frontmatter 读写、[[双链]] 提取、追加章节。"""
import re
from typing import Any, Dict, List, Optional, Tuple

import yaml

_FM_RE = re.compile(r"\A---[ \t]*\r?\n(.*?)\r?\n---[ \t]*\r?\n?", re.DOTALL)
_WIKILINK_RE = re.compile(r"\[\[([^\[\]]+?)\]\]")


def parse_frontmatter(text: str) -> Tuple[Dict[str, Any], str]:
    """返回 (frontmatter字典(可能为空), 正文)。"""
    m = _FM_RE.match(text)
    if not m:
        return {}, text
    raw = m.group(1)
    try:
        data = yaml.safe_load(raw) or {}
    except yaml.YAMLError:
        data = {}
    if not isinstance(data, dict):
        data = {}
    return data, text[m.end():]


def build_frontmatter(data: Dict[str, Any]) -> str:
    if not data:
        return ""
    dumped = yaml.safe_dump(data, allow_unicode=True, sort_keys=False, default_flow_style=False)
    return f"---\n{dumped}---\n"


def ensure_frontmatter(text: str, updates: Dict[str, Any]) -> str:
    """设置/合并 frontmatter 键，保留其余内容与原有键。"""
    data, body = parse_frontmatter(text)
    data.update(updates)
    return build_frontmatter(data) + body


def extract_wiki_links(text: str) -> List[str]:
    """提取全文（含 frontmatter）中的 [[链接]] 目标，去重保序。

    支持 [[目标|别名]] 与 [[目标#标题]] 形式。
    """
    targets: List[str] = []
    seen = set()
    for m in _WIKILINK_RE.finditer(text):
        t = m.group(1).split("|", 1)[0].split("#", 1)[0].strip()
        if t and t not in seen:
            seen.add(t)
            targets.append(t)
    return targets


def append_section(text: str, heading: str, body: str) -> str:
    """在文末追加一个 `## heading` 章节。"""
    text = text.rstrip() or ""
    block = f"\n\n## {heading}\n\n{body.strip()}\n"
    return text + block


def make_excerpt(content: str, keyword: str, width: int = 400) -> Tuple[str, str]:
    """在笔记正文中定位关键词，返回 (前文, 后文) 上下文；找不到则截取开头。"""
    body = content
    idx = body.find(keyword)
    if idx < 0:
        return "", body[: width * 2]
    start = max(0, idx - width)
    end = min(len(body), idx + len(keyword) + width)
    return body[start:idx], body[idx + len(keyword):end]


def strip_frontmatter(text: str) -> str:
    _, body = parse_frontmatter(text)
    return body

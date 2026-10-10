"""Markdown 工具测试：frontmatter、[[双链]]、摘录。"""
from app.markdown_utils import (
    append_section,
    build_frontmatter,
    ensure_frontmatter,
    extract_wiki_links,
    make_excerpt,
    parse_frontmatter,
    strip_frontmatter,
)


def test_frontmatter_roundtrip():
    text = "---\ntitle: 测试\ntype: term\n---\n\n正文内容\n"
    fm, body = parse_frontmatter(text)
    assert fm == {"title": "测试", "type": "term"}
    assert body.startswith("\n正文内容")

    fm2, body2 = parse_frontmatter("没有 frontmatter")
    assert fm2 == {} and body2 == "没有 frontmatter"


def test_build_and_ensure_frontmatter():
    text = build_frontmatter({"title": "洛必达法则", "origin": "[[极限]]"})
    fm, body = parse_frontmatter(text)
    assert fm["origin"] == "[[极限]]"

    merged = ensure_frontmatter("正文", {"type": "term", "title": "X"})
    fm3, body3 = parse_frontmatter(merged)
    assert fm3["type"] == "term" and body3.strip() == "正文"


def test_extract_wiki_links():
    text = "见 [[极限]] 与 [[洛必达法则|L'Hopital]]，以及 [[导数#一阶导数]]；origin: [[笔记A]]"
    assert extract_wiki_links(text) == ["极限", "洛必达法则", "导数", "笔记A"]
    assert extract_wiki_links("没有链接") == []
    # 去重保序
    assert extract_wiki_links("[[A]] [[A]] [[B]]") == ["A", "B"]


def test_append_section():
    out = append_section("# 标题\n\n旧内容", "新章节", "内容正文")
    assert "## 新章节" in out and "内容正文" in out and out.startswith("# 标题")


def test_make_excerpt_and_strip():
    body = "前" * 100 + "关键词" + "后" * 100
    before, after = make_excerpt(body, "关键词", width=20)
    assert "关键词" not in before and "关键词" not in after
    assert len(before) == 20 and len(after) == 20
    assert strip_frontmatter("---\ntitle: x\n---\n关键词") == "关键词"


def test_make_excerpt_not_found():
    before, after = make_excerpt("abc", "不存在", width=5)
    assert before == "" and after.startswith("abc")

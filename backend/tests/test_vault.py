"""笔记库服务测试：主题、树、CRUD、移动、搜索、反链、路径安全。"""
import pytest
from fastapi import HTTPException

from app.services import vault


def _seed():
    vault.create_topic("高等数学")
    vault.create_note("高等数学/极限与连续.md", "# 极限\n\n参见 [[洛必达法则]] 与 [[导数]]")
    vault.create_note("高等数学/terms/洛必达法则.md", "---\ntype: term\norigin: \"[[极限与连续]]\"\n---\n# 洛必达法则")
    vault.create_note("高等数学/第1章/邻域.md", "# 邻域\n内容")


def test_topic_crud(data_dir):
    t = vault.create_topic("线代")
    assert t["name"] == "线代"
    assert {x["name"] for x in vault.list_topics()} == {"线代"}
    with pytest.raises(HTTPException):  # 重名
        vault.create_topic("线代")
    vault.create_note("线代/a.md", "x")
    with pytest.raises(HTTPException):  # 非空需 recursive
        vault.delete_topic("线代")
    vault.delete_topic("线代", recursive=True)
    assert vault.list_topics() == []


def test_note_crud_and_tree(data_dir):
    _seed()
    tree = vault.get_tree("高等数学")
    names = {c["name"] for c in tree["children"]}
    assert names == {"极限与连续", "terms", "第1章"}
    terms = next(c for c in tree["children"] if c["name"] == "terms")
    assert terms["children"][0]["type"] == "term"

    note = vault.read_note("高等数学/极限与连续.md")
    assert note["topic"] == "高等数学" and "洛必达法则" in note["content"]

    vault.save_note("高等数学/极限与连续.md", "# 改过")
    assert "改过" in vault.read_note("高等数学/极限与连续.md")["content"]

    moved = vault.move_note("高等数学/第1章/邻域.md", "高等数学/第2章/邻域.md")
    assert moved["path"] == "高等数学/第2章/邻域.md"
    with pytest.raises(HTTPException):
        vault.read_note("高等数学/第1章/邻域.md")

    vault.delete_note("高等数学/第2章/邻域.md")
    with pytest.raises(HTTPException):
        vault.delete_note("高等数学/第2章/邻域.md")


def test_path_safety(data_dir):
    with pytest.raises(HTTPException):
        vault.read_note("../settings.json")
    with pytest.raises(HTTPException):
        vault.read_note("a/../../etc/passwd")
    with pytest.raises(HTTPException):
        vault.read_note("")


def test_create_duplicate_note(data_dir):
    _seed()
    with pytest.raises(HTTPException):
        vault.create_note("高等数学/极限与连续.md", "x")
    n = vault.create_note("高等数学/极限与连续.md", "覆盖", overwrite=True)
    assert "覆盖" in n["content"]


def test_search(data_dir):
    _seed()
    hits = vault.search_vault("洛必达")
    assert hits and hits[0]["name"] == "洛必达法则"
    assert vault.search_vault("不存在的词") == []


def test_backlinks_and_link_index(data_dir):
    _seed()
    bls = vault.list_backlinks("高等数学/terms/洛必达法则.md")
    assert len(bls) == 1 and bls[0]["name"] == "极限与连续"
    idx = vault.build_link_index()
    out = idx["高等数学/极限与连续"]["outgoing"]
    assert "洛必达法则" in out and "导数" in out


def test_pin_note(data_dir):
    """置顶：写 frontmatter pinned 键，列表跨主题按更新时间倒序，取消后键被移除。"""
    _seed()
    vault.create_topic("AI for Law")
    note = "高等数学/极限与连续.md"
    term = "高等数学/terms/洛必达法则.md"

    vault.set_pinned(note, True)
    vault.set_pinned(term, True)
    pinned = vault.list_pinned()
    assert {p["path"] for p in pinned} == {note, term}

    from app.markdown_utils import parse_frontmatter
    fm, _ = parse_frontmatter(vault.read_note(note)["content"])
    assert fm["pinned"] is True  # 置顶键写入 frontmatter

    vault.set_pinned(note, False)
    fm2, _ = parse_frontmatter(vault.read_note(note)["content"])
    assert "pinned" not in fm2
    assert [p["path"] for p in vault.list_pinned()] == [term]

    with pytest.raises(HTTPException):
        vault.set_pinned("不存在/缺失.md", True)


def test_favorite_note(data_dir):
    """收藏：写 frontmatter fav 键，列表跨主题按更新时间倒序，取消后键被移除。"""
    import os
    from datetime import datetime

    from app.config import get_vault_dir

    _seed()
    vault.create_topic("AI for Law")
    note = "高等数学/极限与连续.md"
    term = "高等数学/terms/洛必达法则.md"

    vault.set_favorite(note, True)
    vault.set_favorite(term, True)
    assert {p["path"] for p in vault.list_favorites()} == {note, term}

    from app.markdown_utils import parse_frontmatter
    fm, _ = parse_frontmatter(vault.read_note(note)["content"])
    assert fm["fav"] is True  # 收藏键写入 frontmatter

    # 置顶与收藏互不影响
    vault.set_pinned(note, True)
    assert {p["path"] for p in vault.list_pinned()} == {note}
    assert {p["path"] for p in vault.list_favorites()} == {note, term}

    # 按更新时间倒序（固定 mtime，保证跨秒断言稳定）
    root = get_vault_dir()
    os.utime(root / note, (1_000_000, 1_000_000))
    os.utime(root / term, (2_000_000, 2_000_000))
    favs = vault.list_favorites()
    assert [p["path"] for p in favs] == [term, note]
    assert favs[0]["updated_at"] == datetime.fromtimestamp(2_000_000).isoformat(timespec="seconds")

    vault.set_favorite(note, False)
    fm2, _ = parse_frontmatter(vault.read_note(note)["content"])
    assert "fav" not in fm2
    assert [p["path"] for p in vault.list_favorites()] == [term]

    with pytest.raises(HTTPException):
        vault.set_favorite("不存在/缺失.md", True)


def test_tree_node_updated_at(data_dir):
    """目录树 note/term 节点带 updated_at（ISO 到秒，与置顶/收藏列表同格式）。"""
    import os
    from datetime import datetime

    _seed()
    rel = "高等数学/极限与连续.md"
    from app.config import get_vault_dir
    os.utime(get_vault_dir() / rel, (1_700_000_000, 1_700_000_000))

    def find(nodes, path):
        for n in nodes:
            if n["path"] == path:
                return n
            if n.get("children"):
                r = find(n["children"], path)
                if r:
                    return r

    node = find(vault.get_tree("高等数学")["children"], rel)
    assert node["updated_at"] == datetime.fromtimestamp(1_700_000_000).isoformat(timespec="seconds")
    term = find(vault.get_tree("高等数学")["children"], "高等数学/terms/洛必达法则.md")
    assert term["updated_at"]


def test_finish_note(data_dir):
    """看完标记：写 frontmatter finished，树节点带 finished 标志，取消后全部清除。"""
    from app.markdown_utils import parse_frontmatter

    _seed()
    note = "高等数学/极限与连续.md"
    vault.set_finished(note, True)

    fm, _ = parse_frontmatter(vault.read_note(note)["content"])
    assert fm["finished"] is True

    def find(nodes, path):
        for n in nodes:
            if n["path"] == path:
                return n
            if n.get("children"):
                r = find(n["children"], path)
                if r:
                    return r

    node = find(vault.get_tree("高等数学")["children"], note)
    assert node["finished"] is True
    assert find(vault.get_tree("高等数学")["children"], "高等数学/第1章/邻域.md")["finished"] is False

    # 置顶列表同步带 finished 标志
    vault.set_pinned(note, True)
    assert vault.list_pinned()[0]["finished"] is True

    vault.set_finished(note, False)
    fm2, _ = parse_frontmatter(vault.read_note(note)["content"])
    assert "finished" not in fm2
    assert vault.list_pinned()[0]["finished"] is False

    with pytest.raises(HTTPException):
        vault.set_finished("不存在/缺失.md", True)

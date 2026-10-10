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

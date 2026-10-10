"""高亮标注测试：增删改、默认样式来自设置、样式校验。"""
import pytest
from fastapi import HTTPException

from app.services import annotations_store, vault
from app.services.settings_store import update_settings


def _seed_note():
    vault.create_topic("T")
    vault.create_note("T/n.md", "# N\n内容")


def test_annotation_crud(data_dir):
    _seed_note()
    a = annotations_store.add_annotation("T/n.md", quote="内容", prefix="# N\n", comment="我的想法")
    assert a["id"] and a["comment"] == "我的想法"
    lst = annotations_store.list_annotations("T/n.md")
    assert len(lst) == 1

    u = annotations_store.update_annotation("T/n.md", a["id"], {"color": "#00ff00", "style": "font"})
    assert u["color"] == "#00ff00" and u["style"] == "font"

    annotations_store.delete_annotation("T/n.md", a["id"])
    assert annotations_store.list_annotations("T/n.md") == []
    with pytest.raises(HTTPException):
        annotations_store.delete_annotation("T/n.md", a["id"])


def test_defaults_from_settings(data_dir):
    _seed_note()
    update_settings("highlight", {"color": "#abcdef", "style": "font"})
    a = annotations_store.add_annotation("T/n.md", quote="x")
    assert a["color"] == "#abcdef" and a["style"] == "font"


def test_invalid_style(data_dir):
    _seed_note()
    with pytest.raises(HTTPException):
        annotations_store.add_annotation("T/n.md", quote="x", style="underline")


def test_empty_quote(data_dir):
    _seed_note()
    with pytest.raises(HTTPException):
        annotations_store.add_annotation("T/n.md", quote="  ")

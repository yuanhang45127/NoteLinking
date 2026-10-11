"""后端补充功能测试：概念定位、concept_refs、考点清单、备考目标、导出、设置。"""
import asyncio
import json

import pytest

from app.main import app
from app.services import exam_service, goals_store, term_service, vault
from app.services.settings_store import load_settings


def test_locate_in_note():
    content = "# 标题\n\n## 神经元模型\n\n训练网络的核心算法反向传播，则负责把误差逐层回传。之后还有内容。\n"
    section, quote = term_service.locate_in_note(content, "反向传播")
    assert section == "神经元模型"
    assert quote.startswith("训练网络的核心算法反向传播")
    assert quote.endswith("回传")


def test_concept_refs(data_dir):
    vault.create_topic("ML")
    vault.create_note("ML/notes.md", "正文提到 反向传播 三次：反向传播、反向传播。\n还有 [[梯度下降]]")
    vault.create_note("ML/terms/反向传播.md", "---\ntype: term\n---\n# 反向传播")
    vault.create_note("ML/terms/梯度下降.md", "---\ntype: term\n---\n# 梯度下降")
    note = vault.read_note("ML/notes.md")
    from app.routers.notes import _concept_refs

    refs = {r["name"]: r["count"] for r in _concept_refs(note)}
    assert refs["反向传播"] == 3 and refs["梯度下降"] == 1


FAKE_CHECKLIST = {"points": [
    {"point": "反向传播推导", "importance": "高", "suggestion": "手推链式法则"},
    {"point": "激活函数对比", "importance": "中", "suggestion": "记 Sigmoid/ReLU 特性"},
]}


@pytest.fixture()
def mock_llm(monkeypatch):
    async def fake_complete(provider_id, messages, model="", temperature=None):
        return json.dumps(FAKE_CHECKLIST, ensure_ascii=False)

    monkeypatch.setattr(exam_service, "complete", fake_complete)


def test_checklist_flow(data_dir, mock_llm):
    vault.create_topic("ML")
    vault.create_note("ML/a.md", "# A")
    doc = asyncio.run(exam_service.generate_checklist(["ML/a.md"]))
    assert doc["topic"] == "ML" and len(doc["items"]) == 2
    got = exam_service.get_checklist("ML")
    assert got["items"][0]["mastered"] is False
    updated = exam_service.toggle_checklist_item("ML", "p1", True)
    assert updated["items"][0]["mastered"] is True
    with pytest.raises(Exception):
        exam_service.toggle_checklist_item("ML", "nope", True)


def test_goals_crud(data_dir):
    g = goals_store.add_goal("机器学习期末", "6月28日", "ML")
    assert g["title"] == "机器学习期末"
    goals_store.update_goal(g["id"], {"date": "7月1日"})
    assert goals_store.list_goals()[0]["date"] == "7月1日"
    goals_store.delete_goal(g["id"])
    assert goals_store.list_goals() == []


def test_reader_graph_settings(data_dir):
    from app.services.settings_store import update_settings

    s = update_settings("reader", {"selection_menu": False, "context_scope": "note"})
    assert s["reader"] == {"selection_menu": False, "auto_concept": True, "context_scope": "note"}
    s = update_settings("graph", {"show_missing": False})
    assert s["graph"]["show_missing"] is False
    assert "reader" in load_settings()


def test_export_vault(data_dir):
    from fastapi.testclient import TestClient

    vault.create_topic("T")
    vault.create_note("T/a.md", "# hello")

    with TestClient(app) as c:
        r = c.get("/api/export/vault")
    assert r.status_code == 200 and r.headers["content-type"] == "application/zip"
    import io
    import zipfile

    z = zipfile.ZipFile(io.BytesIO(r.content))
    assert "T/a.md" in z.namelist()


def test_topic_emoji(data_dir):
    from app.services import vault as v

    v.create_topic("ML")
    assert v.get_topic_emoji("ML") == ""
    r = v.set_topic_emoji("ML", "🤖")
    assert r == {"name": "ML", "emoji": "🤖"}
    assert v.get_topic_emoji("ML") == "🤖"
    assert v.list_topics()[0]["emoji"] == "🤖"
    # 清除
    v.set_topic_emoji("ML", "")
    assert v.get_topic_emoji("ML") == "" and v.list_topics()[0]["emoji"] == ""
    # 不存在的主题
    import pytest as _p
    from fastapi import HTTPException as _H

    with _p.raises(_H):
        v.set_topic_emoji("不存在", "📚")
    # 重命名后图标保留
    v.set_topic_emoji("ML", "🧠")
    v.rename_topic("ML", "机器学习")
    assert v.get_topic_emoji("机器学习") == "🧠"


def test_topic_emoji_api(data_dir):
    from fastapi.testclient import TestClient

    from app.main import app

    with TestClient(app) as c:
        c.post("/api/topics", json={"name": "T"})
        r = c.put("/api/topics/T/emoji", json={"emoji": "📚"})
        assert r.status_code == 200 and r.json()["emoji"] == "📚"
        assert c.get("/api/topics").json()["topics"][0]["emoji"] == "📚"
        c.put("/api/topics/T/emoji", json={"emoji": ""})
        assert c.get("/api/topics").json()["topics"][0]["emoji"] == ""

"""知识图谱测试：节点、边、词条类型、悬空链接占位、主题过滤。"""
from app.services import graph_service, vault


def _seed():
    vault.create_topic("数学")
    vault.create_note("数学/极限.md", "见 [[洛必达法则]] 和 [[悬空链接]]")
    vault.create_note(
        "数学/terms/洛必达法则.md",
        '---\ntype: term\norigin: "[[极限]]"\n---\n# 洛必达法则',
    )
    vault.create_topic("物理")
    vault.create_note("物理/力学.md", "见 [[牛顿第二定律]]")


def test_graph_nodes_and_edges(data_dir):
    _seed()
    g = graph_service.build_graph()
    by_id = {n["id"]: n for n in g["nodes"]}
    assert "数学/极限" in by_id
    assert by_id["数学/terms/洛必达法则"]["type"] == "term"
    # 悬空链接生成占位节点
    assert any(n["type"] == "missing" and n["name"] == "悬空链接" for n in g["nodes"])
    # 边：极限 -> 洛必达法则；极限 -> 悬空链接占位；洛必达 -> 极限（origin）；物理 -> 占位
    pairs = {(e["source"], e["target"]) for e in g["edges"]}
    assert ("数学/极限", "数学/terms/洛必达法则") in pairs
    assert ("数学/terms/洛必达法则", "数学/极限") in pairs
    assert ("数学/极限", "missing:悬空链接") in pairs
    # 度数统计
    assert by_id["数学/极限"]["degree"] >= 2


def test_graph_topic_filter(data_dir):
    _seed()
    g = graph_service.build_graph("物理")
    names = {n["name"] for n in g["nodes"]}
    assert "力学" in names and "极限" not in names


def test_graph_dedup(data_dir):
    vault.create_topic("T")
    vault.create_note("T/a.md", "[[b]] [[b]] [[b|别名]]")
    vault.create_note("T/b.md", "x")
    g = graph_service.build_graph()
    edges = [(e["source"], e["target"]) for e in g["edges"]]
    assert edges.count(("T/a", "T/b")) == 1

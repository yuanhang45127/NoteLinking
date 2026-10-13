"""NoteLink MCP · 备考服务器（试卷 / 判分 / 考点清单 / 备考目标）。

出卷（AI 生成，走 NoteLink 配置的模型服务商）、交卷判分、考点清单覆盖度、备考目标管理。
运行：python3 notelink_exam.py（stdio MCP）
"""
from nl_mcp import (
    ARR_STR, BOOL, NUM, STR, MCPServer, P, api_delete, api_get, api_post, api_put,
    health_tool, main,
)

server = MCPServer(
    "notelink-exam",
    "NoteLink 备考服务器：基于勾选资料 AI 出卷与判分、考点清单与掌握度、备考目标。"
    "题型：mcq（选择题）/ short（简答）/ flashcard（闪卡）。",
)
health_tool(server)


# ---------------------------------------------------------------- 试卷

@server.tool("generate_exam", "AI 出卷：基于勾选的笔记/概念生成试卷（耗时 1-3 分钟）。"
                              "返回试卷 JSON（含 exam_id 与全部题目）。", {
    "paths": {**ARR_STR, "description": "资料路径列表（笔记/概念文档）"},
    "types": {**ARR_STR, "description": "题型列表",
              "items": {"type": "string", "enum": ["mcq", "short", "flashcard"]}},
    "count": P(NUM, "题目总数，默认 10"),
    "difficulty": P(STR, "easy / medium / hard", enum=["easy", "medium", "hard"]),
    "language": P(STR, "zh 或其他语言代码，默认 zh"),
    "title": P(STR, "试卷标题，缺省自动起名"),
}, ["paths"])
def generate_exam(paths, types=None, count=10, difficulty="medium", language="zh", title=""):
    body = {"paths": paths, "types": types or ["mcq", "short"], "count": count,
            "difficulty": difficulty, "language": language}
    if title:
        body["title"] = title
    return api_post("/api/exams/generate", body)


@server.tool("list_exams", "列出全部试卷（id、标题、题型、生成时间等）。")
def list_exams():
    return api_get("/api/exams")


@server.tool("get_exam", "取试卷详情；自测时可 include_answers=false 隐藏答案。", {
    "exam_id": P(STR, "试卷 id"),
    "include_answers": P(BOOL, "是否含答案，默认 true"),
}, ["exam_id"])
def get_exam(exam_id, include_answers=True):
    return api_get(f"/api/exams/{exam_id}", include_answers=include_answers)


@server.tool("delete_exam", "删除试卷。", {"exam_id": P(STR, "试卷 id")}, ["exam_id"])
def delete_exam(exam_id):
    return api_delete(f"/api/exams/{exam_id}")


@server.tool("submit_attempt", "交卷：选择题自动判分，简答题由大模型评阅，返回逐题结果与总分。"
                               "answers 形如 [{question_id, answer}]，answer 为选项字母或文字作答。", {
    "exam_id": P(STR, "试卷 id"),
    "answers": {
        "type": "array",
        "description": "作答列表",
        "items": {
            "type": "object",
            "properties": {
                "question_id": P(STR, "题目 id"),
                "answer": P(STR, "作答内容（选择题传选项字母）"),
            },
            "required": ["question_id", "answer"],
        },
    },
}, ["exam_id", "answers"])
def submit_attempt(exam_id, answers):
    return api_post(f"/api/exams/{exam_id}/attempts", {"answers": answers})


@server.tool("list_attempts", "查看某试卷的历次作答记录与得分。", {
    "exam_id": P(STR, "试卷 id"),
}, ["exam_id"])
def list_attempts(exam_id):
    return api_get(f"/api/exams/{exam_id}/attempts")


# ---------------------------------------------------------------- 考点清单

@server.tool("generate_checklist", "基于勾选资料生成考点清单（按重要度排序，存到对应主题）。", {
    "paths": {**ARR_STR, "description": "资料路径列表"},
    "language": P(STR, "zh 或其他，默认 zh"),
}, ["paths"])
def generate_checklist(paths, language="zh"):
    return api_post("/api/exams/checklist", {"paths": paths, "language": language})


@server.tool("get_checklist", "取某主题当前的考点清单（含各项掌握情况）。", {
    "topic": P(STR, "主题名"),
}, ["topic"])
def get_checklist(topic):
    return api_get("/api/exams/checklist", topic=topic)


@server.tool("set_checklist_mastered", "标记/取消考点掌握情况（前端据此算考点覆盖度）。", {
    "topic": P(STR, "主题名"),
    "item_id": P(STR, "考点条目 id"),
    "mastered": P(BOOL, "true 已掌握 / false 未掌握"),
}, ["topic", "item_id", "mastered"])
def set_checklist_mastered(topic, item_id, mastered):
    return api_put("/api/exams/checklist", {"item_id": item_id, "mastered": mastered}, topic=topic)


# ---------------------------------------------------------------- 备考目标

@server.tool("list_goals", "列出备考目标。")
def list_goals():
    return api_get("/api/goals")


@server.tool("create_goal", "新建备考目标。", {
    "title": P(STR, "目标标题，如「期末高数一轮复习」"),
    "date": P(STR, "目标日期 YYYY-MM-DD（可选）"),
    "topic": P(STR, "关联主题（可选）"),
}, ["title"])
def create_goal(title, date="", topic=""):
    return api_post("/api/goals", {"title": title, "date": date, "topic": topic})


@server.tool("update_goal", "修改备考目标（留空的字段不改）。", {
    "goal_id": P(STR, "目标 id"),
    "title": P(STR, "新标题"),
    "date": P(STR, "新日期"),
    "topic": P(STR, "新关联主题"),
}, ["goal_id"])
def update_goal(goal_id, title="", date="", topic=""):
    body = {}
    for k, v in (("title", title), ("date", date), ("topic", topic)):
        if v:
            body[k] = v
    return api_put(f"/api/goals/{goal_id}", body)


@server.tool("delete_goal", "删除备考目标。", {"goal_id": P(STR, "目标 id")}, ["goal_id"])
def delete_goal(goal_id):
    return api_delete(f"/api/goals/{goal_id}")


if __name__ == "__main__":
    main(server)

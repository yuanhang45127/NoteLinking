# My Notebook API 接口文档

Base URL：`http://127.0.0.1:8000`（Swagger UI：`/docs`）

所有路径均相对笔记库根目录 `data/vault/`，如 `高等数学/极限与连续.md`。
流式接口使用 SSE，格式：`data: {"type":"delta","text":"…"}` → `{"type":"done"}` / `{"type":"error","message":"…"}`。

## 主题与目录树

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/topics` | 主题列表（侧边栏第一层），含笔记数 |
| POST | `/api/topics` | 建主题 `{name}` |
| PATCH | `/api/topics/{name}` | 重命名 `{name}` |
| DELETE | `/api/topics/{name}?recursive=` | 删主题（有笔记需 `recursive=true`） |
| GET | `/api/tree?path=` | 目录树（缺省=全库）；节点含 `type: dir/note/term` |

## 笔记

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/notes?path=` | 读笔记：content/frontmatter/annotations/backlinks/**concept_refs**（本文涉及的概念，含出现次数，正文纯文本提及即算） |
| POST | `/api/notes` | 建 `{path, content, overwrite}` |
| PUT | `/api/notes` | 保存 `{path, content}` |
| POST | `/api/notes/move` | 移动/重命名 `{src, dst}` |
| DELETE | `/api/notes?path=` | 删除 |
| GET | `/api/notes/backlinks?path=` | 反链列表 |
| GET | `/api/notes/resolve-link?target=&topic=` | 解析 `[[双链]]` 目标（悬浮预览/跳转） |
| GET | `/api/search?q=&topic=&limit=` | 全文搜索 |

## 高亮标注（想法默认高亮；样式跟随设置）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/annotations?path=` | 该笔记全部标注 |
| POST | `/api/annotations` | `{path, quote, prefix, suffix, occurrence, color?, style?, comment?}`；color/style 缺省用设置默认 |
| PUT | `/api/annotations/{id}?path=` | 改颜色/样式/批注 `{color?, style?, comment?}` |
| DELETE | `/api/annotations/{id}?path=` | 删除 |

锚定方式：`quote` + 前后文 `prefix/suffix` + 第几次出现 `occurrence`（前端渲染时定位到文本片段）。
`style`: `background`（背景高亮）| `font`（字体高亮）。

## LLM（大模型）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/llm/chat` | 通用对话 `{messages, provider?, model?, temperature?, stream}` |
| POST | `/api/llm/generate-note` | 生成笔记 `{topic, prompt, title?, language, stream, save_path?}`；正文大模型产出，LaTeX 用 `$…$` |
| POST | `/api/llm/ask` | 选中提问 `{path, selected_text, question?, context_before?, context_after?, stream, save_to_note?}` |
| POST | `/api/llm/tutor-chat` | 备考 AI 助教：`{paths, messages, stream}`，自动把勾选资料注入上下文（流式） |
| POST | `/api/llm/study-guide` | 学习指南 `{paths, language, save_path?}`（返回 markdown） |

## 词条（双链解释文档）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/terms` | 选中词组「什么意思」：`{path, term, context_before?, context_after?, regenerate?}`；文档落在 `<主题>/terms/<词>.md`；frontmatter 含 `origin/origin_path/origin_section/context_quote`（概念页「返回出处」「结合你读到的上下文」数据源）；章节结构：一句话解释 / 在当前上下文中的含义 / 数学形式（可选）/ 延伸；已存在则追加「出现于《原笔记》」章节 |
| GET | `/api/terms?topic=` | 词条列表（含 origin 反链信息，供「返回原文」链接） |
| GET | `/api/terms/resolve?name=&topic=` | 按名称取词条文档（悬浮解释/点击跳转） |

## 知识图谱（自动生成）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/graph?topic=` | `{nodes, edges}`；节点 `type: note/term/missing`，边由全库 `[[双链]]` 与词条 `origin` 推出 |

## 考试备考

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/exams/generate` | 出卷 `{paths, types: ["mcq","short","flashcard"], count, difficulty, language, title?}` |
| GET | `/api/exams` | 试卷列表 |
| GET | `/api/exams/{id}?include_answers=` | 试卷详情（自测时可隐藏答案） |
| DELETE | `/api/exams/{id}` | 删除 |
| POST | `/api/exams/{id}/attempts` | 交卷 `{answers: [{question_id, answer}]}`；选择自动判、简答大模型评阅，返回逐题结果与总分 |
| GET | `/api/exams/{id}/attempts` | 历次作答 |

### 考点清单与备考目标

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/exams/checklist` | 基于勾选资料生成考点清单 `{paths}` → `{topic, items:[{id,point,importance,suggestion,mastered}]}`（存 `data/checklists/`） |
| GET | `/api/exams/checklist?topic=` | 取当前主题的考点清单 |
| PUT | `/api/exams/checklist?topic=` | 标记掌握情况 `{item_id, mastered}`；前端据此算「考点覆盖度」 |
| GET | `/api/goals` | 备考目标列表 |
| POST | `/api/goals` | `{title, date?, topic?}` |
| PUT | `/api/goals/{id}` | 修改 |
| DELETE | `/api/goals/{id}` | 删除 |

题型：`mcq`（options + answer 字母）、`short`（reference_answer）、`flashcard`（front/back，自评）。

## 导入

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| POST | `/api/import/pdf` | multipart：`file`（PDF ≤50MB）+ `topic` + `name?` → 文本提取生成 md 笔记（基础实现） |
| GET | `/api/export/vault` | 全库导出为 zip（按主题目录打包） |

## 设置（服务商 / 高亮 / 考试默认值）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/settings` | 当前设置（API Key 打码，附 `supported_types`） |
| PUT | `/api/settings/providers` | 覆盖保存服务商列表；`api_key` 传空或打码值则保留旧 key |
| PUT | `/api/settings/active` | 切换默认服务商 `{provider_id}` |
| PUT | `/api/settings/highlight` | `{color, style}` |
| PUT | `/api/settings/reader` | `{selection_menu, auto_concept, context_scope}`（划选菜单 / 自动概念文档 / 上下文范围） |
| PUT | `/api/settings/graph` | `{default_filter, show_missing}` |
| PUT | `/api/settings/exam` | `{default_count, types, difficulty}` |

服务商类型 `type` 三选一，覆盖所有主流模型：

- `openai` —— 一切 OpenAI 兼容接口：OpenAI、DeepSeek、Qwen/DashScope（compatible-mode）、智谱 GLM、Kimi/Moonshot、OpenRouter、SiliconFlow、Ollama、LM Studio…（改 `base_url` 即可）
- `anthropic` —— Claude 官方接口
- `gemini` —— Google AI 接口

示例：接入 DeepSeek

```json
PUT /api/settings/providers
{"providers": [{
  "id": "deepseek", "type": "openai", "name": "DeepSeek",
  "base_url": "https://api.deepseek.com/v1",
  "api_key": "sk-xxx", "model": "deepseek-chat"
}]}
```

## 其他

- `GET /api/health` → `{ok: true}`（无需令牌）
- **访问令牌**：服务端设置环境变量 `NOTEBOOK_TOKEN` 后，除 `/api/health` 外所有 `/api/*` 需携带令牌（请求头 `X-Notebook-Token: <token>` 或查询参数 `?token=<token>`），否则 401；未设置则不校验（本地使用不受影响）。前端遇到 401 会弹出令牌输入页，令牌保存在浏览器 localStorage
- 模型调用失败统一返回 `502 {"detail": "…"}`
- 数据目录可用环境变量 `NOTEBOOK_DATA_DIR` 重定向（多开/备份用）

## 公网部署（阿里云 ECS 实测）

```bash
# 服务器 /opt/notelink 目录结构
#   backend/  frontend/dist  examples  scripts  data/
# systemd：/etc/systemd/system/notelink.service
#   Environment=NOTEBOOK_TOKEN=<令牌>
#   Environment=NOTEBOOK_DATA_DIR=/opt/notelink/data
#   ExecStart=/opt/notelink/backend/.venv/bin/python run.py --host 0.0.0.0 --port 8020
# nginx：sites-enabled/notelink → 443 (泛域名证书) 反代 127.0.0.1:8020，
#        client_max_body_size 60m，proxy_buffering off（SSE 流式必需）
# 访问：https://notelink.obsidianlyh.top（输入令牌进入）
```

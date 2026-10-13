<div align="center">

# 墨链 NoteLink

**Re：从零开始，享受 AI 学习。**

基于 Markdown 文件的开源 AI 笔记系统：**笔记 · 知识图谱 · 考试备考 · AI 助教**。
底层就是普通的 `.md` 文件夹（Obsidian 兼容思路），大模型负责生成与讲解——随时迁移、随时备份，不被任何平台锁定。

[快速开始](#-快速开始) · [功能总览](#-功能总览) · [接口文档](docs/API.md) · [MCP 接入](mcp_servers/README.md) · [参与贡献](CONTRIBUTING.md)

![Python](https://img.shields.io/badge/Python-3.9+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

</div>

## 核心理念：Re：从零开始，享受 AI 学习

学习最怕两件事：**门槛**和**失去**。NoteLink 用四条原则回应：

1. **从零开始，随时归零。** 想学什么就从零学什么：AI 替你写出第一版笔记，划选任何一句话都能让 AI 讲到你懂为止。学偏了、学废了都没关系——笔记还在文件夹里，重开一局就是。
2. **数据从第一天起就属于你。** 全部知识就是一摞 Markdown 文件，Obsidian 能直接打开，备份等于复制文件夹，迁移等于拖动文件夹。没有云端账号绑架，没有格式锁定。
3. **AI 也属于你。** 任何 OpenAI 兼容接口（OpenAI / DeepSeek / Qwen / GLM / Kimi / OpenRouter / Ollama / LM Studio…）以及 Anthropic、Gemini 都能接。模型会过时、厂商会涨价，你的笔记库不会。
4. **学习本身是享受。** 概念长成知识图谱、错题变成考点清单、划选触发讲解——让"懂了"这件事可见、可玩、可复盘。AI 不是替你学习，而是陪你把学习的正反馈拉满。

> 一句话：**把 AI 当助教，不当房东。** 房子（数据）是你的，钥匙（模型）你说了算，从零开始也不慌。

## 为什么做 NoteLink

市面上的笔记工具要么把数据锁在别人的云上，要么把 AI 能力绑定在单一厂商。NoteLink 的思路很简单：

- **数据是你的**：就是一个 Markdown 文件夹，Obsidian 可以直接打开；备份 = 复制文件夹。
- **AI 是你的**：多服务商配置、随时切换，不被任何一家模型厂商绑定。
- **每个人都能用**：内置账号系统，自建服务器后家人朋友各自注册，数据完全隔离。
- **学习闭环**：不只是存笔记——AI 生成笔记、划选即问、概念双链、知识图谱、出题陪练，一条龙。

## 功能总览

### 1. 笔记（阅读器即笔记本身）
- 笔记正文可由大模型生成（流式），LaTeX 公式渲染（KaTeX）；
- **高亮**：阅读中划选文字一键高亮并记录想法，颜色/方式可配置，标注以 sidecar JSON 存储，不污染 md 正文；点击高亮可写批注；
- **选中提问**：划选弹窗「什么意思 / 解释选段 / 高亮 / 加入对话」；解释选段流式回答，可一键回存笔记；「加入对话」把选中原文收进 AI 对话面板的上下文引用，随下一轮提问注入大模型；
- **概念双链**：选词点「什么意思」→ AI 结合上下文生成概念文档（一句话解释 / 结合上下文 / 数学形式 / 延伸），存入主题 `terms/`；正文中概念名自动渲染为紫色链接，**悬浮显示解释，点击跳转概念页**，概念页顶部「返回出处」一键回原笔记；
- 右栏：我的批注 / 本文涉及的概念 / 本页目录 / 快捷操作（导入 PDF、AI 续写本节）；
- **AI 任务后台**：所有流式生成（概念、笔记、架构、出卷、对话…）都能切到后台继续跑，右下角悬浮窗统一查看谁在跑、跑了多久、流出多少字，随时停止或切回前台；
- **Kimi Code 嵌入**：开启后可把本机 `kimi web` 服务嵌进侧边 AI 对话（设置 → Kimi Code），在 NoteLink 里直接使用 Kimi Code 完整 Agent（其 MCP 可挂 NoteLink 笔记库工具）。

### 2. 知识图谱
- 全自动扫描全库 `[[双链]]`（含概念 origin 关系）力导向布局；笔记蓝、概念紫、悬空链接灰色虚线占位；圆越大链接越多；
- 点击节点看详情与引用，双击跳转文档，拖拽布局自动保存；按 笔记/概念 筛选。

### 3. 考试备考（NotebookLM 风格）
- 左栏勾选资料（笔记/概念/PDF 导入件）+ 备考目标 + 考点覆盖度；
- AI 助教对话出卷：直接说「出 5 道选择题，难度中等」即出卷，可「换成简答题」「出得更难」；
- 随堂测验/模拟试卷：逐题作答 → 交卷判分（选择自动判、简答大模型评阅）→ 逐题解析与总分；
- 记忆闪卡（翻转卡片）、考点清单（按重要度排序、标记掌握算覆盖度）、学习指南一键生成并可存为笔记。

### 4. 文献库
- arXiv 检索一键收录、Zotero 增量同步（元数据走 Web API，PDF 走 arXiv 直下绕开配额）；
- PDF 附件下载、阅读页内嵌分栏阅读、正文提取一键转笔记；
- 阅读状态 / 标签 / 批注管理，与笔记、考试体系共用同一套知识库。

### 5. AI 助教直达（MCP）
- 附带 5 个开箱即用的 MCP 服务器（纯标准库实现），ZCode / Claude Desktop / Cursor 等 AI 工具可直接读写你的笔记库、出卷判分、检索 arXiv——在对话里说「帮我出 5 道极限的题」就能干活。见 [mcp_servers/README.md](mcp_servers/README.md)。

### 6. 账号与部署
- **账号系统**：注册 / 登录 / 会话（HttpOnly Cookie，PBKDF2 口令哈希）；没人注册时为单人开放模式，无需登录；
- **邮箱验证**（可选）：配置 SMTP（`SMTP_HOST/PORT/USER/PASS/FROM_EMAIL`）并设 `NOTELINK_EMAIL_VERIFY=1` 后，注册必须验证邮箱（6 位验证码，5 分钟有效，60 秒冷却），同一邮箱只能绑定一个账号；
- **多用户隔离**：每个用户独立的笔记库、标注、试卷、设置与 API Key；
- **旧数据迁移**：从旧版单人版升级时自动迁移，首位注册者可一键「接管」已有笔记；
- **访问令牌**（可选）：账号体系之外的第二道门，适合纯内网或过渡场景；
- PDF 导入转文本笔记、全库 zip 导出、全文搜索、反链查询、目录树、快捷键（`n`/`g`/`e`/`s`）。

## 🚀 快速开始

### Docker（推荐）

```bash
git clone https://cnb.cool/obsidianlyh.top/my-Notebook.git notelink
cd notelink
docker compose up -d --build
# 打开 http://localhost:8000
```

数据（笔记库、用户、设置）全部落在 `notelink-data` 卷里，备份它即可。

> 首位注册者在注册页可勾选「接管此服务器上已有的笔记与设置」，用于从旧版单人数据平滑升级。

### 源码运行

```bash
# 1. 后端（Python ≥ 3.9）
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run.py --port 8000        # 打开 http://127.0.0.1:8000 即是前端

# 2. 前端开发模式（可选；改前端代码热更）
cd frontend
npm install && npm run dev       # http://localhost:5173，/api 自动代理到 8000
```

体验示例笔记（高等数学、机器学习，含概念文档与双链）：

```bash
python scripts/seed_example.py
```

### 环境变量

| 变量 | 说明 |
| --- | --- |
| `NOTEBOOK_DATA_DIR` | 数据目录（默认 `./data`；Docker 镜像内为 `/data`） |
| `NOTEBOOK_TOKEN` | 可选访问令牌，设置后所有 API 需携带（`X-Notebook-Token` 头或 `?token=`） |
| `NOTEBOOK_COOKIE_SECURE` | `1` = 会话 Cookie 加 `Secure` 标记（HTTPS 反代后建议开启） |
| `NOTEBOOK_CORS_ORIGINS` | 允许的跨域来源，逗号分隔（默认仅 Vite 开发服务器；前端同源托管时无需配置） |
| `NOTELINK_EMAIL_VERIFY` | `1` = 注册必须邮箱验证（需同时配置下方 SMTP；未配置 SMTP 时保持关闭） |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASS` / `FROM_EMAIL` | 注册验证码邮件的 SMTP 配置（如阿里云 DirectMail） |
| `NOTEBOOK_TRUSTED_MARKER` | 可选内网免令牌标记，配合反代注入 `X-Notebook-Trusted` 头使用 |

更细的公网部署（nginx + HTTPS + systemd）见 [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md)。

## 目录结构

```
backend/                  # FastAPI 后端
  app/
    main.py               # 入口（鉴权中间件、CORS、SPA 托管）
    config.py             # 路径与多用户数据隔离
    routers/              # REST 接口（auth / notes / graph / exams / llm …）
    services/             # vault、auth、annotations、term、exam、pdf、llm
  tests/                  # pytest（含账号与多用户隔离）
frontend/                 # React + Vite + TS 前端
  src/
    pages/                # 阅读器 / 概念页 / 图谱 / 考试 / 设置
    components/           # Sidebar / TopBar / LoginGate / Modal / Icons
    lib/                  # markdown 渲染（KaTeX + [[双链]]）、高亮锚定
mcp_servers/              # 5 个 MCP 服务器（AI 工具直连笔记库，纯标准库）
examples/                 # 示例笔记
scripts/seed_example.py   # 示例笔记导入
docs/API.md               # 接口文档
docs/DEPLOYMENT.md        # 公网部署指南
```

交互式 API 文档：`http://127.0.0.1:<port>/docs`。

## 开发

```bash
cd backend && python -m pytest tests/ -q     # 后端测试
cd frontend && npm run build                 # 前端构建（产物由后端托管）
```

提交前请确保测试与构建都通过；前端改动建议顺手过一遍五个主页面。

## 参与贡献

欢迎 Issue 与 PR！方向包括但不限于：PDF 导入增强（标题层级识别、扫描件 OCR）、图谱小地图、移动端适配、更多 LLM 适配。见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## License

[MIT](LICENSE)

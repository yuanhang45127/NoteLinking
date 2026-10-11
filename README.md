<div align="center">

# 墨链 NoteLink

**每个人都可以通过 AI 学习知识与技能！**

基于 Markdown 文件的开源 AI 笔记系统：**笔记 · 知识图谱 · 考试备考**。
底层就是普通的 `.md` 文件夹（Obsidian 兼容思路），大模型负责生成与讲解——随时迁移、随时备份，不被任何平台锁定。

[快速开始](#-快速开始) · [功能总览](#-功能总览) · [接口文档](docs/API.md) · [参与贡献](CONTRIBUTING.md)

![Python](https://img.shields.io/badge/Python-3.9+-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-18-61DAFB?logo=react&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)
![Docker](https://img.shields.io/badge/Docker-ready-2496ED?logo=docker&logoColor=white)
![License](https://img.shields.io/badge/License-MIT-green)

</div>

## 为什么做 NoteLink

市面上的笔记工具要么把数据锁在别人的云上，要么把 AI 能力绑定在单一厂商。NoteLink 的思路很简单：

- **数据是你的**：就是一个 Markdown 文件夹，Obsidian 可以直接打开；备份 = 复制文件夹。
- **AI 是你的**：任何 OpenAI 兼容接口（OpenAI / DeepSeek / Qwen / GLM / Kimi / OpenRouter / Ollama / LM Studio…）以及 Anthropic、Gemini 都能接，多服务商配置、随时切换。
- **每个人都能用**：内置账号系统，自建服务器后家人朋友各自注册，数据完全隔离。
- **学习闭环**：不只是存笔记——AI 生成笔记、划选即问、概念双链、知识图谱、出题陪练，一条龙。

## 功能总览

### 1. 笔记（阅读器即笔记本身）
- 笔记正文可由大模型生成（流式），LaTeX 公式渲染（KaTeX）；
- **高亮**：阅读中划选文字一键高亮并记录想法，颜色/方式可配置，标注以 sidecar JSON 存储，不污染 md 正文；点击高亮可写批注；
- **选中提问**：划选弹窗「什么意思 / 解释选段 / 高亮」；解释选段流式回答，可一键回存笔记；
- **概念双链**：选词点「什么意思」→ AI 结合上下文生成概念文档（一句话解释 / 结合上下文 / 数学形式 / 延伸），存入主题 `terms/`；正文中概念名自动渲染为紫色链接，**悬浮显示解释，点击跳转概念页**，概念页顶部「返回出处」一键回原笔记；
- 右栏：我的批注 / 本文涉及的概念 / 本页目录 / 快捷操作（导入 PDF、AI 续写本节）。

### 2. 知识图谱
- 全自动扫描全库 `[[双链]]`（含概念 origin 关系）力导向布局；笔记蓝、概念紫、悬空链接灰色虚线占位；圆越大链接越多；
- 点击节点看详情与引用，双击跳转文档，拖拽布局自动保存；按 笔记/概念 筛选。

### 3. 考试备考（NotebookLM 风格）
- 左栏勾选资料（笔记/概念/PDF 导入件）+ 备考目标 + 考点覆盖度；
- AI 助教对话出卷：直接说「出 5 道选择题，难度中等」即出卷，可「换成简答题」「出得更难」；
- 随堂测验/模拟试卷：逐题作答 → 交卷判分（选择自动判、简答大模型评阅）→ 逐题解析与总分；
- 记忆闪卡（翻转卡片）、考点清单（按重要度排序、标记掌握算覆盖度）、学习指南一键生成并可存为笔记。

### 4. 账号与部署
- **账号系统**：注册 / 登录 / 会话（HttpOnly Cookie，PBKDF2 口令哈希）；没人注册时为单人开放模式，无需登录；
- **多用户隔离**：每个用户独立的笔记库、标注、试卷、设置与 API Key；
- **旧数据迁移**：从旧版单人版升级时自动迁移，首位注册者可一键「接管」已有笔记；
- **访问令牌**（可选）：账号体系之外的第二道门，适合纯内网或过渡场景；
- PDF 导入转文本笔记、全库 zip 导出、全文搜索、反链查询、目录树、快捷键（`n`/`g`/`e`/`s`）。

## 🚀 快速开始

### Docker（推荐）

```bash
git clone https://github.com/<你的用户名>/notelink.git
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

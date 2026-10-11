# 墨链 NoteLink

基于 **Markdown 文件**的个人笔记系统，三大核心能力：**笔记**、**知识图谱**、**考试备考**。
底层就是普通的 `.md` 文件夹（Obsidian 兼容思路），大模型负责生成与讲解，随时可迁移、可备份。

> 状态：后端 + 前端均已可用（前端按设计稿实现：阅读器/概念页/图谱/考试/设置五页）。

## 功能总览

### 1. 笔记（阅读器即笔记本身）
- 笔记正文可由大模型生成（流式），LaTeX 公式渲染（KaTeX）；
- **高亮**：阅读中划选文字一键高亮并记录想法，颜色/方式（背景高亮 | 字体高亮）在设置中配置，标注以 sidecar JSON 存储，不污染 md 正文；点击高亮可写批注；
- **选中提问**：划选弹窗「什么意思 / 解释选段 / 高亮」；解释选段流式回答，可一键回存笔记；
- **概念双链**：选词点「什么意思」→ 大模型结合上下文生成概念文档（一句话解释 / 结合上下文 / 数学形式 / 延伸），存入主题 `terms/`；正文中纯文本出现的概念名自动渲染为紫色概念链接，**悬浮显示一句话解释，点击跳转概念页**，概念页顶部「返回出处」一键回原笔记；
- 右栏：我的批注 / 本文涉及的概念 / 本页目录 / 快捷操作（导入 PDF、AI 续写本节）。

### 2. 知识图谱
- 全自动：扫描全库 `[[双链]]`（含概念 origin 关系）力导向布局；笔记蓝、概念紫、悬空链接灰色虚线占位；圆越大链接越多；
- 点击节点看详情与引用，双击跳转文档，拖拽布局自动保存；按 笔记/概念 筛选。

### 3. 考试备考（NotebookLM 风格）
- 左栏勾选资料（笔记/概念/PDF 导入件）+ 备考目标 + 考点覆盖度；
- AI 助教对话：直接说「出 5 道选择题，难度中等」即出卷，可「换成简答题」「出得更难」；
- 随堂测验/模拟试卷：逐题作答 → 交卷判分（选择自动判、简答大模型评阅）→ 逐题解析与总分；
- 记忆闪卡（翻转卡片）、考点清单（按重要度排序、标记掌握算覆盖度）、学习指南一键生成并可存为笔记。

### 4. 其他
- PDF 导入转文本笔记（基础实现，扫描件不支持）；全库 zip 导出；
- 全文搜索、反链查询、目录树、快捷键（n/g/e/s）；
- **模型接口**：支持当前所有主流大模型——任何 OpenAI 兼容接口（OpenAI / DeepSeek / Qwen / GLM / Kimi / OpenRouter / Ollama / LM Studio…）、Anthropic、Gemini，多服务商配置、随时切换、可测试连接。

## 快速开始

```bash
# 1. 后端（Python ≥ 3.9）
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python run.py --port 8000        # 打开 http://127.0.0.1:8000 即是前端

# 2. 前端开发模式（可选；改前端代码热更）
cd frontend
npm install && npm run dev       # http://localhost:5173，/api 自动代理到 8000

# 3. 前端构建产物由后端托管：npm run build 后直接访问后端端口即可
```

> 提示：仓库自带示例笔记（高等数学、机器学习，含概念文档），执行 `python scripts/seed_example.py` 导入后即可体验双链与图谱。注意 8000 端口如被其他服务占用，换 `--port` 即可。

## 公网访问（已部署）

服务已部署在阿里云 ECS（47.120.76.240），通过 nginx + 泛域名证书对外提供：

**<https://notelink.obsidianlyh.top>**（首次打开输入访问令牌；本地 `data/` 与服务器数据相互独立）

- 服务器目录：`/opt/notelink`，数据在 `/opt/notelink/data`（笔记库/设置/标注都在里面，备份它即可）
- 进程：`systemctl status notelink`（systemd 托管，开机自启、异常自动拉起）
- 访问令牌：环境变量 `NOTEBOOK_TOKEN`（写入在 systemd unit 中）；本地不设置则不启用
- 更新部署：本地 `git pull` 后重新 rsync `backend/app` 与 `frontend/dist` 并 `systemctl restart notelink`

## 目录结构

```
backend/                  # FastAPI 后端
  app/
    main.py               # 入口（CORS、SPA 托管、异常处理）
    services/             # vault、annotations、graph、term、exam、pdf、llm
    routers/              # REST 接口
  tests/                  # pytest（35 个）
frontend/                 # React + Vite + TS 前端（按设计稿实现）
  src/
    pages/                # NotesPage 阅读器 / ConceptPage 概念页 / GraphPage 图谱
                          # ExamPage 考试备考 / SettingsPage 设置
    components/           # Sidebar / TopBar / Modal / Icons
    lib/                  # markdown 渲染（KaTeX + [[双链]]）、高亮锚定
examples/                 # 示例笔记（可 seed 进笔记库）
scripts/seed_example.py
docs/API.md               # 完整接口文档
```

交互式 API 文档：`http://127.0.0.1:<port>/docs`。

## 待办
- [ ] PDF 导入增强（标题层级识别、扫描件 OCR）
- [ ] 图谱小地图 / 按文件夹着色

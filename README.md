# My Notebook

基于 **Markdown 文件**的个人笔记系统，三大核心能力：**笔记**、**知识图谱**、**考试备考**。
底层就是普通的 `.md` 文件夹（Obsidian 兼容思路），大模型负责生成与讲解，随时可迁移、可备份。

> 当前阶段：后端全部完成。前端等设计稿到位后按稿实现。

## 功能总览

### 1. 笔记
- 笔记正文可由大模型生成（流式输出），渲染支持 LaTeX 公式（`$...$` / `$$...$$`，前端渲染时接入）。
- **阅读器即笔记本身**：阅读中产生的想法直接高亮，高亮颜色与方式（背景高亮 / 字体高亮）在设置中配置；标注以 sidecar JSON 存储，不污染 md 正文。
- **选中提问**：选中看不懂的一段，连同上下文发给大模型解答，可一键把问答追加保存回笔记。
- **词条双链**：选中一个词组 → 弹窗点「什么意思」→ 大模型结合上下文生成解释文档，存入主题的 `terms/` 目录，`frontmatter` 记录 `origin` 反链；阅读器可悬浮显示解释、点击跳转到词条文档、再经 origin 链接回到原文（Obsidian 式双向链接）。

### 2. 知识图谱
- 全自动：扫描全库 `[[双链]]`（含词条的 origin/sources 关系），实时生成节点与边；
- 悬空链接生成占位节点（写了链接还没建文档也能看见）；支持按主题过滤。

### 3. 考试备考（参考 NotebookLM）
- 基于选定的笔记让大模型出卷：**选择题 / 简答题 / 闪卡**，可指定题量与难度；
- 交卷自动判分（选择自动判、简答大模型评阅），保留历次作答记录；
- 一键生成**备考学习指南**（速览 / 核心概念 / 关键公式 / 易错点 / 考点预测 / 记忆技巧）。

### 4. 其他
- PDF 导入转文本笔记（基础实现，扫描件不支持，优先级低）；
- 全文搜索、反链查询、目录树；
- **模型接口**：支持当前所有主流大模型——任何 OpenAI 兼容接口（OpenAI / DeepSeek / Qwen / GLM / Kimi / OpenRouter / Ollama / LM Studio…）、Anthropic、Gemini，多服务商配置、随时切换。

## 数据结构

```
data/                      # 全部用户数据（已 gitignore，注意备份）
  vault/                   # 笔记库：纯 Markdown
    <主题>/                # 主题 = 顶层文件夹（侧边栏第一层）
      *.md                 # 笔记（阅读器即笔记本身）
      terms/*.md           # 词条解释文档（双链）
  settings.json            # 模型服务商（含 API Key）、高亮偏好等
  annotations/             # 高亮标注（sidecar，按笔记路径）
  exams/                   # 试卷与作答记录
```

## 快速开始

```bash
# 1. 安装依赖（建议 Python ≥ 3.9）
cd backend
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. 启动
python run.py                # 默认 http://127.0.0.1:8000
# 开发热重载：python run.py --reload

# 3.（可选）导入示例笔记，体验双链与图谱
cd .. && python scripts/seed_example.py

# 4. 配置模型：打开 http://127.0.0.1:8000/docs → PUT /api/settings/providers
#    例如 DeepSeek：type=openai, base_url=https://api.deepseek.com/v1, model=deepseek-chat
```

交互式 API 文档：<http://127.0.0.1:8000/docs>；完整接口说明见 [docs/API.md](docs/API.md)。

## 目录结构

```
backend/
  app/
    main.py                 # FastAPI 入口（CORS、异常处理）
    config.py               # 数据目录
    schemas.py              # 请求模型
    markdown_utils.py       # frontmatter / [[双链]] 解析
    services/               # 业务：vault、annotations、graph、term、exam、pdf、llm
    routers/                # REST 接口
  tests/                    # pytest
examples/                   # 示例笔记（可 seed 进笔记库）
scripts/seed_example.py
docs/API.md
```

## 待办（等设计稿）
- [ ] 前端：左侧主题侧边栏 + 文件树；阅读器（md + LaTeX 渲染 + 高亮 + 悬浮词条 + 词条跳转/返回）
- [ ] 知识图谱可视化（力导向图）、考试界面、设置页
- [ ] PDF 导入增强（标题层级识别、扫描件 OCR）

# Handoff：文献同步（Zotero）+ 前沿论文收录

> 交接文档。目标：在 NoteLink 里落地"前沿论文收录 + Zotero 同步"，方案已与用户确认，
> 按"推荐组合"执行。实现前请通读本文，避免重复调研（结论都已验证过）。

## 1. 背景与已拍板的决策

用户需求：收录前沿论文，并且与其 Zotero 工作流共存。用户**离不开 Zotero 的浏览器插件一键收录和 BibTeX 导出**，
因此已确认：**不改造 Zotero**，桌面 Zotero 原样使用（收录 + PDF + 引用导出），NoteLink 只做"数据汇入方"。

已确认的推荐组合（用户原话：按你的推荐组合来）：

| 层 | 方案 | 容量上限 |
| --- | --- | --- |
| 元数据同步 | Zotero Web API（api.zotero.org）+ `since=版本号` 增量拉取 | 无限（免费额度只限附件，元数据不占） |
| PDF 附件 | **arXiv 直下为主**（按 arxiv_id 从 arxiv.org 拉，绕开一切配额）+ WebDAV 托底（可选，后置） | = 磁盘 |
| 条目存储 | 现有 `papers_store`（按主题 JSON），预留 SQLite+FTS 升级路径 | 个人规模（单主题数千条）够用 |

明确否决的路线（不要再调研）：
- **不在 47 服务器上装 Zotero**：Zotero 是 GUI 程序，无头 Linux 要靠 Xvfb 硬撑，sqlite 单写锁、
  无服务化设计，长期维护成本高。用户问过，已按上述理由否掉。
- **不走 zotero.org 免费 300MB 同步 PDF**：两三百篇带附件就满，无扩展性。
- **不改造 Zotero 内部/写 Zotero 插件**：桥接成本照付，还和 vault 体系割裂。

## 2. 现状盘点（能复用的都已存在）

后端（`backend/app/`）：
- `routers/papers.py`：**已有** arXiv 检索（`GET /api/papers/search-arxiv`，Atom API 解析，
  返回 title/authors/year/venue/abstract/arxiv_id/url/pdf/published/categories）+ 文献库 CRUD
  （`GET/POST /api/papers`、`PUT/DELETE /api/papers/{id}`，支持 status/tags/comment/topic 移动）。
- `services/papers_store.py`：存储层，按主题 JSON（`data/papers/<主题>.json`），READ_STATUS =
  ("unread", "reading", "done")。存储已隔离在此文件——未来换 SQLite 只动这里。
- `routers/importer.py` + PDF 导入：已有"导入 PDF 自动转文本笔记"（前端在 设置→导入与导出），
  文献 PDF → AI 精读可复用这条管线。
- `services/llm_service.py`：`complete()` / `stream_llm()` 供 AI 精读笔记生成复用。

前端（`frontend/src/`）：
- **文献库尚无任何 UI**（pages/ 里没有 Papers 页面）——`papers.py` 后端是悬空的，需要新建界面。
- 设置页：`pages/SettingsPage.tsx`，tab 结构在 TABS 数组；「导入与导出」是 IoPanel（Zotero 同步
  卡片建议放这里，或后续独立「文献」页）。

## 3. 要实现的内容（按阶段）

### 阶段 1：Zotero Web API 同步（核心）

- 设置项（前端存 localStorage 或 io tab 表单）：Zotero userID、API Key（zotero.org 设置页
  Create key → 建议只读权限即可）、可选 collection 过滤、目标主题（写入哪个主题的文献库）。
- 后端新端点（建议 `routers/papers.py` 内扩展）：
  - `GET /api/papers/zotero/status`：校验 userID+key（`GET api.zotero.org/users/{id}/collections?limit=1`
    带 header `Zotero-API-Key`），返回 collections 列表供前端选择。
  - `POST /api/papers/zotero/sync`：增量拉取条目并写入 papers_store。
- 增量协议（关键）：
  - 首次全量：`GET /users/{id}/items?limit=100&format=json`（分页 `start=`）；
  - 之后增量：`?since={lastVersion}`，只返回变动条目；
  - 每次响应头 `Last-Modified-Version` → 存为 last_version（建议存
    `data/papers/_zotero_sync.json`：`{"last_version": N, "synced_at": ...}`）。
  - 速率限制对增量同步完全够用，无需特殊处理。
- 条目映射（Zotero `item.data` → PaperIn）：
  `title → title`；`creators`（firstName/lastName 或单字段 name）→ `["姓 名", ...]`；
  `date[:4] → year`；`publicationTitle → venue`；`abstractNote → abstract`；
  `DOI → doi`；`url → url`；`tags[].tag → tags`；`itemType → 可存入 tags 或新字段`。
  预印本类型的 arXiv 条目通常自带 `arxiv_id`（在 url 或 doi 字段里，形如 `arXiv:2401.xxxxx`），解析出来。
- 去重：DOI 优先 → arxiv_id → 标题精确匹配。命中即跳过（不要覆盖用户的状态/标签/想法）。

### 阶段 2：PDF 采集

- 有 `arxiv_id` 的条目：`https://arxiv.org/pdf/{arxiv_id}` 下载到附件目录
  （建议 `data/papers/pdf/`，**不在 vault 内**，避免进笔记树；目录可配置）。
- 下载后可选自动调 PDF→文本导入（复用 importer）+ AI 精读（复用 generate-note 管线）。
- 非 arXiv 论文：阶段 2 先不做自动下载，笔记里留 doi/url 入口即可。
- WebDAV 托底（拉 Zotero 附件）：后置，用户未急需。

### 阶段 3：前端文献库界面

- 文献列表页（按主题）：标题/作者/年份/venue/标签/读状态筛选，行内操作（改状态、想法、删除）；
- 收录入口：arXiv 搜索框（调 search-arxiv）+ Zotero 同步卡片（放 设置→导入与导出 或本页）；
- 论文条目可跳转 AI 精读（复用 GenerateModal 模式）。

### 阶段 4（可选，数据量大时再做）

- papers_store JSON → SQLite + FTS5（存储层已隔离，只改 papers_store.py）；
- WebDAV 附件同步；Semantic Scholar 引用关系（"被谁引"扩展阅读）。

## 4. 部署/环境事实（已验证，勿重复踩坑）

- **用户这台 Mac 没装 Zotero**（23119 无响应）→ 本地 API 适配只能算可选项，联调用 Web API 或 mock。
- **47 服务器（root@100.93.24.87，pindou47）磁盘 40G 已用 84%，仅剩 6.3G**——PDF 若要放服务器，
  先在阿里云扩容/挂数据盘，否则只存 Mac 本地。
- NoteLink 服务运行方式：Mac 上 `backend/` 内
  `nohup .venv/bin/python run.py --host 0.0.0.0 --port 8000`（日志 `backend/server.log`），
  **后端改代码必须重启**；前端 `frontend/` 内 `npm run build`（FastAPI 托管 dist，构建即生效）。
- 后端新路由注册在 `app/main.py` 的 `include_router` 列表。
- 域名：`https://mac-notebook.obsidianlyh.top`（pindou47 nginx 反代 → Mac tailnet IP:8000，
  仅 tailnet 可达）。47 服务器 root 免密 SSH 可用。

## 5. 测试建议

- 无真实 Zotero 时：mock `api.zotero.org`（本地起个小 HTTP 服务按 Web API 格式返回条目 JSON，
  后端 base url 做成可配置即可测试）；papers_store 有现成 `add_paper` 可做断言。
- 拿到真实 userID/API Key 后：先调 status 端点验证连通，再小 collection 试同步，核对去重。
- 注意：用户的真实数据在 `data/users/default/`，测试用临时主题，**测完删干净**（参考
  `DELETE /api/topics/{name}?recursive=true`）。

## 6. 仓库当前状态（交接时点）

- 大量已完成但**未提交**的改动（用户尚未要求提交）：响应式布局、主题图标直改、流式输出实时渲染、
  设置页主题删除、架构目录骨架 + 按提纲批量生成笔记（`arch_service.py / llm.py / schemas.py`）、
  行菜单删除修复、正文内联批注、`.gitignore` 加 `*.log`、新文件
  `frontend/src/components/StreamMd.tsx`。接手后如用户要求提交，注意这些是同一批。
- 已验证可用的批量生成链路（与本 handoff 无直接关系，但同仓库）：
  `POST /api/llm/topic-architecture/scaffold`（目录骨架）与
  `/generate-notes/stream`（按提纲逐篇生成，SSE 进度）。

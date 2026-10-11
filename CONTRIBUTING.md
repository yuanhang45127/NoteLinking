# 参与贡献

感谢关注墨链 NoteLink！欢迎通过 Issue 讨论、PR 提交代码。

## 提 Issue

- **Bug**：请附上复现步骤、预期行为、实际行为，以及后端日志（脱敏后）；
- **功能建议**：说清楚使用场景——你想怎么学、现在卡在哪一步。

## 提 PR

1. Fork 仓库，从 `main` 拉分支（如 `feat/pdf-ocr`）；
2. 提交前跑通：
   ```bash
   cd backend && python -m pytest tests/ -q   # 后端测试全过
   cd frontend && npm run build               # 前端构建无报错
   ```
3. 涉及接口变动时，同步更新 [docs/API.md](docs/API.md)；
4. 提交信息用简洁的中文或英文，说明「做了什么、为什么」。

## 代码约定

- 后端：Python 3.9+，尽量只用 FastAPI 生态；数据一律落 `data/`（通过 `app/config.py` 取路径，支持多用户隔离）；
- 前端：React + TypeScript，组件风格与现有页面保持一致；
- 用户数据（笔记内容、API Key）永远不入库——`.gitignore` 已排除 `data/`。

## 方向建议

- PDF 导入增强（标题层级识别、扫描件 OCR）
- 知识图谱小地图、按文件夹着色
- 移动端适配
- 更多 LLM / Embedding 服务商适配
- 笔记模板与导入（Notion / 印象笔记迁移）

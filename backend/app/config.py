"""全局路径与基础配置。

数据目录默认为仓库根目录下的 data/（已被 .gitignore 排除），
可通过环境变量 NOTEBOOK_DATA_DIR 重定向（测试即用该变量指向临时目录）。

目录结构：
    data/
      vault/            # 笔记库：纯 Markdown，主题 = 顶层文件夹
        <主题>/
          *.md
          terms/*.md    # 词条解释文档（双链）
      settings.json     # 模型服务商、高亮偏好等设置（含 API Key，勿外传）
      annotations/      # 高亮标注（按笔记路径存放的 sidecar JSON）
      exams/            # 生成的试卷与作答记录
"""
import os
from pathlib import Path


def get_data_dir() -> Path:
    root = os.environ.get("NOTEBOOK_DATA_DIR")
    if root:
        p = Path(root).expanduser().resolve()
    else:
        p = Path(__file__).resolve().parents[2] / "data"
    return p


def get_vault_dir() -> Path:
    d = get_data_dir() / "vault"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_settings_file() -> Path:
    return get_data_dir() / "settings.json"


def get_annotations_dir() -> Path:
    d = get_data_dir() / "annotations"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_exams_dir() -> Path:
    d = get_data_dir() / "exams"
    d.mkdir(parents=True, exist_ok=True)
    return d

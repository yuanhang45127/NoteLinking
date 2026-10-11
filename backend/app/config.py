"""全局路径与基础配置（支持多用户数据隔离）。

数据目录默认为仓库根目录下的 data/（已被 .gitignore 排除），
可通过环境变量 NOTEBOOK_DATA_DIR 重定向（测试即用该变量指向临时目录）。

目录结构：
    data/
      secret.key         # 会话签名密钥（自动生成）
      users.json         # 注册用户（用户名 + 口令哈希）；为空 = 单人开放模式
      users/
        <用户名>/         # 每个用户一份独立数据
          vault/          # 笔记库：纯 Markdown，主题 = 顶层文件夹
            <主题>/
              *.md
              terms/*.md  # 词条解释文档（双链）
          settings.json   # 模型服务商、高亮偏好等
          annotations/    # 高亮标注
          exams/          # 试卷与作答
          checklists/     # 考点清单
          goals.json      # 备考目标

兼容：启动时若发现旧版单用户数据（data/vault 等），自动迁移到
users/default/，行为不变（未注册用户前为「单人开放模式」，无需登录）。
"""
import os
from contextvars import ContextVar
from pathlib import Path

# 当前请求对应的用户名（由中间件按会话解析后设置；空 = 单人开放模式的 default）
_current_user: ContextVar = ContextVar("nl_current_user", default="")


def set_current_user(user: str) -> None:
    _current_user.set(user)


def get_current_user() -> str:
    return _current_user.get()


def get_data_dir() -> Path:
    """全局数据根目录（用户注册表、密钥等全局文件所在）。"""
    root = os.environ.get("NOTEBOOK_DATA_DIR")
    if root:
        p = Path(root).expanduser().resolve()
    else:
        p = Path(__file__).resolve().parents[2] / "data"
    return p


def get_user_data_dir() -> Path:
    """当前用户的数据目录；未认证（开放模式）时落在 default。"""
    user = _current_user.get() or "default"
    return get_data_dir() / "users" / user


def get_users_root() -> Path:
    return get_data_dir() / "users"


def get_vault_dir() -> Path:
    d = get_user_data_dir() / "vault"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_settings_file() -> Path:
    return get_user_data_dir() / "settings.json"


def get_annotations_dir() -> Path:
    d = get_user_data_dir() / "annotations"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_exams_dir() -> Path:
    d = get_user_data_dir() / "exams"
    d.mkdir(parents=True, exist_ok=True)
    return d


def get_checklists_dir() -> Path:
    d = get_user_data_dir() / "checklists"
    d.mkdir(parents=True, exist_ok=True)
    return d

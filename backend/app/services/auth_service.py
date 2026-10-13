"""账号系统：注册 / 登录 / 会话（纯标准库实现，无额外依赖）。

模式：
- 单人开放模式：users.json 为空（没人注册过）时不要求登录，
  所有请求以 default 用户身份读写 —— 与旧版单人使用完全兼容；
- 多用户模式：一旦有人注册，/api/*（除 auth 与 health）都需要会话，
  每个用户的数据完全隔离（vault/标注/考试/设置/目标…）。

口令：PBKDF2-HMAC-SHA256（20 万轮，随机盐），存 data/users.json。
会话：HMAC-SHA256 签名的令牌 `username.expiry.sig`，签名密钥在
data/secret.key（首次自动生成）；通过 HttpOnly Cookie（nl_session）
或 X-Session 请求头携带，默认 30 天有效。
"""
import base64
import hashlib
import hmac
import json
import re
import secrets
import time
from pathlib import Path
from typing import Dict, List, Optional

from fastapi import HTTPException

from ..config import get_data_dir, get_users_root, get_user_data_dir

USERNAME_RE = re.compile(r"^[A-Za-z0-9_\-\u4e00-\u9fa5]{2,32}$")
SESSION_COOKIE = "nl_session"
SESSION_TTL = 30 * 24 * 3600
PBKDF2_ROUNDS = 200_000


# ---------------------------------------------------------------- 密钥
def _secret_key() -> bytes:
    f = get_data_dir() / "secret.key"
    if not f.exists():
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_bytes(base64.b64encode(secrets.token_bytes(32)))
    try:
        return base64.b64decode(f.read_bytes())
    except Exception:
        return b"nl-fallback-secret"


# ---------------------------------------------------------------- 用户存储
def _users_file() -> Path:
    return get_data_dir() / "users.json"


def _load_users() -> List[Dict]:
    f = _users_file()
    if not f.exists():
        return []
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        return data.get("users", []) if isinstance(data, dict) else []
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return []


def _save_users(users: List[Dict]) -> None:
    f = _users_file()
    f.parent.mkdir(parents=True, exist_ok=True)
    tmp = f.with_suffix(".json.tmp")
    tmp.write_text(json.dumps({"version": 1, "users": users}, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(f)


def users_count() -> int:
    return len(_load_users())


def list_usernames() -> List[str]:
    return [u["username"] for u in _load_users()]


def _hash_password(password: str, salt_hex: str) -> str:
    return hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), bytes.fromhex(salt_hex), PBKDF2_ROUNDS
    ).hex()


def email_taken(email: str) -> bool:
    """该邮箱是否已被其他账号绑定（注册邮箱验证时防重复绑定）。"""
    email = (email or "").strip().lower()
    if not email:
        return False
    return any((u.get("email") or "").lower() == email for u in _load_users())


def register_user(username: str, password: str, claim_existing: bool = False,
                  email: str = "") -> Dict:
    """注册新用户。首一个注册者可勾选接管旧版单人数据（users/default）。

    返回 {"username": ...}；失败抛 HTTPException。
    """
    username = (username or "").strip()
    password = password or ""
    if not USERNAME_RE.match(username):
        raise HTTPException(
            status_code=400,
            detail="用户名需为 2-32 位字母、数字、中文、_ 或 -",
        )
    if len(password) < 6:
        raise HTTPException(status_code=400, detail="密码至少 6 位")

    users = _load_users()
    if any(u["username"] == username for u in users):
        raise HTTPException(status_code=409, detail=f"用户名已被注册：{username}")

    # 接管旧数据：users.json 为空且存在 default 数据目录
    migrated_from = None
    if claim_existing and not users:
        default_dir = get_users_root() / "default"
        target_dir = get_users_root() / username
        if default_dir.exists() and username != "default" and not target_dir.exists():
            default_dir.rename(target_dir)
            migrated_from = "default"

    user_dir = get_users_root() / username
    (user_dir / "vault").mkdir(parents=True, exist_ok=True)

    salt = secrets.token_hex(16)
    users.append(
        {
            "username": username,
            "salt": salt,
            "hash": _hash_password(password, salt),
            "email": (email or "").strip(),
            "created": time.strftime("%Y-%m-%d %H:%M:%S"),
        }
    )
    _save_users(users)
    if migrated_from:
        return {"username": username, "claimed_existing": True}
    return {"username": username}


def verify_user(username: str, password: str) -> bool:
    for u in _load_users():
        if u["username"] == username:
            return hmac.compare_digest(u["hash"], _hash_password(password, u["salt"]))
    # 防计时探测：假校验一次
    _hash_password(password or "x", "00" * 16)
    return False


# ---------------------------------------------------------------- 会话
def _b64e(s: str) -> str:
    return base64.urlsafe_b64encode(s.encode("utf-8")).decode("ascii").rstrip("=")


def _b64d(s: str) -> str:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4)).decode("utf-8")


def create_session_token(username: str) -> str:
    exp = int(time.time()) + SESSION_TTL
    user_b64 = _b64e(username)
    payload = f"{user_b64}.{exp}"
    sig = hmac.new(_secret_key(), payload.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"{payload}.{sig}"


def resolve_session_token(token: str) -> Optional[str]:
    """校验会话令牌，返回用户名；无效/过期返回 None。用户名经 base64url 编码，
    保证 Cookie 值为 ASCII（中文用户名也能正常签发会话）。"""
    if not token or token.count(".") != 2:
        return None
    try:
        user_b64, exp, sig = token.split(".")
        username = _b64d(user_b64)
        if int(exp) < time.time():
            return None
        expect = hmac.new(
            _secret_key(), f"{user_b64}.{exp}".encode("utf-8"), hashlib.sha256
        ).hexdigest()
        if not hmac.compare_digest(sig, expect):
            return None
        if username != "default" and username not in list_usernames():
            return None
        return username
    except (ValueError, IndexError, UnicodeDecodeError):
        return None


def session_cookie_header(token: str, secure: bool = False) -> str:
    """构造 Set-Cookie 响应头值（routers/auth.py 用 Response.set_cookie，此处备用）。"""
    flags = f"HttpOnly; SameSite=Lax; Path=/; Max-Age={SESSION_TTL}"
    if secure:
        flags += "; Secure"
    return f"{SESSION_COOKIE}={token}; {flags}"


# ---------------------------------------------------------------- 旧数据迁移
def migrate_legacy_single_user() -> bool:
    """旧版单用户数据（data/vault、data/settings.json…）迁移到 users/default。

    旧数据指 data 根下的 vault / settings.json / annotations / exams /
    checklists / goals.json。users/default 里已有任何文件（说明多用户模式
    已真正启用）时不动；否则合并迁移，可安全地重复调用（幂等）。
    """
    base = get_data_dir()
    legacy_items = ["vault", "settings.json", "annotations", "exams", "checklists", "goals.json"]
    has_legacy = any((base / item).exists() for item in legacy_items)
    if not has_legacy:
        return False
    default_dir = get_users_root() / "default"
    # default 下已有文件：视为已启用，避免覆盖真实数据
    if any(p.is_file() for p in default_dir.rglob("*")):
        return False
    moved = False
    for item in legacy_items:
        src = base / item
        if src.exists():
            _merge_move(src, default_dir / item)
            moved = True
    return moved


def _merge_move(src: Path, dst: Path) -> None:
    """把 src 移动为 dst；dst 已存在时递归合并内容（同名文件保留 dst）。"""
    import shutil

    if dst.exists():
        if src.is_dir() and dst.is_dir():
            for child in src.iterdir():
                _merge_move(child, dst / child.name)
            if not any(src.iterdir()):
                src.rmdir()
        # dst 是同名文件：保留 dst，src 留在原地不动（不丢数据）
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(src), str(dst))


__all__ = [
    "register_user", "verify_user", "users_count", "list_usernames",
    "email_taken",
    "create_session_token", "resolve_session_token",
    "session_cookie_header", "SESSION_COOKIE",
    "migrate_legacy_single_user",
]

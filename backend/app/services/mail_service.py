"""注册邮箱验证码：SMTP 发送（复用阿里云 DirectMail 配置）+ 内存验证码存储。

开关：配置 SMTP_HOST/SMTP_USER/SMTP_PASS 且 NOTELINK_EMAIL_VERIFY=1 时，
注册必须提供已验证邮箱；未配置时本模块完全不参与请求路径。
存储为单进程内存实现（重启即失效，可接受）。
"""
import hmac
import os
import re
import secrets
import smtplib
import threading
import time
from email.header import Header
from email.mime.text import MIMEText
from email.utils import formataddr
from typing import Dict, Optional, Tuple

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
CODE_TTL = 5 * 60            # 验证码 5 分钟有效
RESEND_COOLDOWN = 60         # 重发冷却秒数
SEND_LIMIT_PER_HOUR = 5      # 每邮箱每小时发送上限（防刷）

_lock = threading.Lock()
_store: Dict[str, Dict] = {}  # email -> {code, expires, sends: [(ts)]}


def _cfg() -> Tuple[str, int, str, str, str]:
    host = os.environ.get("SMTP_HOST", "").strip()
    port = int(os.environ.get("SMTP_PORT", "465") or 465)
    user = os.environ.get("SMTP_USER", "").strip()
    password = os.environ.get("SMTP_PASS", "").strip()
    from_email = os.environ.get("FROM_EMAIL", "").strip() or user
    return host, port, user, password, from_email


def smtp_configured() -> bool:
    host, _, user, password, _ = _cfg()
    return bool(host and user and password)


def email_verify_enabled() -> bool:
    """有效开关 = 总开关 AND SMTP 已配置（防止配错把注册锁死）。"""
    on = os.environ.get("NOTELINK_EMAIL_VERIFY", "").strip().lower() in ("1", "true", "yes")
    return on and smtp_configured()


def send_verification_code(email: str, code: str) -> None:
    """经 SMTP 发送验证码；失败抛异常由路由转 502。"""
    host, port, user, password, from_email = _cfg()
    msg = MIMEText(
        f"您的 NoteLink（墨链）注册验证码是：{code}\n\n{CODE_TTL // 60} 分钟内有效。"
        "如非本人操作，请忽略本邮件。",
        "plain", "utf-8",
    )
    msg["Subject"] = Header("【墨链 NoteLink】您的验证码", "utf-8")
    msg["From"] = formataddr((str(Header("墨链 NoteLink", "utf-8")), from_email))
    msg["To"] = email
    with smtplib.SMTP_SSL(host, port, timeout=20) as s:
        s.login(user, password)
        s.sendmail(from_email, [email], msg.as_string())


def issue_code(email: str) -> Tuple[Optional[str], Optional[int]]:
    """生成并寄出验证码。返回 (error, retry_after)。
    error 为 None 表示已发送；否则为错误描述，retry_after 为冷却剩余秒数。"""
    now = time.time()
    with _lock:
        rec = _store.get(email)
        sends = [t for t in (rec or {}).get("sends", []) if now - t < 3600]
        if len(sends) >= SEND_LIMIT_PER_HOUR:
            return f"发送太频繁，请 {int(3600 - (now - sends[0])) // 60 + 1} 分钟后再试", None
        if rec and now < rec.get("resend_after", 0):
            return None, int(rec["resend_after"] - now) + 1
        code = f"{secrets.randbelow(1_000_000):06d}"
        _store[email] = {
            "code": code,
            "expires": now + CODE_TTL,
            "resend_after": now + RESEND_COOLDOWN,
            "sends": sends + [now],
        }
    try:
        send_verification_code(email, code)
    except Exception as e:  # noqa: BLE001 —— 发送失败作废该码，避免重发空等
        with _lock:
            _store.pop(email, None)
        raise
    return None, None


def verify_code(email: str, code: str) -> bool:
    """校验验证码：对则销毁返回 True；错则累计尝试次数，满 5 次作废（防枚举），
    过期即失效。"""
    now = time.time()
    with _lock:
        rec = _store.get(email)
        if not rec or now >= rec["expires"]:
            _store.pop(email, None)
            return False
        ok = hmac.compare_digest(rec["code"], (code or "").strip())
        if ok:
            _store.pop(email, None)
        else:
            rec["attempts"] = rec.get("attempts", 0) + 1
            if rec["attempts"] >= 5:
                _store.pop(email, None)
        return ok


def clear_code(email: str) -> None:
    with _lock:
        _store.pop(email, None)


__all__ = [
    "EMAIL_RE", "email_verify_enabled", "smtp_configured",
    "issue_code", "verify_code", "clear_code", "send_verification_code",
]

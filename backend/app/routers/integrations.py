"""外部工具集成：探测本机 Kimi Code Web（`kimi web`）服务，供前端嵌入侧边对话。

安全说明：enabled 默认关闭——开启后任何能登录本服务的人都会拿到本机 kimi web 的访问，
单人本地部署建议开启，多用户部署请谨慎评估。
"""
import os
import urllib.error
import urllib.request
from pathlib import Path

from fastapi import APIRouter

from ..services.settings_store import load_settings

router = APIRouter(prefix="/api/integrations", tags=["integrations"])

_TOKEN_FILE = Path.home() / ".kimi-code" / "server.token"
_DEFAULT_PORT = 58627
# kimi web 端口被占用时自动 +1（多实例依次后移），探测范围内任一端口视为活着
_PROBE_PORTS = 4
_PROBE_TIMEOUT = 1.0


def _kimi_web_alive(port: int) -> bool:
    """kimi web 对无鉴权请求回 401——收到 200/401 即视为服务在线。"""
    try:
        req = urllib.request.Request(f"http://127.0.0.1:{port}/openapi.json", method="GET")
        with urllib.request.urlopen(req, timeout=_PROBE_TIMEOUT) as resp:
            return resp.status in (200, 401)
    except urllib.error.HTTPError as e:
        return e.code in (200, 401)
    except Exception:  # noqa: BLE001 —— 连接拒绝/超时统一视为不在线
        return False


@router.get("/kimi-web")
def kimi_web_status():
    s = load_settings()
    cfg = s.get("kimi_web") or {}
    enabled = bool(cfg.get("enabled")) or os.environ.get("NOTELINK_KIMI_WEB", "").strip() == "1"
    try:
        port = int(cfg.get("port") or _DEFAULT_PORT)
    except (TypeError, ValueError):
        port = _DEFAULT_PORT
    running = False
    url = ""
    if enabled:
        for p in range(port, port + _PROBE_PORTS):
            if _kimi_web_alive(p):
                running = True
                url = f"http://127.0.0.1:{p}"
                break
    token = ""
    if running and _TOKEN_FILE.exists():
        try:
            token = _TOKEN_FILE.read_text(encoding="utf-8").strip()
        except OSError:
            token = ""
    return {"enabled": enabled, "running": running, "url": url, "token": token}

# 公网部署指南

单机自用直接 `docker compose up -d` 就够了。要安全地暴露到公网，推荐方案：
**HTTPS 反代（nginx / Caddy）+ Docker + 可选访问令牌**。

## 1. Docker 起服务

```bash
docker compose up -d --build
# 服务监听 127.0.0.1:8000（compose 里可改为 127.0.0.1:8000:8000 更安全）
```

## 2. nginx 反向代理（HTTPS）

```nginx
server {
    listen 443 ssl;
    server_name notelink.example.com;          # 换成你的域名
    ssl_certificate     /etc/letsencrypt/live/example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_buffering off;                    # SSE 流式输出必需
        proxy_read_timeout 300s;
    }
}
```

> 反代务必不要透传 `X-Notebook-Trusted` 头（公网 server 块中 `proxy_set_header X-Notebook-Trusted "";`），
> 否则设置了 `NOTEBOOK_TRUSTED_MARKER` 的部署可被客户端伪造该头绕过令牌。

## 3. 加固选项

| 措施 | 做法 |
| --- | --- |
| 会话 Cookie 强制 Secure | compose 环境变量 `NOTEBOOK_COOKIE_SECURE=1` |
| 第二道访问令牌 | `NOTEBOOK_TOKEN=<随机串>`；之后浏览器首访会要求输入令牌（也可由反代注入） |
| 内网免令牌 | 设置 `NOTEBOOK_TRUSTED_MARKER`，由内网入口的反代注入 `X-Notebook-Trusted` |
| 只限内网/VPN | 服务不暴露公网端口，仅 Tailscale/WireGuard 等内网可达，天然免令牌 |

## 4. 数据与备份

- Docker：备份 `notelink-data` 卷（或宿主机 bind 目录）；
- 源码部署：备份 `data/` 目录；
- 里面有笔记库、用户表（`users.json`）、会话密钥（`secret.key`）与每个用户独立的设置——**备份整个目录即可完整迁移**。
- 换机迁移：停服 → 拷贝数据目录 → 新机起服 → 恢复。

## 5. 升级版本

```bash
git pull
docker compose up -d --build
```

旧版单人数据（`data/vault`、`data/settings.json`…）会在启动时自动迁移到
`users/default/`，首位注册者勾选「接管此服务器上已有的笔记与设置」即可收编。

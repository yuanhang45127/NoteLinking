# ---------- 阶段一：构建前端 ----------
FROM node:20-alpine AS web
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# ---------- 阶段二：运行镜像 ----------
FROM python:3.12-slim
WORKDIR /app

COPY backend/requirements.txt ./backend/
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ ./backend/
COPY --from=web /build/dist ./frontend/dist

# 数据（笔记库、用户、设置）统一落在 /data，挂卷即可持久化
ENV NOTEBOOK_DATA_DIR=/data \
    PYTHONUNBUFFERED=1
VOLUME ["/data"]
EXPOSE 8000

# 非 root 运行（uid 1000，与大多数 Linux 首个用户一致，方便 bind mount）
RUN useradd -m -u 1000 notelink && mkdir -p /data && chown -R notelink:notelink /app /data
USER notelink

WORKDIR /app/backend
CMD ["python", "run.py", "--host", "0.0.0.0", "--port", "8000"]

# syntax=docker/dockerfile:1
# ============================================================
# DeepSearch Agents - 后端多阶段构建镜像
#   阶段一 builder：uv 安装锁定依赖 + 复制源码
#   阶段二 runtime ：精简 Python 3.12 运行镜像
# ============================================================

FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# 先复制依赖清单，利用 Docker 层缓存避免每次改源码都重新装依赖
COPY pyproject.toml requirements.txt uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# 再复制应用源码
COPY app ./app

# ---------- 运行阶段 ----------
FROM python:3.12-slim

WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/app/.venv/bin:$PATH"

# 运行时目录（session 产物与上传暂存）由 server.py 自动创建
COPY --from=builder /app/.venv ./.venv
COPY --from=builder /app/app ./app

EXPOSE 8000
CMD ["uvicorn", "app.api.server:app", "--host", "0.0.0.0", "--port", "8000"]

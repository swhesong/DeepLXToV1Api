# 使用官方 Python 3.9 精简镜像
FROM python:3.9-slim

# 设置环境变量
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # 修改：统一 worker 环境变量名，方便管理
    UVICORN_WORKERS=2

# 安装系统依赖
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 修正：创建与 docker-compose.yml 中 user: "1000:1000" 匹配的非 root 用户
RUN groupadd -r -g 1000 appuser && useradd --no-log-init -r -u 1000 -g appuser appuser

# 设置工作目录
WORKDIR /app

# 复制和安装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码并设置所有权
COPY --chown=appuser:appuser . .

# 修正：创建目录并按要求赋予最大化权限(777)，确保任何情况都可写
RUN mkdir -p /app/results /app/logs && \
    chown -R appuser:appuser /app/results /app/logs && \
    chmod -R 777 /app/results /app/logs

# 切换到非 root 用户
USER appuser

# 暴露应用端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 修改：使用统一的 $UVICORN_WORKERS 变量
CMD exec uvicorn main:app --host 0.0.0.0 --port 8000 --workers $UVICORN_WORKERS --loop asyncio --log-level info
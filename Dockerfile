# 使用官方 Python 3.9 精简镜像
FROM python:3.9-slim

# 设置环境变量，提升 Python 在容器中的运行效率
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    # 推荐：通过环境变量控制 worker 数量，提供部署灵活性
    WORKERS_PER_CORE=2

# 设置工作目录
WORKDIR /app

# 安装系统依赖，并清理缓存以减小镜像体积
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# 创建非 root 用户和组，用于安全运行应用
RUN groupadd -r appuser && useradd --no-log-init -r -g appuser appuser

# 复制依赖文件（利用层缓存）
COPY requirements.txt .

# 安装 Python 依赖
RUN pip install --no-cache-dir -r requirements.txt

# 修正1：合并为单行 COPY，一次性完成复制和权限设置，提高效率并减小镜像体积
COPY --chown=appuser:appuser . .

# 创建应用需要写入的目录，并设置权限
RUN mkdir -p /app/results /app/logs && \
    chown -R appuser:appuser /app/results /app/logs

# 切换到非 root 用户
USER appuser

# 暴露应用端口
EXPOSE 8000

# 健康检查
HEALTHCHECK --interval=30s --timeout=10s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 推荐：使用 exec 启动并用环境变量配置 workers，更灵活且能正确处理信号
CMD exec uvicorn main:app --host 0.0.0.0 --port 8000 --workers $WORKERS_PER_CORE --loop asyncio --log-level info

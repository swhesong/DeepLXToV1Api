# 使用官方 Python 3.9 精简镜像
FROM python:3.9-slim

# 设置环境变量，提高效率和一致性
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# 安装系统依赖（仅保留健康检查必须的 curl）
RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

# 设置工作目录
WORKDIR /app

# 复制 requirements.txt 并安装依赖
# 这一步可以利用 Docker 的层缓存
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制所有应用代码到工作目录
COPY . .

# 暴露应用端口
EXPOSE 8000

# 健康检查
# 由于容器以 root 运行，此命令也以 root 身份执行
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# 默认启动命令
# 使用 exec 确保 uvicorn 成为主进程 (PID 1)，能正确接收和处理信号
# --workers 参数已被移除，将由 docker-compose.yml 中的环境变量 UVICORN_WORKERS 控制
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]

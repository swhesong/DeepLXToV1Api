#!/bin/sh

# 使用 exec 启动 uvicorn，这样 uvicorn 会替换掉 shell 进程，成为 PID 1
# 这对于接收信号（如 SIGTERM）以实现优雅停机至关重要
exec uvicorn main:app --host 0.0.0.0 --port 8000 --workers ${UVICORN_WORKERS:-1}

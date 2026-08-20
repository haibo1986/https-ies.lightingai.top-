#!/usr/bin/env bash
# IES 工具一键启动：后端 (127.0.0.1:8000) + 前端 (127.0.0.1:5173)
# 用法：bash start.sh   停止：关闭终端窗口或 Ctrl+C
set -euo pipefail
cd "$(dirname "$0")"

(cd backend && .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000) &
BACKEND_PID=$!

(cd frontend && npm run dev) &
FRONTEND_PID=$!

echo "=============================="
echo " 后端 PID: $BACKEND_PID (端口 8000)"
echo " 前端 PID: $FRONTEND_PID (端口 5173)"
echo " 浏览器打开: http://localhost:5173"
echo " 停止服务: 关闭本窗口 或 kill $BACKEND_PID $FRONTEND_PID"
echo "=============================="

wait

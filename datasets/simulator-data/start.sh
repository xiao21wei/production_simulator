#!/usr/bin/env bash
# 一键启动：把本文件夹整体打包到别的服务器后，解压 → pip install -r requirements.txt → ./start.sh 即可
set -e
cd "$(dirname "$0")"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"
exec python3 -m uvicorn app.main:app --host "$HOST" --port "$PORT"

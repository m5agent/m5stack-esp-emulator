#!/bin/bash
set -e
cd "$(dirname "$0")"
PORT="${PORT:-8787}"
( sleep 1; open "http://127.0.0.1:${PORT}/platform/web/" ) &
exec python3 platform/tools/serve.py "$PORT"

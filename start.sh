#!/bin/bash
set -eu
cd "$(dirname "$0")"
PORT="${PORT:-8787}"
task_python="${M5_PYTHON:-}"
if [ -z "$task_python" ]; then
  for candidate in python3 python3.13 python3.12 python3.11 python3.10; do
    if command -v "$candidate" >/dev/null 2>&1 && "$candidate" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
      task_python="$candidate"
      break
    fi
  done
fi
if [ -z "$task_python" ] || ! "$task_python" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
  echo "Device Service requires Python 3.10+. Set M5_PYTHON to a compatible interpreter." >&2
  exit 2
fi
if [ "${M5_OPEN_BROWSER:-1}" = 1 ] && command -v open >/dev/null 2>&1; then
  ( sleep 1; open "http://127.0.0.1:${PORT}/platform/web/" ) &
fi
exec "$task_python" platform/tools/serve.py "$PORT" "$@"

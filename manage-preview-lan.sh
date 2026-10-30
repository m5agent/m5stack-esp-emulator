#!/usr/bin/env bash
# Manage only the temporary opaque LAN bridge; never restart Device Service.
set -euo pipefail
PREVIEW_REPO_ROOT="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
PREVIEW_PYTHON="${PREVIEW_LAN_PYTHON:-python3}"
if ! command -v "$PREVIEW_PYTHON" >/dev/null 2>&1; then
  printf '%s\n' 'Python 3 is required; set PREVIEW_LAN_PYTHON to its executable.' >&2
  exit 1
fi
if [[ $# -eq 0 ]]; then
  set -- help
fi
exec "$PREVIEW_PYTHON" "$PREVIEW_REPO_ROOT/scripts/preview_lan_proxy.py" \
  --state-dir "$PREVIEW_REPO_ROOT/.work/preview-lan-proxy" "$@"

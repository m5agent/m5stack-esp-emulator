#!/usr/bin/env python3
"""Serve one controlled HTTP request through a QEMU user-net guestfwd."""
from __future__ import annotations

import argparse
import fcntl
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def read_headers(limit: int = 64 * 1024) -> bytes:
    data = bytearray()
    while b"\r\n\r\n" not in data and len(data) < limit:
        chunk = sys.stdin.buffer.readline()
        if not chunk:
            break
        data.extend(chunk)
    return bytes(data)


def request_record(request: bytes) -> dict[str, Any]:
    lines = request.decode("iso-8859-1", errors="replace").splitlines()
    path = ""
    if lines:
        parts = lines[0].split()
        if len(parts) >= 2:
            path = parts[1]
    host = ""
    for line in lines[1:]:
        if line.lower().startswith("host:"):
            host = line.split(":", 1)[1].strip()
            break
    return {
        "path": path,
        "host": host,
        "received_at": datetime.now(timezone.utc).isoformat(),
        "fixture_generation": 1,
        "transport": "qemu-guestfwd",
    }


def append_record(path: Path, record: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = path.with_name(path.name + ".lock")
    with lock_path.open("a+", encoding="utf-8") as lock_file:
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX)
        try:
            try:
                loaded = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                loaded = []
            rows = loaded if isinstance(loaded, list) else []
            rows.append(record)
            temporary = path.with_name(
                f".{path.name}.{os.getpid()}.tmp"
            )
            temporary.write_text(
                json.dumps(rows, indent=2) + "\n",
                encoding="utf-8",
            )
            temporary.replace(path)
        finally:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--log", type=Path, required=True)
    parser.add_argument("--body-hex", required=True)
    args = parser.parse_args()
    try:
        body = bytes.fromhex(args.body_hex)
    except ValueError:
        parser.error("--body-hex must be valid hexadecimal")
    request = read_headers()
    append_record(args.log, request_record(request))
    response = (
        b"HTTP/1.0 200 OK\r\n"
        b"Content-Type: text/plain\r\n"
        + f"Content-Length: {len(body)}\r\n".encode()
        + b"Connection: close\r\n\r\n"
        + body
    )
    sys.stdout.buffer.write(response)
    sys.stdout.buffer.flush()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

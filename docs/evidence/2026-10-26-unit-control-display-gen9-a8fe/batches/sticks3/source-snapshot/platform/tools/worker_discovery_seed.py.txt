#!/usr/bin/env python3
"""Serve HMAC-authenticated worker discovery beacons over unicast HTTP."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from worker_auth import WorkerAuthError, read_master_token_file
from worker_discovery import (
    DEFAULT_DISCOVERY_GROUP,
    DEFAULT_DISCOVERY_PORT,
    DEFAULT_DISCOVERY_TTL,
    WorkerDiscoveryError,
    build_discovery_beacon,
)

DEFAULT_SEED_PATH = "/worker-discovery/v1/beacon"


class DiscoverySeedServer(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    token_provider: Callable[[], str | None]
    service_url: str
    discovery_group: str
    discovery_port: int
    ttl_seconds: float
    seed_path: str


class DiscoverySeedHandler(BaseHTTPRequestHandler):
    server: DiscoverySeedServer

    def do_GET(self) -> None:
        if self.path != self.server.seed_path:
            self._json(
                {
                    "error": {
                        "code": "not_found",
                        "message": "discovery seed path not found",
                    }
                },
                404,
            )
            return
        try:
            token = self.server.token_provider()
            if not token:
                raise WorkerDiscoveryError(
                    "invalid_discovery_secret",
                    "worker discovery seed has no active token",
                )
            beacon = build_discovery_beacon(
                token,
                self.server.service_url,
                group=self.server.discovery_group,
                port=self.server.discovery_port,
                ttl_seconds=self.server.ttl_seconds,
            )
            body = json.dumps(
                beacon,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        except (OSError, WorkerAuthError, WorkerDiscoveryError) as error:
            code = getattr(error, "code", "discovery_seed_unavailable")
            self._json(
                {
                    "error": {
                        "code": str(code),
                        "message": "authenticated discovery beacon is "
                        "unavailable",
                    }
                },
                503,
            )
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _json(self, payload: dict[str, Any], status: int) -> None:
        body = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: Any) -> None:
        super().log_message(format, *args)


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Serve a signed worker discovery beacon for workers that cannot "
            "receive the control plane's multicast domain"
        )
    )
    parser.add_argument(
        "--bind",
        default=os.environ.get("M5_WORKER_DISCOVERY_SEED_BIND", "0.0.0.0"),
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(
            os.environ.get("M5_WORKER_DISCOVERY_SEED_HTTP_PORT", "8788")
        ),
    )
    parser.add_argument(
        "--path",
        default=os.environ.get(
            "M5_WORKER_DISCOVERY_SEED_PATH",
            DEFAULT_SEED_PATH,
        ),
    )
    parser.add_argument(
        "--service-url",
        required=True,
        help="control-plane base URL encoded in the signed beacon",
    )
    token_group = parser.add_mutually_exclusive_group()
    token_group.add_argument(
        "--token",
        default=os.environ.get("M5_SERVICE_API_TOKEN"),
    )
    token_group.add_argument(
        "--token-file",
        type=Path,
        default=(
            Path(os.environ["M5_SERVICE_API_TOKEN_FILE"])
            if os.environ.get("M5_SERVICE_API_TOKEN_FILE")
            else None
        ),
    )
    parser.add_argument(
        "--discovery-group",
        default=os.environ.get(
            "M5_WORKER_DISCOVERY_GROUP",
            DEFAULT_DISCOVERY_GROUP,
        ),
    )
    parser.add_argument(
        "--discovery-port",
        type=int,
        default=int(
            os.environ.get(
                "M5_WORKER_DISCOVERY_PORT",
                str(DEFAULT_DISCOVERY_PORT),
            )
        ),
    )
    parser.add_argument(
        "--discovery-ttl",
        type=float,
        default=float(
            os.environ.get(
                "M5_WORKER_DISCOVERY_TTL",
                str(DEFAULT_DISCOVERY_TTL),
            )
        ),
    )
    args = parser.parse_args()
    if args.token is None and args.token_file is None:
        parser.error("--token or --token-file is required")
    if not 1 <= args.port <= 65535:
        parser.error("--port must be 1-65535")
    if not args.path.startswith("/") or "?" in args.path or "#" in args.path:
        parser.error("--path must be an absolute path without query or fragment")
    return args


def main() -> int:
    args = parse_arguments()
    if args.token is not None and args.token_file is not None:
        raise SystemExit("--token and --token-file are mutually exclusive")

    def load_token() -> str | None:
        if args.token_file is not None:
            return read_master_token_file(args.token_file)
        return args.token

    try:
        build_discovery_beacon(
            load_token() or "",
            args.service_url,
            group=args.discovery_group,
            port=args.discovery_port,
            ttl_seconds=args.discovery_ttl,
        )
    except (OSError, WorkerAuthError, WorkerDiscoveryError) as error:
        print(f"worker discovery seed configuration error: {error}", file=sys.stderr)
        return 2
    server = DiscoverySeedServer((args.bind, args.port), DiscoverySeedHandler)
    server.token_provider = load_token
    server.service_url = args.service_url
    server.discovery_group = args.discovery_group
    server.discovery_port = args.discovery_port
    server.ttl_seconds = args.discovery_ttl
    server.seed_path = args.path
    print(
        f"Worker discovery seed: http://{args.bind}:{args.port}{args.path}",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

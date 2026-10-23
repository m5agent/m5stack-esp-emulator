#!/usr/bin/env python3
"""Probe lab reachability and external egress from inside a network sandbox."""
from __future__ import annotations

import argparse
import json
import socket
import urllib.request


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True)
    parser.add_argument("--target", default="1.1.1.1")
    parser.add_argument("--port", type=int, default=80)
    parser.add_argument("--dns-name", default="example.com")
    parser.add_argument("--timeout", type=float, default=2)
    args = parser.parse_args()
    result = {
        "lab_http": "NOT_RUN",
        "external_tcp": "NOT_RUN",
        "dns": "NOT_RUN",
    }
    try:
        with urllib.request.urlopen(args.url, timeout=args.timeout) as response:
            result["lab_http"] = {
                "status": response.status,
                "body": response.read(256).decode("utf-8", errors="replace"),
            }
    except OSError as error:
        result["lab_http"] = {
            "status": "FAIL",
            "error": f"{type(error).__name__}: {error}",
        }
    try:
        with socket.create_connection(
            (args.target, args.port),
            timeout=args.timeout,
        ):
            result["external_tcp"] = "ALLOWED"
    except OSError as error:
        result["external_tcp"] = {
            "status": "DENIED",
            "error": f"{type(error).__name__}: {error}",
        }
    try:
        result["dns"] = {
            "status": "ALLOWED",
            "addresses": socket.getaddrinfo(
                args.dns_name,
                None,
                type=socket.SOCK_STREAM,
            ),
        }
    except OSError as error:
        result["dns"] = {
            "status": "DENIED",
            "error": f"{type(error).__name__}: {error}",
        }
    print(json.dumps(result, indent=2))
    return (
        0
        if result["lab_http"] != "NOT_RUN"
        and not (
            isinstance(result["lab_http"], dict)
            and result["lab_http"].get("status") == "FAIL"
        )
        else 1
    )


if __name__ == "__main__":
    raise SystemExit(main())

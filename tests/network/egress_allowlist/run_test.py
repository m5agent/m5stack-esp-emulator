#!/usr/bin/env python3
"""Prove exact destination IP/port filtering through the Linux egress gateway."""
from __future__ import annotations

import argparse
import http.server
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SANDBOX = ROOT / "platform/tools/network_sandbox.py"
DENIED_IP = "192.0.2.1"


def default_route_source() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.connect(("1.1.1.1", 80))
        return str(sock.getsockname()[0])


class TargetServer(http.server.ThreadingHTTPServer):
    def __init__(self, *, label: str, log_path: Path):
        self.label = label
        self.requests: list[str] = []
        self.log_path = log_path
        owner = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                owner.requests.append(self.path)
                owner.persist()
                body = b"allowed egress\n"
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format: str, *_args: object) -> None:
                return

        super().__init__(("0.0.0.0", 0), Handler)
        self.thread = threading.Thread(
            target=self.serve_forever,
            name=f"m5-egress-{label}",
            daemon=True,
        )

    def persist(self) -> None:
        self.log_path.write_text(
            json.dumps(self.requests, indent=2) + "\n"
        )

    def start(self) -> None:
        self.thread.start()

    def close(self) -> None:
        self.shutdown()
        self.server_close()
        self.thread.join(timeout=5)
        self.persist()


def connect_probe(
    host: str,
    port: int,
    *,
    timeout: float,
    http: bool,
) -> dict:
    started = time.monotonic()
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        try:
            sock.connect((host, port))
        except OSError as error:
            return {
                "connected": False,
                "error": type(error).__name__,
                "elapsed_seconds": round(time.monotonic() - started, 3),
            }
        status = None
        if http:
            request = f"GET /{host}:{port} HTTP/1.0\r\nHost: {host}\r\n\r\n"
            sock.sendall(request.encode("ascii"))
            response = sock.recv(4096)
            first = response.split(b"\r\n", 1)[0].decode(
                "ascii",
                errors="replace",
            )
            if first.startswith("HTTP/"):
                status = int(first.split()[1])
        return {
            "connected": True,
            "status": status,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }


def inner_probe(
    out: Path,
    host: str,
    allowed_port: int,
    denied_port: int,
    *,
    public: bool,
) -> int:
    result = {
        "allowed_ip_port": connect_probe(
            host,
            allowed_port,
            timeout=3,
            http=True,
        ),
        "denied_port": connect_probe(
            host,
            denied_port,
            timeout=1,
            http=False,
        ),
        "denied_ip": connect_probe(
            DENIED_IP,
            allowed_port,
            timeout=1,
            http=False,
        ),
    }
    if public:
        result["public_ip_port"] = connect_probe(
            "1.1.1.1",
            80,
            timeout=5,
            http=True,
        )
    (out / "inner-probe.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--inner-probe", action="store_true")
    parser.add_argument("--host")
    parser.add_argument("--allowed-port", type=int)
    parser.add_argument("--denied-port", type=int)
    parser.add_argument("--public", action="store_true")
    args = parser.parse_args()
    out = args.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if args.inner_probe:
        if args.host is None or args.allowed_port is None or args.denied_port is None:
            parser.error("inner probe requires host and both ports")
        return inner_probe(
            out,
            args.host,
            args.allowed_port,
            args.denied_port,
            public=args.public,
        )
    if sys.platform != "linux":
        parser.error("egress gateway integration requires Linux")

    host = default_route_source()
    allowed_log = out / "allowed-server.json"
    denied_log = out / "denied-server.json"
    allowed = TargetServer(label="allowed", log_path=allowed_log)
    denied = TargetServer(label="denied", log_path=denied_log)
    allowed_port = allowed.server_address[1]
    denied_port = denied.server_address[1]
    allowed.start()
    denied.start()
    config_path = out / "sandbox.json"
    endpoints = [
        {
            "protocol": "tcp",
            "address": host,
            "port": allowed_port,
        }
    ]
    if args.public:
        endpoints.append(
            {
                "protocol": "tcp",
                "address": "1.1.1.1",
                "port": 80,
            }
        )
    config = {
        "policy": {
            "isolation": "namespace",
            "egress": "allowlist",
            "dns": "deny",
            "allowed_hosts": [],
            "allowed_endpoints": endpoints,
        },
        "isolation_evidence": str(out / "isolation.json"),
    }
    config_path.write_text(json.dumps(config, indent=2) + "\n")
    command = [
        sys.executable,
        str(SANDBOX),
        "--config",
        str(config_path),
        "--",
        sys.executable,
        str(Path(__file__).resolve()),
        "--inner-probe",
        "--out-dir",
        str(out),
        "--host",
        host,
        "--allowed-port",
        str(allowed_port),
        "--denied-port",
        str(denied_port),
    ]
    if args.public:
        command.append("--public")
    started = time.monotonic()
    try:
        try:
            completed = subprocess.run(
                command,
                cwd=ROOT,
                text=True,
                capture_output=True,
                timeout=45,
                check=False,
                env=os.environ.copy(),
            )
        except subprocess.TimeoutExpired as error:
            stdout = error.stdout or ""
            stderr = error.stderr or ""
            if isinstance(stdout, bytes):
                stdout = stdout.decode("utf-8", errors="replace")
            if isinstance(stderr, bytes):
                stderr = stderr.decode("utf-8", errors="replace")
            completed = subprocess.CompletedProcess(
                command,
                124,
                stdout=stdout,
                stderr=stderr + "\negres gateway test timed out\n",
            )
    finally:
        allowed.close()
        denied.close()
    (out / "sandbox.stderr").write_text(completed.stderr)
    (out / "sandbox.stdout").write_text(completed.stdout)
    inner_path = out / "inner-probe.json"
    inner = (
        json.loads(inner_path.read_text())
        if inner_path.is_file()
        else {}
    )
    isolation_path = out / "isolation.json"
    isolation = (
        json.loads(isolation_path.read_text())
        if isolation_path.is_file()
        else {}
    )
    allowed_requests = (
        json.loads(allowed_log.read_text())
        if allowed_log.is_file()
        else []
    )
    denied_requests = (
        json.loads(denied_log.read_text())
        if denied_log.is_file()
        else []
    )
    gateway = isolation.get("gateway", {})
    namespace = str(gateway.get("namespace", ""))
    nat_table = str(gateway.get("nat_table", ""))
    namespaces = subprocess.run(
        ["ip", "netns", "list"],
        text=True,
        capture_output=True,
        check=False,
    )
    nft_tables = subprocess.run(
        ["nft", "list", "tables"],
        text=True,
        capture_output=True,
        check=False,
    )
    checks = {
        "sandbox_exit_zero": completed.returncode == 0,
        "allowed_ip_port_connected": (
            inner.get("allowed_ip_port", {}).get("connected") is True
            and inner["allowed_ip_port"].get("status") == 200
        ),
        "denied_port_filtered": (
            inner.get("denied_port", {}).get("connected") is False
        ),
        "denied_ip_filtered": (
            inner.get("denied_ip", {}).get("connected") is False
        ),
        "allowed_server_saw_one_request": len(allowed_requests) == 1,
        "denied_server_saw_no_request": not denied_requests,
        "nftables_default_drop": (
            isolation.get("egress_enforcement")
            == "nftables-input-output-default-drop"
        ),
        "gateway_mode": (
            isolation.get("gateway", {}).get("mode") == "veth-nat"
        ),
        "allowed_endpoint_recorded": (
            isolation.get("allowed_endpoints")
            == config["policy"]["allowed_endpoints"]
        ),
        "namespace_cleaned": (
            bool(namespace) and namespace not in namespaces.stdout
        ),
        "nat_table_cleaned": (
            bool(nat_table) and nat_table not in nft_tables.stdout
        ),
    }
    if args.public:
        checks["public_ip_port_connected"] = (
            inner.get("public_ip_port", {}).get("connected") is True
        )
    evidence = {
        "schema_version": 1,
        "kind": "m5stack-egress-ip-port-allowlist",
        "scope": "linux-virtual-network-policy-not-firmware-or-hardware",
        "date": "2026-10-24",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "duration_seconds": round(time.monotonic() - started, 3),
        "checks": checks,
        "target": {
            "host": host,
            "allowed_port": allowed_port,
            "denied_port": denied_port,
            "denied_ip": DENIED_IP,
            "public_ip_port": "1.1.1.1:80" if args.public else None,
        },
        "inner_probe": inner,
        "isolation": isolation,
        "requests": {
            "allowed": allowed_requests,
            "denied": denied_requests,
        },
        "sandbox_returncode": completed.returncode,
        "not_claimed": [
            "firmware guest behavior",
            "physical hardware or RF",
            "general public internet availability",
            "external IPv6 egress",
            "malware safety",
        ],
    }
    (out / "evidence.json").write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

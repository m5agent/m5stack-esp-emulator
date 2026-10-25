#!/usr/bin/env python3
"""Prove exact destination IP/port filtering through the Linux egress gateway."""
from __future__ import annotations

import argparse
import http.server
import ipaddress
import json
import os
import secrets
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
SANDBOX = ROOT / "platform/tools/network_sandbox.py"
WORKER_IPV4 = "10.203.0.1"
ALLOWED_CIDR = "10.203.0.4/30"
ALLOWED_IP = "10.203.0.5"
DENIED_IP = "10.203.0.9"
WORKER_IPV6 = "fd00:6d35:1::1"
UPSTREAM_IPV6 = "fd00:6d35:1::2"
IPV6_ALLOWED_IP = "2001:db8:6d35::1"
IPV6_DENIED_IP = "2001:db8:6d35::2"


class TargetServer(http.server.ThreadingHTTPServer):
    def __init__(
        self,
        *,
        label: str,
        address: str,
        port: int,
        log_path: Path,
    ):
        self.label = label
        self.requests: list[str] = []
        self.peers: list[str] = []
        self.log_path = log_path
        self.peer_log_path = log_path.with_suffix(".peers.json")
        family = ipaddress.ip_address(address).version
        self.address_family = (
            socket.AF_INET6 if family == 6 else socket.AF_INET
        )
        bind_address = (
            (address, port, 0, 0)
            if family == 6
            else (address, port)
        )
        owner = self

        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                owner.requests.append(self.path)
                owner.peers.append(str(self.client_address[0]))
                owner.persist()
                body = b"allowed egress\n"
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format: str, *_args: object) -> None:
                return

        super().__init__(bind_address, Handler)
        self.thread = threading.Thread(
            target=self.serve_forever,
            name=f"m5-egress-{label}",
            daemon=True,
        )

    def persist(self) -> None:
        self.log_path.write_text(
            json.dumps(self.requests, indent=2) + "\n"
        )
        self.peer_log_path.write_text(
            json.dumps(self.peers, indent=2) + "\n"
        )

    def start(self) -> None:
        self.thread.start()

    def close(self) -> None:
        self.shutdown()
        self.server_close()
        self.thread.join(timeout=5)
        self.persist()


class WorkerFabric:
    def __init__(self, out: Path):
        suffix = secrets.token_hex(3)
        self.worker_namespace = f"m5ew-{suffix}"
        self.upstream_namespace = f"m5eu-{suffix}"
        self.worker_interface = f"m5w-{suffix}"
        self.upstream_interface = f"m5u-{suffix}"
        self.out = out
        self.processes: list[subprocess.Popen[str]] = []
        self.started = False

    def run(
        self,
        command: list[str],
        *,
        check: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        completed = subprocess.run(
            command,
            text=True,
            capture_output=True,
            check=False,
        )
        if check and completed.returncode != 0:
            detail = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(
                f"fabric command failed ({' '.join(command)}): {detail}"
            )
        return completed

    def start(self) -> None:
        self.run(["ip", "netns", "add", self.worker_namespace])
        self.started = True
        self.run(["ip", "netns", "add", self.upstream_namespace])
        self.run(
            [
                "ip",
                "netns",
                "exec",
                self.worker_namespace,
                "ip",
                "link",
                "add",
                self.worker_interface,
                "type",
                "veth",
                "peer",
                "name",
                self.upstream_interface,
            ]
        )
        self.run(
            [
                "ip",
                "netns",
                "exec",
                self.worker_namespace,
                "ip",
                "link",
                "set",
                self.upstream_interface,
                "netns",
                self.upstream_namespace,
            ]
        )
        for namespace in (
            self.worker_namespace,
            self.upstream_namespace,
        ):
            self.run(
                [
                    "ip",
                    "netns",
                    "exec",
                    namespace,
                    "ip",
                    "link",
                    "set",
                    "lo",
                    "up",
                ]
            )
        self.run(
            [
                "ip",
                "netns",
                "exec",
                self.worker_namespace,
                "ip",
                "link",
                "set",
                self.worker_interface,
                "up",
            ]
        )
        self.run(
            [
                "ip",
                "netns",
                "exec",
                self.upstream_namespace,
                "ip",
                "link",
                "set",
                self.upstream_interface,
                "up",
            ]
        )
        self.run(
            [
                "ip",
                "netns",
                "exec",
                self.worker_namespace,
                "ip",
                "addr",
                "add",
                f"{WORKER_IPV4}/28",
                "dev",
                self.worker_interface,
            ]
        )
        self.run(
            [
                "ip",
                "-6",
                "netns",
                "exec",
                self.worker_namespace,
                "ip",
                "-6",
                "addr",
                "add",
                f"{WORKER_IPV6}/64",
                "dev",
                self.worker_interface,
                "nodad",
            ]
        )
        self.run(
            [
                "ip",
                "netns",
                "exec",
                self.upstream_namespace,
                "ip",
                "addr",
                "add",
                f"{ALLOWED_IP}/28",
                "dev",
                self.upstream_interface,
            ]
        )
        self.run(
            [
                "ip",
                "netns",
                "exec",
                self.upstream_namespace,
                "ip",
                "addr",
                "add",
                f"{DENIED_IP}/28",
                "dev",
                self.upstream_interface,
            ]
        )
        self.run(
            [
                "ip",
                "-6",
                "netns",
                "exec",
                self.upstream_namespace,
                "ip",
                "-6",
                "addr",
                "add",
                f"{UPSTREAM_IPV6}/64",
                "dev",
                self.upstream_interface,
                "nodad",
            ]
        )
        for address in (IPV6_ALLOWED_IP, IPV6_DENIED_IP):
            self.run(
                [
                    "ip",
                    "-6",
                    "netns",
                    "exec",
                    self.upstream_namespace,
                    "ip",
                    "-6",
                    "addr",
                    "add",
                    f"{address}/128",
                    "dev",
                    "lo",
                    "nodad",
                ]
            )
        self.run(
            [
                "ip",
                "netns",
                "exec",
                self.worker_namespace,
                "ip",
                "route",
                "add",
                "default",
                "via",
                ALLOWED_IP,
            ]
        )
        self.run(
            [
                "ip",
                "-6",
                "netns",
                "exec",
                self.worker_namespace,
                "ip",
                "-6",
                "route",
                "add",
                "default",
                "via",
                UPSTREAM_IPV6,
            ]
        )
        self.run(
            [
                "ip",
                "netns",
                "exec",
                self.worker_namespace,
                "sysctl",
                "--write",
                "net.ipv4.ip_forward=1",
            ]
        )
        self.run(
            [
                "ip",
                "netns",
                "exec",
                self.worker_namespace,
                "sysctl",
                "--write",
                "net.ipv6.conf.all.forwarding=1",
            ]
        )

    def start_target(
        self,
        *,
        label: str,
        address: str,
        port: int = 0,
    ) -> tuple[subprocess.Popen[str], int, Path, Path]:
        log_path = self.out / f"{label}-server.json"
        ready_path = self.out / f"{label}-server.ready.json"
        ready_path.unlink(missing_ok=True)
        log_path.unlink(missing_ok=True)
        log_path.with_suffix(".peers.json").unlink(missing_ok=True)
        process = subprocess.Popen(
            [
                "ip",
                "netns",
                "exec",
                self.upstream_namespace,
                sys.executable,
                str(Path(__file__).resolve()),
                "--serve-target",
                "--target-address",
                address,
                "--target-port",
                str(port),
                "--target-log",
                str(log_path),
                "--target-ready",
                str(ready_path),
            ],
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        self.processes.append(process)
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if ready_path.is_file():
                ready = json.loads(ready_path.read_text())
                return (
                    process,
                    int(ready["port"]),
                    log_path,
                    log_path.with_suffix(".peers.json"),
                )
            if process.poll() is not None:
                stdout, stderr = process.communicate()
                raise RuntimeError(
                    f"target server {label} exited early: "
                    f"{stderr.strip() or stdout.strip()}"
                )
            time.sleep(0.05)
        raise RuntimeError(f"target server {label} did not become ready")

    def close(self) -> None:
        for process in self.processes:
            if process.poll() is None:
                process.terminate()
        for process in self.processes:
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        if self.started:
            for namespace in (
                self.worker_namespace,
                self.upstream_namespace,
            ):
                self.run(
                    ["ip", "netns", "delete", namespace],
                    check=False,
                )
        self.started = False

    def __enter__(self) -> WorkerFabric:
        try:
            self.start()
        except Exception:
            self.close()
            raise
        return self

    def __exit__(self, *_args: object) -> None:
        self.close()


def connect_probe(
    host: str,
    port: int,
    *,
    timeout: float,
    http: bool,
) -> dict:
    started = time.monotonic()
    family = (
        socket.AF_INET6
        if ipaddress.ip_address(host).version == 6
        else socket.AF_INET
    )
    target = (host, port, 0, 0) if family == socket.AF_INET6 else (host, port)
    with socket.socket(family, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        try:
            sock.connect(target)
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
    ipv6_host: str,
    ipv6_allowed_port: int,
    ipv6_denied_port: int,
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
        "allowed_ipv6_port": connect_probe(
            ipv6_host,
            ipv6_allowed_port,
            timeout=3,
            http=True,
        ),
        "denied_ipv6_port": connect_probe(
            ipv6_host,
            ipv6_denied_port,
            timeout=1,
            http=False,
        ),
        "denied_ipv6": connect_probe(
            IPV6_DENIED_IP,
            ipv6_allowed_port,
            timeout=1,
            http=False,
        ),
    }
    (out / "inner-probe.json").write_text(
        json.dumps(result, indent=2) + "\n"
    )
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--serve-target", action="store_true")
    parser.add_argument("--target-address")
    parser.add_argument("--target-port", type=int, default=0)
    parser.add_argument("--target-log", type=Path)
    parser.add_argument("--target-ready", type=Path)
    parser.add_argument("--inner-probe", action="store_true")
    parser.add_argument("--host")
    parser.add_argument("--allowed-port", type=int)
    parser.add_argument("--denied-port", type=int)
    parser.add_argument("--ipv6-host")
    parser.add_argument("--ipv6-allowed-port", type=int)
    parser.add_argument("--ipv6-denied-port", type=int)
    args = parser.parse_args()
    if args.serve_target:
        if (
            args.target_address is None
            or args.target_log is None
            or args.target_ready is None
        ):
            parser.error(
                "--serve-target requires address, log and ready paths"
            )
        args.target_log.parent.mkdir(parents=True, exist_ok=True)
        server = TargetServer(
            label="target",
            address=args.target_address,
            port=args.target_port,
            log_path=args.target_log,
        )
        server.persist()
        args.target_ready.write_text(
            json.dumps({"port": server.server_address[1]}) + "\n"
        )
        try:
            server.serve_forever()
        finally:
            server.server_close()
            server.persist()
        return 0
    if args.out_dir is None:
        parser.error("--out-dir is required")
    out = args.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if args.inner_probe:
        if (
            args.host is None
            or args.allowed_port is None
            or args.denied_port is None
            or args.ipv6_host is None
            or args.ipv6_allowed_port is None
            or args.ipv6_denied_port is None
        ):
            parser.error(
                "inner probe requires IPv4/IPv6 hosts and allowed/denied ports"
            )
        return inner_probe(
            out,
            args.host,
            args.allowed_port,
            args.denied_port,
            args.ipv6_host,
            args.ipv6_allowed_port,
            args.ipv6_denied_port,
        )
    if sys.platform != "linux":
        parser.error("egress gateway integration requires Linux")

    started = time.monotonic()
    fabric = WorkerFabric(out)
    with fabric:
        (
            _,
            allowed_port,
            allowed_log,
            allowed_peer_log,
        ) = fabric.start_target(label="allowed", address=ALLOWED_IP)
        (
            _,
            denied_port,
            denied_log,
            denied_peer_log,
        ) = fabric.start_target(label="denied", address=ALLOWED_IP)
        (
            _,
            _,
            denied_ip_log,
            denied_ip_peer_log,
        ) = fabric.start_target(
            label="denied-ip",
            address=DENIED_IP,
            port=allowed_port,
        )
        (
            _,
            ipv6_allowed_port,
            ipv6_allowed_log,
            ipv6_allowed_peer_log,
        ) = fabric.start_target(
            label="allowed-ipv6",
            address=IPV6_ALLOWED_IP,
        )
        (
            _,
            ipv6_denied_port,
            ipv6_denied_log,
            ipv6_denied_peer_log,
        ) = fabric.start_target(
            label="denied-ipv6",
            address=IPV6_ALLOWED_IP,
        )
        (
            _,
            _,
            ipv6_denied_ip_log,
            ipv6_denied_ip_peer_log,
        ) = fabric.start_target(
            label="denied-ipv6-ip",
            address=IPV6_DENIED_IP,
            port=ipv6_allowed_port,
        )
        config_path = out / "sandbox.json"
        endpoints = [
            {
                "protocol": "tcp",
                "address": ALLOWED_CIDR,
                "port": allowed_port,
            },
            {
                "protocol": "tcp",
                "address": IPV6_ALLOWED_IP,
                "port": ipv6_allowed_port,
            },
        ]
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
            "ip",
            "netns",
            "exec",
            fabric.worker_namespace,
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
            ALLOWED_IP,
            "--allowed-port",
            str(allowed_port),
            "--denied-port",
            str(denied_port),
            "--ipv6-host",
            IPV6_ALLOWED_IP,
            "--ipv6-allowed-port",
            str(ipv6_allowed_port),
            "--ipv6-denied-port",
            str(ipv6_denied_port),
        ]
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
        inner_namespaces = fabric.run(
            [
                "ip",
                "netns",
                "exec",
                fabric.worker_namespace,
                "ip",
                "netns",
                "list",
            ]
        )
        nft_tables = fabric.run(
            [
                "ip",
                "netns",
                "exec",
                fabric.worker_namespace,
                "nft",
                "list",
                "tables",
            ]
        )
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
    denied_ip_requests = (
        json.loads(denied_ip_log.read_text())
        if denied_ip_log.is_file()
        else []
    )
    ipv6_allowed_requests = (
        json.loads(ipv6_allowed_log.read_text())
        if ipv6_allowed_log.is_file()
        else []
    )
    ipv6_denied_requests = (
        json.loads(ipv6_denied_log.read_text())
        if ipv6_denied_log.is_file()
        else []
    )
    ipv6_denied_ip_requests = (
        json.loads(ipv6_denied_ip_log.read_text())
        if ipv6_denied_ip_log.is_file()
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
    allowed_peers = (
        json.loads(allowed_peer_log.read_text())
        if allowed_peer_log.is_file()
        else []
    )
    denied_peers = (
        json.loads(denied_peer_log.read_text())
        if denied_peer_log.is_file()
        else []
    )
    denied_ip_peers = (
        json.loads(denied_ip_peer_log.read_text())
        if denied_ip_peer_log.is_file()
        else []
    )
    ipv6_allowed_peers = (
        json.loads(ipv6_allowed_peer_log.read_text())
        if ipv6_allowed_peer_log.is_file()
        else []
    )
    ipv6_denied_peers = (
        json.loads(ipv6_denied_peer_log.read_text())
        if ipv6_denied_peer_log.is_file()
        else []
    )
    ipv6_denied_ip_peers = (
        json.loads(ipv6_denied_ip_peer_log.read_text())
        if ipv6_denied_ip_peer_log.is_file()
        else []
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
        "allowed_ipv6_port_connected": (
            inner.get("allowed_ipv6_port", {}).get("connected") is True
            and inner["allowed_ipv6_port"].get("status") == 200
        ),
        "denied_ipv6_port_filtered": (
            inner.get("denied_ipv6_port", {}).get("connected") is False
        ),
        "denied_ipv6_filtered": (
            inner.get("denied_ipv6", {}).get("connected") is False
        ),
        "allowed_server_saw_one_request": len(allowed_requests) == 1,
        "denied_server_saw_no_request": (
            not denied_requests and not denied_ip_requests
        ),
        "allowed_ipv6_server_saw_one_request": (
            len(ipv6_allowed_requests) == 1
        ),
        "denied_ipv6_server_saw_no_request": not ipv6_denied_requests,
        "denied_ipv6_ip_server_saw_no_request": (
            not ipv6_denied_ip_requests
        ),
        "nftables_default_drop": (
            isolation.get("egress_enforcement")
            == "nftables-input-output-default-drop"
        ),
        "gateway_mode": (
            isolation.get("gateway", {}).get("mode") == "veth-nat"
        ),
        "ipv4_nat_used": WORKER_IPV4 in allowed_peers,
        "ipv6_nat_used": WORKER_IPV6 in ipv6_allowed_peers,
        "ipv6_default_interface_present": (
            isolation.get("gateway", {}).get("default_ipv6_interface")
            == fabric.worker_interface
        ),
        "allowed_endpoint_recorded": (
            isolation.get("allowed_endpoints")
            == config["policy"]["allowed_endpoints"]
        ),
        "namespace_cleaned": (
            bool(namespace) and namespace not in inner_namespaces.stdout
        ),
        "nat_table_cleaned": (
            bool(nat_table) and nat_table not in nft_tables.stdout
        ),
        "worker_namespace_cleaned": (
            fabric.worker_namespace not in namespaces.stdout
        ),
        "upstream_namespace_cleaned": (
            fabric.upstream_namespace not in namespaces.stdout
        ),
    }
    evidence = {
        "schema_version": 1,
        "kind": "m5stack-egress-ip-cidr-port-allowlist",
        "scope": "linux-virtual-network-policy-not-firmware-or-hardware",
        "date": "2026-10-25",
        "status": "PASS" if all(checks.values()) else "FAIL",
        "duration_seconds": round(time.monotonic() - started, 3),
        "checks": checks,
        "target": {
            "host": "<fixture-upstream-ipv4>",
            "allowed_cidr": ALLOWED_CIDR,
            "allowed_port": allowed_port,
            "denied_port": denied_port,
            "denied_ip": DENIED_IP,
            "ipv6_host": IPV6_ALLOWED_IP,
            "ipv6_allowed_port": ipv6_allowed_port,
            "ipv6_denied_port": ipv6_denied_port,
            "ipv6_denied_ip": IPV6_DENIED_IP,
        },
        "inner_probe": inner,
        "isolation": isolation,
        "requests": {
            "allowed": allowed_requests,
            "denied": denied_requests,
            "denied_ip": denied_ip_requests,
            "allowed_ipv6": ipv6_allowed_requests,
            "denied_ipv6": ipv6_denied_requests,
            "denied_ipv6_ip": ipv6_denied_ip_requests,
        },
        "peers": {
            "allowed": allowed_peers,
            "denied": denied_peers,
            "denied_ip": denied_ip_peers,
            "allowed_ipv6": ipv6_allowed_peers,
            "denied_ipv6": ipv6_denied_peers,
            "denied_ipv6_ip": ipv6_denied_ip_peers,
        },
        "sandbox_returncode": completed.returncode,
        "not_claimed": [
            "firmware guest behavior",
            "physical hardware or RF",
            "general public internet availability",
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

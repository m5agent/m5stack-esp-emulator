#!/usr/bin/env python3
"""Prove authenticated worker discovery through a routed/NAT seed."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import secrets
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
SERVICE = ROOT / "platform/tools/serve.py"
WORKER = ROOT / "platform/tools/worker_agent.py"
SEED = ROOT / "platform/tools/worker_discovery_seed.py"
GROUP = "239.255.77.77"
SEED_PATH = "/worker-discovery/v1/beacon"
CONTROL_NS = "m5ds-control"
WORKER_NS = "m5ds-worker"
ROUTER_NS = "m5ds-router"
CONTROL_ADDRESS = "10.213.1.10"
CONTROL_ROUTER_ADDRESS = "10.213.1.1"
WORKER_ADDRESS = "10.213.2.10"
WORKER_ROUTER_ADDRESS = "10.213.2.1"
CONTROL_SUBNET = "10.213.1.0/24"
WORKER_SUBNET = "10.213.2.0/24"
NAT_TABLE = "m5_worker_discovery_seed"
TOOL_PATHS = {
    "runner": Path(__file__).resolve(),
    "worker_agent": ROOT / "platform/tools/worker_agent.py",
    "worker_discovery": ROOT / "platform/tools/worker_discovery.py",
    "worker_discovery_seed": ROOT / "platform/tools/worker_discovery_seed.py",
    "serve": SERVICE,
}


class FixtureError(RuntimeError):
    pass


def command(
    arguments: list[str],
    *,
    input_text: str | None = None,
    timeout: float = 30,
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            arguments,
            cwd=ROOT,
            input=input_text,
            capture_output=True,
            text=True,
            check=False,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as error:
        raise FixtureError(
            f"command timed out: {' '.join(arguments[:5])}"
        ) from error


def checked(
    arguments: list[str],
    *,
    input_text: str | None = None,
    timeout: float = 30,
) -> subprocess.CompletedProcess[str]:
    result = command(
        arguments,
        input_text=input_text,
        timeout=timeout,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout).strip()[-2000:]
        raise FixtureError(
            f"command failed ({result.returncode}): "
            f"{' '.join(arguments[:5])}: {detail}"
        )
    return result


def in_namespace(
    namespace: str,
    arguments: list[str],
    *,
    input_text: str | None = None,
    timeout: float = 30,
) -> subprocess.CompletedProcess[str]:
    return checked(
        ["ip", "netns", "exec", namespace, *arguments],
        input_text=input_text,
        timeout=timeout,
    )


def free_port(kind: int) -> int:
    with socket.socket(socket.AF_INET, kind) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def tool_hashes() -> dict[str, str]:
    return {
        name: sha256_file(path)
        for name, path in TOOL_PATHS.items()
    }


def wait_namespace_http(
    namespace: str,
    url: str,
    process: subprocess.Popen[str],
    *,
    token_file: Path | None = None,
    timeout: float = 20,
) -> None:
    script = """
import json
import pathlib
import sys
import urllib.request
url = sys.argv[1]
token_file = pathlib.Path(sys.argv[2]) if sys.argv[2] else None
headers = {}
if token_file is not None:
    headers["Authorization"] = "Bearer " + token_file.read_text().strip()
request = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(request, timeout=1) as response:
    if response.status != 200:
        raise SystemExit(2)
    json.loads(response.read())
"""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise FixtureError("fixture process exited before HTTP readiness")
        try:
            result = command(
                [
                    "ip",
                    "netns",
                    "exec",
                    namespace,
                    sys.executable,
                    "-c",
                    script,
                    url,
                    str(token_file) if token_file is not None else "",
                ],
                timeout=4,
            )
        except FixtureError:
            time.sleep(0.1)
            continue
        if result.returncode == 0:
            return
        time.sleep(0.1)
    raise FixtureError(f"HTTP endpoint did not become ready: {url}")


def api_json(namespace: str, url: str, token_file: Path) -> Any:
    script = """
import json
import pathlib
import sys
import urllib.request
token = pathlib.Path(sys.argv[2]).read_text().strip()
request = urllib.request.Request(
    sys.argv[1],
    headers={"Authorization": "Bearer " + token},
)
with urllib.request.urlopen(request, timeout=10) as response:
    print(json.dumps(json.loads(response.read())))
"""
    result = in_namespace(
        namespace,
        [
            sys.executable,
            "-c",
            script,
            url,
            str(token_file),
        ],
        timeout=15,
    )
    return json.loads(result.stdout)


def wait_api_ready(namespace: str, url: str, token_file: Path) -> None:
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        try:
            api_json(namespace, url, token_file)
            return
        except FixtureError:
            time.sleep(0.1)
    raise FixtureError("authenticated API did not become ready")


def atomic_token_write(path: Path, token: str) -> None:
    temporary = path.with_name(path.name + ".next")
    temporary.write_text(token + "\n")
    temporary.chmod(0o600)
    os.replace(temporary, path)


class NetworkFixture:
    def __init__(self, out_dir: Path):
        self.out_dir = out_dir
        self.setup: dict[str, Any] = {}

    def run(self, namespace: str, arguments: list[str]) -> str:
        return in_namespace(namespace, arguments).stdout.strip()

    def up(self) -> None:
        self.cleanup()
        for namespace in (CONTROL_NS, WORKER_NS, ROUTER_NS):
            checked(["ip", "netns", "add", namespace])
        checked(
            [
                "ip",
                "link",
                "add",
                "cd-router",
                "type",
                "veth",
                "peer",
                "name",
                "cd-control",
            ]
        )
        checked(["ip", "link", "set", "cd-control", "netns", CONTROL_NS])
        checked(["ip", "link", "set", "cd-router", "netns", ROUTER_NS])
        checked(
            [
                "ip",
                "link",
                "add",
                "wd-router",
                "type",
                "veth",
                "peer",
                "name",
                "wd-worker",
            ]
        )
        checked(["ip", "link", "set", "wd-worker", "netns", WORKER_NS])
        checked(["ip", "link", "set", "wd-router", "netns", ROUTER_NS])

        for interface, address in (
            ("cd-control", f"{CONTROL_ADDRESS}/24"),
            ("wd-worker", f"{WORKER_ADDRESS}/24"),
        ):
            namespace = (
                CONTROL_NS if interface == "cd-control" else WORKER_NS
            )
            self.run(
                namespace,
                ["ip", "addr", "add", address, "dev", interface],
            )
            self.run(namespace, ["ip", "link", "set", "lo", "up"])
            self.run(namespace, ["ip", "link", "set", interface, "up"])
        for interface, address in (
            ("cd-router", f"{CONTROL_ROUTER_ADDRESS}/24"),
            ("wd-router", f"{WORKER_ROUTER_ADDRESS}/24"),
        ):
            self.run(
                ROUTER_NS,
                ["ip", "addr", "add", address, "dev", interface],
            )
            self.run(ROUTER_NS, ["ip", "link", "set", interface, "up"])
        self.run(ROUTER_NS, ["ip", "link", "set", "lo", "up"])
        self.run(
            ROUTER_NS,
            [
                "sysctl",
                "-q",
                "-w",
                "net.ipv4.ip_forward=1",
            ],
        )
        self.run(
            CONTROL_NS,
            [
                "ip",
                "route",
                "add",
                "default",
                "via",
                CONTROL_ROUTER_ADDRESS,
            ],
        )
        self.run(
            WORKER_NS,
            [
                "ip",
                "route",
                "add",
                "default",
                "via",
                WORKER_ROUTER_ADDRESS,
            ],
        )
        nft_script = (
            f"table inet {NAT_TABLE} {{\n"
            "  chain postrouting {\n"
            "    type nat hook postrouting priority srcnat; policy accept;\n"
            f'    oifname "cd-router" ip saddr {WORKER_SUBNET} masquerade\n'
            "  }\n"
            "}\n"
        )
        in_namespace(ROUTER_NS, ["nft", "-f", "-"], input_text=nft_script)
        self.setup = {
            "control_route": self.run(
                CONTROL_NS,
                ["ip", "route", "show", "default"],
            ),
            "worker_route": self.run(
                WORKER_NS,
                ["ip", "route", "show", "default"],
            ),
            "router_ipv4_forward": self.run(
                ROUTER_NS,
                ["sysctl", "-n", "net.ipv4.ip_forward"],
            ),
            "nftables": self.run(ROUTER_NS, ["nft", "list", "ruleset"]),
        }

    def cleanup(self) -> None:
        for namespace in (CONTROL_NS, WORKER_NS, ROUTER_NS):
            command(["ip", "netns", "delete", namespace], timeout=15)

    def namespaces(self) -> str:
        return checked(["ip", "netns", "list"]).stdout

    def nftables(self) -> str:
        result = command(["ip", "netns", "exec", ROUTER_NS, "nft", "list"])
        return result.stdout


def process_log_lines(process: subprocess.Popen[str]) -> tuple[list[str], threading.Thread]:
    lines: list[str] = []

    def consume() -> None:
        if process.stdout is None:
            return
        for line in process.stdout:
            lines.append(line)

    thread = threading.Thread(target=consume, daemon=True)
    thread.start()
    return lines, thread


def stop_process(process: subprocess.Popen[str] | None) -> None:
    if process is None or process.poll() is not None:
        return
    process.send_signal(signal.SIGTERM)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


def run_worker(
    *,
    mode: str,
    seed_url: str | None,
    token_file: Path,
    work_dir: Path,
    worker_id: str,
    discovery_port: int,
    timeout: float,
) -> subprocess.CompletedProcess[str]:
    command_line = [
        "ip",
        "netns",
        "exec",
        WORKER_NS,
        sys.executable,
        str(WORKER),
    ]
    if mode == "seed":
        command_line.extend(
            [
                "--discover-control-seed-url",
                str(seed_url),
            ]
        )
    elif mode == "multicast":
        command_line.append("--discover-control")
    else:
        raise ValueError(mode)
    command_line.extend(
        [
            "--discover-control-group",
            GROUP,
            "--discover-control-port",
            str(discovery_port),
            "--discover-control-timeout",
            str(timeout),
            "--token-file",
            str(token_file),
            "--worker-id",
            worker_id,
            "--work-dir",
            str(work_dir),
            "--poll-seconds",
            "0.1",
            "--heartbeat-interval",
            "1",
            "--once",
        ]
    )
    return command(
        command_line,
        timeout=timeout + 20,
    )

def main() -> int:
    if sys.platform != "linux":
        raise SystemExit("worker discovery seed integration requires Linux")
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)

    control_port = free_port(socket.SOCK_STREAM)
    seed_http_port = free_port(socket.SOCK_STREAM)
    multicast_port = free_port(socket.SOCK_DGRAM)
    control_url = f"http://{CONTROL_ADDRESS}:{control_port}"
    seed_url = (
        f"http://{CONTROL_ADDRESS}:{seed_http_port}{SEED_PATH}"
    )
    bypass_hosts = ",".join(
        (
            CONTROL_ADDRESS,
            CONTROL_ROUTER_ADDRESS,
            WORKER_ADDRESS,
            WORKER_ROUTER_ADDRESS,
        )
    )
    for variable in ("NO_PROXY", "no_proxy"):
        current = os.environ.get(variable, "")
        os.environ[variable] = (
            f"{current},{bypass_hosts}" if current else bypass_hosts
        )
    token = secrets.token_hex(32)
    rotated_token = secrets.token_hex(32)
    wrong_token = secrets.token_hex(32)
    token_file = args.out_dir / "discovery.token"
    old_token_file = args.out_dir / "old.token"
    wrong_token_file = args.out_dir / "wrong.token"
    atomic_token_write(token_file, token)
    atomic_token_write(old_token_file, token)
    atomic_token_write(wrong_token_file, wrong_token)

    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        filter(
            None,
            [str(ROOT / "platform/tools"), env.get("PYTHONPATH", "")],
        )
    )
    fixture = NetworkFixture(args.out_dir)
    hashes_before = tool_hashes()
    service: subprocess.Popen[str] | None = None
    seed: subprocess.Popen[str] | None = None
    service_lines: list[str] = []
    seed_lines: list[str] = []
    service_thread: threading.Thread | None = None
    seed_thread: threading.Thread | None = None
    try:
        fixture.up()
        service = subprocess.Popen(
            [
                "ip",
                "netns",
                "exec",
                CONTROL_NS,
                sys.executable,
                "-u",
                str(SERVICE),
                str(control_port),
                "--bind",
                CONTROL_ADDRESS,
                "--state-dir",
                str(args.out_dir / "service-state"),
                "--api-token-file",
                str(token_file),
                "--worker-discovery-group",
                GROUP,
                "--worker-discovery-port",
                str(multicast_port),
                "--worker-discovery-advertise-url",
                control_url,
                "--worker-discovery-interval",
                "0.2",
                "--worker-discovery-ttl",
                "2",
            ],
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
        )
        service_lines, service_thread = process_log_lines(service)
        try:
            wait_namespace_http(
                CONTROL_NS,
                control_url + "/api/health",
                service,
                timeout=45,
            )
        except FixtureError as error:
            detail = "".join(service_lines).strip()[-4000:]
            raise FixtureError(f"{error}; service output: {detail}") from error
        seed = subprocess.Popen(
            [
                "ip",
                "netns",
                "exec",
                CONTROL_NS,
                sys.executable,
                "-u",
                str(SEED),
                "--bind",
                CONTROL_ADDRESS,
                "--port",
                str(seed_http_port),
                "--path",
                SEED_PATH,
                "--service-url",
                control_url,
                "--token-file",
                str(token_file),
                "--discovery-group",
                GROUP,
                "--discovery-port",
                str(multicast_port),
                "--discovery-ttl",
                "30",
            ],
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            bufsize=1,
        )
        seed_lines, seed_thread = process_log_lines(seed)
        wait_namespace_http(WORKER_NS, seed_url, seed)
        wait_api_ready(
            CONTROL_NS,
            control_url + "/api/v1/workers",
            token_file,
        )

        multicast = run_worker(
            mode="multicast",
            seed_url=None,
            token_file=token_file,
            work_dir=args.out_dir / "worker-multicast",
            worker_id="cross-subnet-multicast-worker",
            discovery_port=multicast_port,
            timeout=2,
        )
        good = run_worker(
            mode="seed",
            seed_url=seed_url,
            token_file=token_file,
            work_dir=args.out_dir / "worker-seed",
            worker_id="seed-bootstrap-worker",
            discovery_port=multicast_port,
            timeout=8,
        )
        wrong = run_worker(
            mode="seed",
            seed_url=seed_url,
            token_file=wrong_token_file,
            work_dir=args.out_dir / "worker-wrong-token",
            worker_id="wrong-token-worker",
            discovery_port=multicast_port,
            timeout=4,
        )

        atomic_token_write(token_file, rotated_token)
        if service.poll() is not None:
            raise FixtureError("control service exited before rotation")
        service.send_signal(signal.SIGHUP)
        wait_api_ready(
            CONTROL_NS,
            control_url + "/api/v1/workers",
            token_file,
        )
        rotated = run_worker(
            mode="seed",
            seed_url=seed_url,
            token_file=token_file,
            work_dir=args.out_dir / "worker-rotated",
            worker_id="rotated-seed-worker",
            discovery_port=multicast_port,
            timeout=8,
        )
        old = run_worker(
            mode="seed",
            seed_url=seed_url,
            token_file=old_token_file,
            work_dir=args.out_dir / "worker-old-token",
            worker_id="old-token-worker",
            discovery_port=multicast_port,
            timeout=4,
        )

        workers = api_json(
            CONTROL_NS,
            control_url + "/api/v1/workers",
            token_file,
        )["workers"]
        sessions = api_json(
            CONTROL_NS,
            control_url + "/api/v1/sessions",
            token_file,
        )["sessions"]
        by_id = {
            str(worker.get("worker_id")): worker
            for worker in workers
        }
        good_output = good.stdout + good.stderr
        multicast_output = multicast.stdout + multicast.stderr
        wrong_output = wrong.stdout + wrong.stderr
        rotated_output = rotated.stdout + rotated.stderr
        old_output = old.stdout + old.stderr
        stop_process(seed)
        stop_process(service)
        if seed_thread is not None:
            seed_thread.join(timeout=2)
        if service_thread is not None:
            service_thread.join(timeout=2)
        service_log = "".join(service_lines)
        seed_log = "".join(seed_lines)
        hashes_after = tool_hashes()
        input_assets_unchanged = hashes_after == hashes_before
        observed_sources = re.findall(
            r"^([0-9.]+) - - .*?\"GET ",
            seed_log,
            flags=re.MULTILINE,
        )
        fixture.cleanup()
        namespaces_after = fixture.namespaces()
        nft_after = fixture.nftables()
        checks = {
            "control_route_via_router": (
                CONTROL_ROUTER_ADDRESS in fixture.setup["control_route"]
            ),
            "worker_route_via_router": (
                WORKER_ROUTER_ADDRESS in fixture.setup["worker_route"]
            ),
            "router_ipv4_forwarding": (
                fixture.setup["router_ipv4_forward"] == "1"
            ),
            "nat_masquerade_installed": (
                f"ip saddr {WORKER_SUBNET} masquerade"
                in fixture.setup["nftables"]
            ),
            "multicast_did_not_cross_subnet": multicast.returncode != 0,
            "multicast_worker_not_registered": (
                "cross-subnet-multicast-worker" not in by_id
            ),
            "seed_worker_exit_zero": good.returncode == 0,
            "seed_discovery_used": (
                "worker control service discovered via unicast seed"
                in good_output
            ),
            "seed_worker_registered": (
                by_id.get("seed-bootstrap-worker", {}).get("state")
                == "stopped"
            ),
            "wrong_token_rejected": wrong.returncode != 0,
            "wrong_token_not_registered": (
                "wrong-token-worker" not in by_id
            ),
            "token_rotation_applied": rotated.returncode == 0,
            "rotated_worker_registered": (
                by_id.get("rotated-seed-worker", {}).get("state")
                == "stopped"
            ),
            "old_token_rejected": old.returncode != 0,
            "old_token_not_registered": "old-token-worker" not in by_id,
            "control_observed_nat_router": (
                bool(observed_sources)
                and all(
                    source == CONTROL_ROUTER_ADDRESS
                    for source in observed_sources
                )
            ),
            "initial_token_absent": all(
                token not in text
                for text in (
                    service_log,
                    seed_log,
                    good_output,
                    multicast_output,
                    wrong_output,
                    rotated_output,
                    old_output,
                )
            ),
            "rotated_token_absent": all(
                rotated_token not in text
                for text in (
                    service_log,
                    seed_log,
                    good_output,
                    multicast_output,
                    wrong_output,
                    rotated_output,
                    old_output,
                )
            ),
            "wrong_token_absent": wrong_token not in wrong_output,
            "no_device_session_created": not sessions,
            "input_assets_unchanged": input_assets_unchanged,
            "namespaces_cleaned": all(
                namespace not in namespaces_after
                for namespace in (CONTROL_NS, WORKER_NS, ROUTER_NS)
            ),
            "nat_table_cleaned": NAT_TABLE not in nft_after,
        }
        evidence = {
            "schema_version": 1,
            "kind": "m5stack-worker-discovery-unicast-seed-nat",
            "date": "2026-10-25",
            "validation": "virtual control-plane validation",
            "status": "PASS" if all(checks.values()) else "FAIL",
            "topology": {
                "control_subnet": CONTROL_SUBNET,
                "worker_subnet": WORKER_SUBNET,
                "control_address": CONTROL_ADDRESS,
                "worker_address": WORKER_ADDRESS,
                "router_control_address": CONTROL_ROUTER_ADDRESS,
                "router_worker_address": WORKER_ROUTER_ADDRESS,
                "multicast_group": GROUP,
                "multicast_port": multicast_port,
                "seed_path": SEED_PATH,
                "ipv4_forwarding": True,
                "masquerade": True,
            },
            "discovery": {
                "control_url": control_url,
                "seed_url": seed_url,
                "initial_token_sha256": hashlib.sha256(
                    token.encode()
                ).hexdigest(),
                "rotated_token_sha256": hashlib.sha256(
                    rotated_token.encode()
                ).hexdigest(),
                "control_observed_sources": sorted(set(observed_sources)),
            },
            "workers": {
                "seed_bootstrap": {
                    "returncode": good.returncode,
                    "state": by_id.get(
                        "seed-bootstrap-worker", {}
                    ).get("state"),
                },
                "rotated_seed": {
                    "returncode": rotated.returncode,
                    "state": by_id.get(
                        "rotated-seed-worker", {}
                    ).get("state"),
                },
                "multicast_returncode": multicast.returncode,
                "wrong_token_returncode": wrong.returncode,
                "old_token_returncode": old.returncode,
            },
            "checks": checks,
            "tool_hashes": hashes_before,
            "input_assets_unchanged": input_assets_unchanged,
            "cleanup": {
                "control_service_exit": service.poll() is not None,
                "seed_service_exit": seed.poll() is not None,
                "namespaces": namespaces_after.strip().splitlines(),
                "nftables_contains_table": NAT_TABLE in nft_after,
            },
            "not_claimed": [
                "physical cross-host execution",
                "arbitrary NAT traversal without a reachable seed",
                "QEMU execution through the discovered control plane",
                "production multi-host scheduling",
                "physical hardware validation",
            ],
            "redaction": {
                "tokens_removed": True,
                "raw_token_files_removed_after_run": True,
            },
        }
        (args.out_dir / "evidence.json").write_text(
            json.dumps(evidence, indent=2) + "\n"
        )
        print(json.dumps(evidence, indent=2))
        return 0 if evidence["status"] == "PASS" else 1
    finally:
        stop_process(seed)
        stop_process(service)
        if seed_thread is not None:
            seed_thread.join(timeout=2)
        if service_thread is not None:
            service_thread.join(timeout=2)
        fixture.cleanup()
        token_file.unlink(missing_ok=True)
        old_token_file.unlink(missing_ok=True)
        wrong_token_file.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())

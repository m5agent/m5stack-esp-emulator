#!/usr/bin/env python3
"""Run two real QEMU guests on an isolated Linux L2 fabric."""
from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import os
import signal
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "platform/tools"))

from network_fabric import (  # noqa: E402
    GUEST_ADDRESSES,
    GUEST_MACS,
    LabSocketFabric,
    LabFabricError,
)
from pcap_summary import summarize_pcap  # noqa: E402


FABRIC_TOOL = ROOT / "platform/tools/network_fabric.py"
FLASH_SIZE = 8 << 20
PEER_PORT = 19123
A_MARKERS = (
    "LAB_FABRIC_A DHCP 10.230.0.2",
    "LAB_FABRIC_A PASS",
)
B_MARKERS = (
    "LAB_FABRIC_B DHCP 10.230.0.3",
    "LAB_FABRIC_B READY 19123",
    "LAB_FABRIC_B PASS",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stop_process(process: subprocess.Popen | None) -> None:
    if process is None or process.poll() is not None:
        return
    try:
        os.killpg(process.pid, signal.SIGTERM)
    except (OSError, ProcessLookupError):
        process.terminate()
    try:
        process.wait(timeout=8)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(process.pid, signal.SIGKILL)
        except (OSError, ProcessLookupError):
            process.kill()
        process.wait(timeout=5)


def close_process_log(process: subprocess.Popen | None) -> None:
    if process is None:
        return
    log = getattr(process, "_m5_log", None)
    if log is not None:
        log.close()


def wait_for_file(path: Path, *, timeout: float) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if path.is_file():
            return True
        time.sleep(0.1)
    return False


def wait_for_markers(
    path: Path,
    markers: tuple[str, ...],
    *,
    process: subprocess.Popen,
    timeout: float,
) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        text = path.read_text(errors="replace") if path.is_file() else ""
        if all(marker in text for marker in markers):
            return True
        if process.poll() is not None:
            return False
        time.sleep(0.2)
    return False


class HostTarget:
    def __init__(self) -> None:
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self) -> None:
                body = b"HOST_CONTROL_PLANE_MUST_NOT_BE_REACHABLE\n"
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def log_message(self, _format: str, *_args: object) -> None:
                return

        self.server = http.server.ThreadingHTTPServer(("0.0.0.0", 0), Handler)
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            name="m5-lab-host-control",
            daemon=True,
        )

    @property
    def port(self) -> int:
        return int(self.server.server_address[1])

    def start(self) -> None:
        self.thread.start()

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


def default_route_source() -> str:
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        sock.connect(("1.1.1.1", 80))
        return str(sock.getsockname()[0])


def isolation_probe(
    output: Path,
    *,
    host: str,
    host_port: int,
) -> int:
    probes = {}
    for name, target in (
        ("host_control", (host, host_port)),
        ("public_web", ("1.1.1.1", 80)),
        ("metadata", ("169.254.169.254", 80)),
    ):
        started = time.monotonic()
        try:
            with socket.create_connection(target, timeout=2):
                connected = True
                error = None
        except OSError as exc:
            connected = False
            error = f"{type(exc).__name__}: {exc}"
        probes[name] = {
            "connected": connected,
            "error": error,
            "elapsed_seconds": round(time.monotonic() - started, 3),
        }
    routes = subprocess.run(
        ["ip", "-json", "-4", "route", "show"],
        text=True,
        capture_output=True,
        check=False,
    )
    links = subprocess.run(
        ["ip", "-json", "link", "show"],
        text=True,
        capture_output=True,
        check=False,
    )
    output.write_text(
        json.dumps(
            {
                "probes": probes,
                "routes": (
                    json.loads(routes.stdout)
                    if routes.returncode == 0 and routes.stdout
                    else []
                ),
                "links": (
                    json.loads(links.stdout)
                    if links.returncode == 0 and links.stdout
                    else []
                ),
            },
            indent=2,
        )
        + "\n"
    )
    return 0 if not any(row["connected"] for row in probes.values()) else 1


def flow_present(
    summary: dict,
    *,
    source: str,
    destination: str,
    source_port: int | None = None,
    destination_port: int | None = None,
) -> bool:
    for flow in summary.get("flows", []):
        if flow.get("protocol") != "TCP":
            continue
        flow_source = str(flow.get("source", ""))
        flow_destination = str(flow.get("destination", ""))
        if not flow_source.startswith(source + ":"):
            continue
        if not flow_destination.startswith(destination + ":"):
            continue
        if (
            source_port is not None
            and flow_source != f"{source}:{source_port}"
        ):
            continue
        if (
            destination_port is not None
            and flow_destination != f"{destination}:{destination_port}"
        ):
            continue
        if flow.get("payload_sha256"):
            return True
    return False


def qemu_command(
    qemu: Path,
    rom_dir: Path,
    image: Path,
    efuse: Path,
    *,
    fabric: LabSocketFabric,
    endpoint_index: int,
    serial_path: Path,
    pcap_path: Path,
) -> list[str]:
    endpoint = fabric.endpoints[endpoint_index]
    return [
        str(qemu),
        "-accel",
        "tcg,thread=single",
        "-snapshot",
        "-M",
        "m5sticks3",
        "-m",
        "8M",
        "-drive",
        f"file={image},if=mtd,format=raw",
        "-drive",
        f"if=none,id=efuse{endpoint_index},file={efuse},format=raw",
        "-L",
        str(rom_dir),
        "-display",
        "none",
        "-monitor",
        "none",
        "-serial",
        f"file:{serial_path}",
        "-nic",
        (
            "socket,model=misc.esp32s3.wifi,id=wifi0,"
            f"mac={endpoint.mac},connect={fabric.listen_host}:"
            f"{fabric.listen_port}"
        ),
        "-object",
        (
            "filter-dump,id=netdump,netdev=wifi0,"
            f"file={pcap_path},maxlen=262144"
        ),
        "-global",
        (
            f"driver=nvram.esp32s3.efuse,property=drive,"
            f"value=efuse{endpoint_index}"
        ),
    ]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--rom-dir", type=Path, required=True)
    parser.add_argument("--image-a", type=Path, required=True)
    parser.add_argument("--image-b", type=Path, required=True)
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--probe-isolation", action="store_true")
    parser.add_argument("--probe-output", type=Path)
    parser.add_argument("--host")
    parser.add_argument("--host-port", type=int)
    args = parser.parse_args()

    if args.probe_isolation:
        if (
            args.probe_output is None
            or args.host is None
            or args.host_port is None
        ):
            parser.error(
                "isolation probe requires output, host and host port"
            )
        return isolation_probe(
            args.probe_output,
            host=args.host,
            host_port=args.host_port,
        )
    if sys.platform != "linux":
        parser.error("the two-guest lab fabric requires Linux")
    for label, path in (
        ("QEMU", args.qemu),
        ("ROM directory", args.rom_dir),
        ("guest A image", args.image_a),
        ("guest B image", args.image_b),
        ("fabric helper", FABRIC_TOOL),
    ):
        if not path.exists():
            parser.error(f"{label} does not exist: {path}")
    for label, image in (
        ("guest A", args.image_a),
        ("guest B", args.image_b),
    ):
        if image.stat().st_size != FLASH_SIZE:
            parser.error(f"{label} image must be exactly 8 MiB")

    out = args.out_dir.resolve()
    out.mkdir(parents=True, exist_ok=True)
    paths = {
        "serial_a": out / "serial-a.log",
        "serial_b": out / "serial-b.log",
        "pcap_a": out / "guest-a.pcap",
        "pcap_b": out / "guest-b.pcap",
        "dhcp_ready": out / "dhcp-ready.json",
        "dhcp_leases": out / "dhcp-leases.json",
        "switch_log": out / "switch.log",
        "switch_state": out / "switch-state.json",
        "probe": out / "isolation-probe.json",
        "evidence": out / "evidence.json",
    }
    for path in paths.values():
        path.unlink(missing_ok=True)
    efuses = []
    for index in range(2):
        efuse = out / f"efuse-{index}.bin"
        data = bytearray(4096)
        data[36:40] = (1 << 21).to_bytes(4, "little")
        efuse.write_bytes(data)
        efuses.append(efuse)

    fabric = LabSocketFabric.allocate()
    switch: subprocess.Popen | None = None
    guest_a: subprocess.Popen | None = None
    guest_b: subprocess.Popen | None = None
    host_target = HostTarget()
    host_target.start()
    started = time.monotonic()
    namespace_before = []
    namespace_after = []
    isolation_exit = 1
    try:
        fabric.start()
        namespace_before = subprocess.run(
            ["ip", "netns", "list"],
            text=True,
            capture_output=True,
            check=False,
        ).stdout.splitlines()
        switch_config = out / "switch.json"
        switch_config.write_text(
            json.dumps(
                {
                    "listen_host": fabric.listen_host,
                    "listen_port": fabric.listen_port,
                    "expected_clients": 2,
                    "server_address": "10.230.0.1",
                    "prefix_length": 24,
                    "lease_seconds": 3600,
                    "reservations": dict(zip(GUEST_MACS, GUEST_ADDRESSES)),
                    "endpoints": [
                        {
                            "index": endpoint.index,
                            "mac": endpoint.mac,
                            "address": endpoint.address,
                        }
                        for endpoint in fabric.endpoints
                    ],
                    "lease_file": str(paths["dhcp_leases"]),
                    "ready_file": str(paths["dhcp_ready"]),
                    "state_file": str(paths["switch_state"]),
                    "trace": os.environ.get("M5_LAB_FABRIC_TRACE") == "1",
                },
                indent=2,
            )
            + "\n"
        )
        switch = fabric.run(
            [
                sys.executable,
                str(FABRIC_TOOL),
                "switch",
                "--config",
                str(switch_config),
            ],
            log_path=paths["switch_log"],
        )
        if not wait_for_file(paths["dhcp_ready"], timeout=10):
            raise LabFabricError("lab socket switch did not become ready")

        isolation_exit = subprocess.run(
            fabric.command(
                [
                    sys.executable,
                    str(Path(__file__).resolve()),
                    "--probe-isolation",
                    "--probe-output",
                    str(paths["probe"]),
                    "--host",
                    default_route_source(),
                    "--host-port",
                    str(host_target.port),
                    "--qemu",
                    str(args.qemu),
                    "--rom-dir",
                    str(args.rom_dir),
                    "--image-a",
                    str(args.image_a),
                    "--image-b",
                    str(args.image_b),
                    "--out-dir",
                    str(out),
                ]
            ),
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=20,
            check=False,
        ).returncode

        qemu_a = qemu_command(
            args.qemu.resolve(),
            args.rom_dir.resolve(),
            args.image_a.resolve(),
            efuses[0],
            fabric=fabric,
            endpoint_index=0,
            serial_path=paths["serial_a"],
            pcap_path=paths["pcap_a"],
        )
        qemu_b = qemu_command(
            args.qemu.resolve(),
            args.rom_dir.resolve(),
            args.image_b.resolve(),
            efuses[1],
            fabric=fabric,
            endpoint_index=1,
            serial_path=paths["serial_b"],
            pcap_path=paths["pcap_b"],
        )
        guest_a = fabric.run(
            qemu_a,
            log_path=out / "qemu-a.log",
        )
        guest_b = fabric.run(
            qemu_b,
            log_path=out / "qemu-b.log",
        )
        b_ready = wait_for_markers(
            paths["serial_b"],
            B_MARKERS,
            process=guest_b,
            timeout=args.timeout,
        )
        a_ready = wait_for_markers(
            paths["serial_a"],
            A_MARKERS,
            process=guest_a,
            timeout=args.timeout,
        )
        time.sleep(1)
    finally:
        stop_process(guest_a)
        stop_process(guest_b)
        close_process_log(guest_a)
        close_process_log(guest_b)
        stop_process(switch)
        close_process_log(switch)
        fabric.cleanup()
        namespace_after = subprocess.run(
            ["ip", "netns", "list"],
            text=True,
            capture_output=True,
            check=False,
        ).stdout.splitlines()
        host_target.close()

    serial_a = (
        paths["serial_a"].read_text(errors="replace")
        if paths["serial_a"].is_file()
        else ""
    )
    serial_b = (
        paths["serial_b"].read_text(errors="replace")
        if paths["serial_b"].is_file()
        else ""
    )
    probe = (
        json.loads(paths["probe"].read_text())
        if paths["probe"].is_file()
        else {}
    )
    leases = (
        json.loads(paths["dhcp_leases"].read_text())
        if paths["dhcp_leases"].is_file()
        else {}
    )
    switch_state = (
        json.loads(paths["switch_state"].read_text())
        if paths["switch_state"].is_file()
        else {}
    )
    capture_a = (
        summarize_pcap(paths["pcap_a"])
        if paths["pcap_a"].is_file() and paths["pcap_a"].stat().st_size > 24
        else {}
    )
    capture_b = (
        summarize_pcap(paths["pcap_b"])
        if paths["pcap_b"].is_file() and paths["pcap_b"].stat().st_size > 24
        else {}
    )
    checks = {
        "guest_a_serial": all(marker in serial_a for marker in A_MARKERS),
        "guest_b_serial": all(marker in serial_b for marker in B_MARKERS),
        "guest_a_dhcp": GUEST_ADDRESSES[0]
        in capture_a.get("dhcp", {}).get("guest_addresses", []),
        "guest_b_dhcp": GUEST_ADDRESSES[1]
        in capture_b.get("dhcp", {}).get("guest_addresses", []),
        "dhcp_reservations": leases.get("leases")
        == dict(zip(GUEST_MACS, GUEST_ADDRESSES)),
        "switch_mac_binding": all(
            (
                str(endpoint.index) in switch_state.get(
                    "client_slot_by_endpoint",
                    {},
                )
                and switch_state.get("mac_by_client_slot", {}).get(
                    str(
                        switch_state["client_slot_by_endpoint"][
                            str(endpoint.index)
                        ]
                    )
                )
                == endpoint.mac
            )
            for endpoint in fabric.endpoints
        )
        and not any(
            switch_state.get("pending_frames", {}).values()
        ),
        "guest_a_to_b_tcp": flow_present(
            capture_a,
            source=GUEST_ADDRESSES[0],
            destination=GUEST_ADDRESSES[1],
            destination_port=PEER_PORT,
        ),
        "guest_b_to_a_tcp": flow_present(
            capture_b,
            source=GUEST_ADDRESSES[1],
            destination=GUEST_ADDRESSES[0],
            source_port=PEER_PORT,
        ),
        "guest_a_pcap": bool(capture_a),
        "guest_b_pcap": bool(capture_b),
        "host_control_unreachable": (
            probe.get("probes", {}).get("host_control", {}).get(
                "connected"
            )
            is False
        ),
        "public_unreachable": (
            probe.get("probes", {}).get("public_web", {}).get(
                "connected"
            )
            is False
        ),
        "metadata_unreachable": (
            probe.get("probes", {}).get("metadata", {}).get(
                "connected"
            )
            is False
        ),
        "isolation_probe_exit_zero": isolation_exit == 0,
        "no_default_route": not any(
            route.get("dst") == "default"
            for route in probe.get("routes", [])
        ),
        "namespace_created": any(
            line.split(maxsplit=1)[0] == fabric.namespace
            for line in namespace_before
            if line.strip()
        ),
        "namespace_cleaned": all(
            line.split(maxsplit=1)[0] != fabric.namespace
            for line in namespace_after
            if line.strip()
        ),
    }
    status = "PASS" if all(checks.values()) else "FAIL"
    evidence = {
        "schema_version": 1,
        "kind": "m5stack-two-guest-linux-lab-fabric",
        "scope": "virtual-device-network-not-hardware-rf",
        "date": "2026-10-24",
        "status": status,
        "duration_seconds": round(time.monotonic() - started, 3),
        "checks": checks,
        "fabric": fabric.metadata(),
        "firmware": {
            "guest_a": {
                "bytes": args.image_a.stat().st_size,
                "sha256": sha256(args.image_a),
            },
            "guest_b": {
                "bytes": args.image_b.stat().st_size,
                "sha256": sha256(args.image_b),
            },
        },
        "qemu": {
            "version_target": "xtensa-softmmu",
            "sha256": sha256(args.qemu),
        },
        "isolation_probe": probe,
        "dhcp_leases": leases,
        "switch_state": switch_state,
        "packet_captures": {
            "guest_a": capture_a,
            "guest_b": capture_b,
        },
        "serial": {
            "guest_a_bytes": len(serial_a.encode()),
            "guest_b_bytes": len(serial_b.encode()),
        },
        "not_claimed": [
            "physical hardware or RF",
            "WPA2 or WPA3 security",
            "workstation LAN isolation outside the container/namespace",
            "multi-host scheduling",
            "malware safety",
        ],
    }
    paths["evidence"].write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
    )
    print(json.dumps(evidence, ensure_ascii=False, indent=2))
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

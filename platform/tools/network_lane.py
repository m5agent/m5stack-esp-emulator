#!/usr/bin/env python3
"""Run reproducible esp-emu WiFi/BLE checks against a disposable lab network."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import signal
import socket
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EMULATOR = (
    ROOT
    / ".work/esp-emu-versions/0.50.0"
    / "esp-emu-0.50.0-aarch64-apple-darwin/esp-emu"
)
BLE_PROBE = ROOT / "platform/tools/ble_probe.py"
HTTP_PROBE_PORT = 8070
SUPPORTED_CHIPS = {
    "esp32c3",
    "esp32c5",
    "esp32c6",
    "esp32h2",
    "esp32p4",
    "esp32s3",
    "esp32s31",
}


class LaneError(RuntimeError):
    pass


@dataclass(frozen=True)
class Artifact:
    role: str
    path: Path
    bytes: int
    sha256: str

    def evidence(self) -> dict:
        return {
            "role": self.role,
            "path": str(self.path),
            "bytes": self.bytes,
            "sha256": self.sha256,
        }


@dataclass(frozen=True)
class LaneConfig:
    profile: str
    chip: str
    firmware: Path
    elf: Path | None
    emulator: Path
    out_dir: Path
    timeout: float
    ssid: str
    password: str
    wifi_auth: str
    psram_size: str
    net_mode: str
    wifi: bool
    ble: bool
    ble_port: int
    ble_name: str
    tcp: bool
    expected_markers: list[str]


@dataclass
class LabServer:
    server: ThreadingHTTPServer
    thread: threading.Thread
    requests: list[str]
    request_seen: threading.Event

    @property
    def port(self) -> int:
        return int(self.server.server_port)

    def close(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)


class ProbeHandler(BaseHTTPRequestHandler):
    body = b"M" * (1024 * 1024)

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler contract
        self.server.requests.append(self.path)  # type: ignore[attr-defined]
        self.server.request_seen.set()  # type: ignore[attr-defined]
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(self.body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(self.body)

    def log_message(self, format: str, *args: Any) -> None:
        return


def file_artifact(role: str, path: Path) -> Artifact:
    path = path.resolve()
    if not path.is_file():
        raise LaneError(f"{role} does not exist: {path}")
    digest = hashlib.sha256()
    size = 0
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            digest.update(chunk)
            size += len(chunk)
    return Artifact(role, path, size, digest.hexdigest())


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def start_lab_server(port: int = 0) -> LabServer:
    requests: list[str] = []
    seen = threading.Event()
    server = ThreadingHTTPServer(("127.0.0.1", port), ProbeHandler)
    server.requests = requests  # type: ignore[attr-defined]
    server.request_seen = seen  # type: ignore[attr-defined]
    thread = threading.Thread(
        target=server.serve_forever,
        name="m5-network-lane-http",
        daemon=True,
    )
    thread.start()
    return LabServer(server, thread, requests, seen)


def uiflow2_injection(config: LaneConfig) -> str:
    ssid = json.dumps(config.ssid)
    password = json.dumps(config.password)
    name = json.dumps(config.ble_name)
    lines = ["import network,time"]
    if config.ble:
        lines.extend(
            [
                "from bleuart import BLEUARTServer",
                f"server=BLEUARTServer(name={name})",
                'server.irq(lambda: print("LANE_BLE_RX", bytes(server.read())))',
                'print("LANE_BLE_READY")',
            ]
        )
    if config.wifi:
        lines.extend(
            [
                "w=network.WLAN(network.STA_IF)",
                "w.active(True)",
                'print("LANE_WIFI_SCAN", len(w.scan()))',
                f"w.connect({ssid},{password})",
                "time.sleep(6)",
                'print("LANE_WIFI_CONNECTED", w.isconnected())',
                'print("LANE_WIFI_STATUS", w.status())',
                'print("LANE_WIFI_IP", w.ifconfig()[0])',
            ]
        )
    lines.append('print("LANE_DONE")')
    return "\r\n".join(lines) + "\r\n"


def build_emulator_command(
    config: LaneConfig,
    *,
    firmware_copy: Path,
) -> tuple[list[str], dict]:
    use_bumble = config.profile == "uiflow2-sticks3" and config.ble
    command = [
        str(config.emulator),
        "--chip",
        config.chip,
        "--firmware",
        str(firmware_copy),
    ]
    if config.psram_size != "0":
        command.extend(["--psram-size", config.psram_size])
    command.extend(
        [
            "--net",
            config.net_mode,
            "--wifi-ssid",
            config.ssid,
            "--wifi-password",
            config.password,
            "--wifi-auth",
            config.wifi_auth,
            "--console",
            "uart0",
            "--timeout",
            f"{config.timeout:g}s",
            "--log-color",
            "never",
        ]
    )
    injection: dict[str, Any] = {}
    if config.elf is not None:
        command.extend(["--elf", str(config.elf)])
    if use_bumble:
        command.extend(["--ble-hci", f"tcp:127.0.0.1:{config.ble_port}"])
    if config.profile == "esp-idf-smoke":
        command.append("--no-panic-intercept")
    exit_marker = {
        "esp-idf-http": "HTTP_TPUT_RESULT",
        "esp-idf-smoke": "RESULT_SUMMARY",
    }.get(config.profile)
    if exit_marker:
        command.extend(["--exit-on", exit_marker])
    for marker in config.expected_markers:
        command.extend(["--exit-on", marker])
    if config.profile == "uiflow2-sticks3":
        injection = {
            "stages": [
                {
                    "trigger": "WiFi initialized",
                    "payload": "\x03",
                },
                {
                    "trigger": ">>>",
                    "payload": (
                        "import os,machine\r\n"
                        'os.rename("/flash/boot.py","/flash/boot.py.lane")\r\n'
                        "machine.reset()\r\n"
                    ),
                },
                {
                    "trigger": "RTC_SW_CPU_RST",
                    "payload": uiflow2_injection(config),
                },
            ]
        }
        for stage in injection["stages"]:
            command.extend(
                [
                    "--inject-on",
                    stage["trigger"],
                    "--inject",
                    stage["payload"],
                ]
            )
    return command, injection


def redact_command(command: list[str], password: str) -> str:
    safe = [entry.replace(password, "<redacted>") if password else entry for entry in command]
    return shlex.join(safe)


def read_text(path: Path) -> str:
    if not path.is_file():
        return ""
    return path.read_text(errors="replace")


def terminate_process(proc: subprocess.Popen | None, timeout: float = 5) -> None:
    if proc is None or proc.poll() is not None:
        return
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGTERM)
        else:
            proc.terminate()
    except (OSError, ProcessLookupError):
        proc.terminate()
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            if os.name == "posix":
                os.killpg(proc.pid, signal.SIGKILL)
            else:
                proc.kill()
        except (OSError, ProcessLookupError):
            proc.kill()
        proc.wait(timeout=5)


def start_ble_probe(config: LaneConfig, log_path: Path) -> tuple[subprocess.Popen, threading.Event]:
    ready = threading.Event()
    environment = os.environ.copy()
    python_path = str(ROOT / ".work/py")
    environment["PYTHONPATH"] = os.pathsep.join(
        filter(None, [python_path, environment.get("PYTHONPATH", "")])
    )
    command = [
        sys.executable,
        str(BLE_PROBE),
        "--port",
        str(config.ble_port),
        "--name-prefix",
        config.ble_name,
        "--timeout",
        f"{max(10, config.timeout - 5):g}",
        "--write-delay",
        "10",
        "--linger",
        "15",
    ]
    log = log_path.open("w")
    proc = subprocess.Popen(
        command,
        cwd=ROOT,
        env=environment,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        start_new_session=True,
    )
    assert proc.stdout is not None

    def collect() -> None:
        for line in proc.stdout:
            log.write(line)
            log.flush()
            if "BLE_PROBE_READY" in line:
                ready.set()
        log.close()

    threading.Thread(
        target=collect,
        name="m5-network-lane-ble-log",
        daemon=True,
    ).start()
    return proc, ready


def check_uiflow2_evidence(
    serial: str,
    ble_log: str,
    *,
    wifi: bool,
    ble: bool,
) -> tuple[dict[str, bool], dict[str, str]]:
    scan_match = re.search(r"LANE_WIFI_SCAN\s+(\d+)", serial)
    ip_match = re.search(r"LANE_WIFI_IP\s+(192\.168\.4\.\d+)", serial)
    checks: dict[str, bool] = {}
    if wifi:
        checks.update(
            {
                "wifi_scan": bool(scan_match and int(scan_match.group(1)) >= 1),
                "wifi_association": bool(
                    re.search(r"LANE_WIFI_CONNECTED\s+True", serial)
                ),
                "wifi_dhcp": bool(
                    re.search(r"LANE_WIFI_STATUS\s+1010", serial)
                    and ip_match
                ),
            }
        )
    if ble:
        checks["ble_probe"] = bool(
            "BLE_BUMBLE_PASS" in ble_log
            and "BLE_BUMBLE_GATT_DISCOVERED" in ble_log
            and "BLE_BUMBLE_SUBSCRIBED" in ble_log
            and "BLE_BUMBLE_WRITE" in ble_log
        )
        checks["ble_device_to_host"] = bool(
            "LANE_BLE_RX" in serial and "M5_LANE" in serial
        )
    checks["guest_completed"] = bool(
        re.search(r"(?m)^LANE_DONE\s*$", serial)
    )
    values = {
        "wifi_ip": ip_match.group(1) if ip_match else "",
        "ble_name": (
            match.group(1)
            if (match := re.search(r"BLE_BUMBLE_FOUND name='([^']+)'", ble_log))
            else ""
        ),
        "ble_payload": (
            match.group(1)
            if (match := re.search(r"LANE_BLE_RX b'([^']+)'", serial))
            else ""
        ),
    }
    return checks, values


def check_http_evidence(serial: str, requests: list[str]) -> dict[str, bool]:
    return {
        "wifi_dhcp": bool(
            re.search(r"GOT_IP\s+192\.168\.4\.2", serial)
            and "HTTP 200" in serial
        ),
        "http_request": "/bigfile" in requests,
        "complete_download": bool(
            re.search(r"download complete=1", serial)
            or re.search(r"\(complete=1\)", serial)
        ),
        "http_probe": bool(
            re.search(r"HTTP_TPUT:\s+bytes=[1-9]\d*", serial)
            and "HTTP_TPUT_RESULT: PASSED" in serial
        ),
    }


def check_generic_evidence(
    serial: str,
    expected_markers: list[str],
) -> dict[str, bool]:
    if expected_markers:
        return {
            f"marker:{index + 1}": marker in serial
            for index, marker in enumerate(expected_markers)
        }
    return {"runtime_output": bool(serial.strip())}


def check_smoke_evidence(serial: str, require_ble: bool) -> dict[str, bool]:
    checks = {
        "wifi_dhcp": bool(
            re.search(r"WiFi: GOT_IP\s+192\.168\.4\.2", serial)
            and re.search(r"TEST wifi:\s*PASSED", serial)
        ),
        "summary": "RESULT_SUMMARY:" in serial,
    }
    if require_ble:
        checks["ble_advertising"] = bool(
            "BLE: advertising as" in serial
            and re.search(r"TEST ble:\s*PASSED", serial)
            and "failed=0" in serial
        )
    return checks


def execute(config: LaneConfig) -> dict:
    if config.chip not in SUPPORTED_CHIPS:
        raise LaneError(
            f"chip {config.chip!r} is not supported by esp-emu; "
            "Core2 ESP32 LX6 needs a separate network/PHY path"
        )
    firmware = file_artifact("firmware", config.firmware)
    emulator = file_artifact("emulator", config.emulator)
    elf = file_artifact("elf", config.elf) if config.elf else None
    config.out_dir.mkdir(parents=True, exist_ok=True)

    firmware_copy = config.out_dir / "firmware-under-test.bin"
    firmware_copy.write_bytes(config.firmware.read_bytes())
    firmware_copy_artifact = file_artifact("firmware-runtime-copy", firmware_copy)

    initial_requests: list[str] = []
    lab_server: LabServer | None = None
    tcp_port = free_port()
    if config.tcp:
        lab_server = start_lab_server(
            HTTP_PROBE_PORT if config.profile == "esp-idf-http" else 0
        )
        initial_requests = lab_server.requests
        tcp_port = lab_server.port

    serial_path = config.out_dir / "serial.log"
    ble_log_path = config.out_dir / "ble-probe.log"
    command, injection = build_emulator_command(
        config,
        firmware_copy=firmware_copy,
    )
    public_command = redact_command(command, config.password)
    if config.password:
        for stage in injection.get("stages", []):
            stage["payload"] = stage["payload"].replace(
                config.password, "<redacted>"
            )

    ble_proc: subprocess.Popen | None = None
    emu_proc: subprocess.Popen | None = None
    use_bumble = config.profile == "uiflow2-sticks3" and config.ble
    timed_out = False
    started = time.monotonic()
    try:
        if use_bumble:
            ble_proc, ble_ready = start_ble_probe(config, ble_log_path)
            if not ble_ready.wait(timeout=10):
                raise LaneError("Bumble BLE probe did not become ready")

        with serial_path.open("wb") as serial_log:
            emu_proc = subprocess.Popen(
                command,
                cwd=ROOT,
                stdout=serial_log,
                stderr=subprocess.STDOUT,
                start_new_session=True,
            )
            deadline = time.monotonic() + config.timeout + 10
            ble_exited_at: float | None = None
            while time.monotonic() < deadline:
                if emu_proc.poll() is not None:
                    break
                serial_snapshot = read_text(serial_path)
                ble_snapshot = read_text(ble_log_path)
                guest_done = bool(
                    re.search(r"(?m)^LANE_DONE\s*$", serial_snapshot)
                )
                ble_done = not use_bumble or (
                    "BLE_BUMBLE_PASS" in ble_snapshot
                    and re.search(
                        r"(?m)^LANE_BLE_RX b'M5_LANE'\s*$",
                        serial_snapshot,
                    )
                )
                if guest_done and ble_done:
                    break
                if use_bumble and ble_proc is not None and ble_proc.poll() is not None:
                    ble_exited_at = ble_exited_at or time.monotonic()
                    if (
                        re.search(r"(?m)^LANE_BLE_RX b'M5_LANE'\s*$", serial_snapshot)
                        and re.search(r"(?m)^LANE_DONE\s*$", serial_snapshot)
                    ):
                        break
                    if time.monotonic() - ble_exited_at >= 3:
                        break
                time.sleep(0.25)
            else:
                timed_out = True
    finally:
        terminate_process(emu_proc)
        terminate_process(ble_proc)
        if lab_server is not None:
            lab_server.close()

    duration = round(time.monotonic() - started, 3)
    serial = read_text(serial_path)
    if config.password:
        serial = serial.replace(config.password, "<redacted>")
    serial_path.write_text(serial)
    ble_log = read_text(ble_log_path)

    if config.profile == "uiflow2-sticks3":
        checks, values = check_uiflow2_evidence(
            serial,
            ble_log,
            wifi=config.wifi,
            ble=config.ble,
        )
    elif config.profile == "esp-idf-http":
        checks = check_http_evidence(serial, initial_requests)
        values = {}
    elif config.profile == "generic-observe":
        checks = check_generic_evidence(serial, config.expected_markers)
        values = {}
    else:
        checks = check_smoke_evidence(serial, require_ble=config.ble)
        values = {}

    required = list(checks)
    passed = all(checks[name] for name in required)
    if config.profile == "generic-observe" and not config.expected_markers:
        passed = False
    if not passed and any(checks[name] for name in required):
        status = "PARTIAL"
    else:
        status = "PASS" if passed else "FAIL"

    artifact_rows = [firmware, emulator, firmware_copy_artifact]
    if elf is not None:
        artifact_rows.insert(1, elf)
    evidence = {
        "schema_version": 1,
        "kind": "m5stack-network-lane-proof",
        "scope": "simulation-only-not-hardware-validation",
        "status": status,
        "profile": config.profile,
        "chip": config.chip,
        "runtime": {
            "name": "esp-emu",
            "expected_version": "0.50.0",
            "network_backend": config.net_mode,
            "wifi": {
                "enabled": config.wifi,
                "ssid": config.ssid,
                "password": "<redacted>",
                "auth": config.wifi_auth,
            },
            "ble": {
                "enabled": config.ble,
                "observer": (
                    "bumble"
                    if use_bumble
                    else ("esp-emu-built-in" if config.ble else None)
                ),
                "name": config.ble_name,
            },
            "tcp": {
                "enabled": config.tcp,
                "guest_endpoint": (
                    f"192.168.4.1:{tcp_port}" if config.tcp else None
                ),
                "host_requests": list(initial_requests),
            },
        },
        "artifacts": [artifact.evidence() for artifact in artifact_rows],
        "command": public_command,
        "injection": injection,
        "checks": checks,
        "values": values,
        "result": {
            "status": status,
            "passed": passed,
            "timed_out": timed_out,
            "duration_seconds": duration,
            "emulator_exit_code": emu_proc.returncode if emu_proc else None,
            "ble_probe_exit_code": ble_proc.returncode if ble_proc else None,
            "serial_bytes": serial_path.stat().st_size,
            "serial_sha256": hashlib.sha256(serial.encode()).hexdigest(),
            "ble_probe_sha256": (
                hashlib.sha256(ble_log.encode()).hexdigest() if use_bumble else None
            ),
        },
        "not_claimed": [
            "real-hardware behavior",
            "public internet access",
            "TLS certificate validation",
            "device safety or malware sandboxing",
            "Bluedroid or Classic Bluetooth compatibility",
        ],
    }
    evidence_path = config.out_dir / "evidence.json"
    evidence_path.write_text(
        json.dumps(evidence, ensure_ascii=False, indent=2) + "\n"
    )
    return evidence


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--profile",
        choices=(
            "uiflow2-sticks3",
            "esp-idf-http",
            "esp-idf-smoke",
            "generic-observe",
        ),
        default="uiflow2-sticks3",
    )
    parser.add_argument("--chip", default="esp32s3")
    parser.add_argument("--firmware", type=Path, required=True)
    parser.add_argument("--elf", type=Path)
    parser.add_argument("--emulator", type=Path, default=DEFAULT_EMULATOR)
    parser.add_argument("--out-dir", type=Path)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--ssid", default="myssid")
    parser.add_argument("--password", default="mypassword")
    parser.add_argument(
        "--wifi-auth",
        choices=("wpa2-wpa3", "wpa3-sae", "wpa2-psk", "open"),
        default="wpa2-wpa3",
    )
    parser.add_argument("--psram-size", default="8M")
    parser.add_argument("--net-mode", default="user")
    parser.add_argument("--wifi", action=argparse.BooleanOptionalAction)
    parser.add_argument("--ble", action=argparse.BooleanOptionalAction)
    parser.add_argument("--ble-port", type=int)
    parser.add_argument("--ble-name", default="M5-NETWORK-LANE")
    parser.add_argument(
        "--expect",
        action="append",
        default=[],
        help="required serial marker for generic-observe; repeatable",
    )
    parser.add_argument("--tcp", action=argparse.BooleanOptionalAction)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--json", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    out_dir = args.out_dir or Path("/tmp") / f"m5-network-{args.profile}-{timestamp}"
    config = LaneConfig(
        profile=args.profile,
        chip=args.chip,
        firmware=args.firmware,
        elf=args.elf,
        emulator=args.emulator,
        out_dir=out_dir,
        timeout=args.timeout,
        ssid=args.ssid,
        password=args.password,
        wifi_auth=args.wifi_auth,
        psram_size=args.psram_size,
        net_mode=args.net_mode,
        wifi=True if args.wifi is None else args.wifi,
        ble=False if args.ble is None else args.ble,
        ble_port=args.ble_port or free_port(),
        ble_name=args.ble_name,
        tcp=(
            args.profile == "esp-idf-http"
            if args.tcp is None
            else args.tcp
        ),
        expected_markers=list(args.expect),
    )
    if args.dry_run:
        firmware_copy = config.out_dir / "firmware-under-test.bin"
        command, injection = build_emulator_command(
            config,
            firmware_copy=firmware_copy,
        )
        payload = {
            "command": redact_command(command, config.password),
            "injection": injection,
        }
        print(json.dumps(payload, indent=2) if args.json else payload["command"])
        return 0
    try:
        evidence = execute(config)
    except (LaneError, OSError, subprocess.SubprocessError) as error:
        print(f"network lane failed: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(evidence, indent=2, ensure_ascii=False))
    else:
        print(f"status={evidence['status']} out_dir={config.out_dir}")
        for name, passed in evidence["checks"].items():
            print(f"  {name}: {'PASS' if passed else 'FAIL'}")
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())

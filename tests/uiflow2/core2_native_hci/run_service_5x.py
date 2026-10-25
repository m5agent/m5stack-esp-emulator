#!/usr/bin/env python3
"""Exercise the Core2 native-HCI runtime through the Device Service API."""
from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "platform/tools"))

from ble_runtime_limits import (  # noqa: E402
    MAX_BLE_HOLD_SECONDS,
    MAX_BLE_RECONNECT_CYCLES,
    reconnect_workload_timeout_seconds,
)
from qemu_accel import CORE2_TCG_TB_SIZE_MIB  # noqa: E402

PROFILE = "core2-native-hci"
READY_MARKER = "UNIFIED_CORE2_READY"
PSRAM_EXTERNAL_HEAP_MIN_BYTES = 4 << 20
PSRAM_MACHINE_CAPACITY_MIN_BYTES = 8 << 20
PSRAM_REQUESTED_BYTES = 1 << 20
EXPECTED_QEMU_ACCELERATOR = (
    f"tcg,thread=single,tb-size={CORE2_TCG_TB_SIZE_MIB}"
)
TOOL_PATHS = {
    "runner": Path(__file__).resolve(),
    "device_service": ROOT / "platform/tools/device_service.py",
    "qemu_accel": ROOT / "platform/tools/qemu_accel.py",
    "ble_runtime_limits": ROOT / "platform/tools/ble_runtime_limits.py",
    "ble_probe": ROOT / "platform/tools/ble_probe.py",
    "network_policy": ROOT / "platform/tools/network_policy.py",
    "unified_http_guestfwd": (
        ROOT / "platform/tools/unified_http_guestfwd.py"
    ),
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def freeze_input_hashes(
    image: Path,
    elf: Path,
    qemu: Path,
    tool_paths: dict[str, Path] | None = None,
) -> dict[str, str | int]:
    """Bind evidence to the exact inputs observed before the first lease."""
    result: dict[str, str | int] = {
        "firmware_bytes": image.stat().st_size,
        "firmware_sha256": sha256(image),
        "elf_sha256": sha256(elf),
        "qemu_sha256": sha256(qemu),
    }
    for name, path in (tool_paths or {}).items():
        result[f"{name}_sha256"] = sha256(path)
    return result


def parse_ps_rss_kib(output: str) -> int | None:
    value = output.strip()
    return int(value) if value.isdigit() else None


def parse_footprint_kib(output: str) -> int | None:
    match = re.search(
        r"^\s*phys_footprint:\s*([0-9]+(?:\.[0-9]+)?)\s*(B|KB|MB|GB)\s*$",
        output,
        re.MULTILINE,
    )
    if match is None:
        return None
    value = float(match.group(1))
    multiplier = {
        "B": 1 / 1024,
        "KB": 1,
        "MB": 1024,
        "GB": 1024 * 1024,
    }[match.group(2)]
    return round(value * multiplier)


def process_rss_kib(pid: int | None) -> int | None:
    if not pid:
        return None
    try:
        result = subprocess.run(
            ["ps", "-o", "rss=", "-p", str(pid)],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_ps_rss_kib(result.stdout)


def process_phys_footprint_kib(pid: int | None) -> int | None:
    if not pid or sys.platform != "darwin":
        return None
    try:
        result = subprocess.run(
            ["/usr/bin/footprint", "-p", str(pid)],
            check=False,
            capture_output=True,
            text=True,
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_footprint_kib(result.stdout)


def process_memory_sample(pid: int | None) -> dict[str, int | None]:
    return {
        "rss_kib": process_rss_kib(pid),
        "phys_footprint_kib": process_phys_footprint_kib(pid),
    }


def parse_qemu_accelerator(command: str) -> str | None:
    match = re.search(r"(?:^|\s)-accel\s+(\S+)", command)
    return match.group(1) if match else None


def process_qemu_accelerator(pid: int | None) -> str | None:
    if not pid:
        return None
    try:
        result = subprocess.run(
            ["ps", "-o", "command=", "-p", str(pid)],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return parse_qemu_accelerator(result.stdout)


class Api:
    def __init__(self, base_url: str, token: str | None) -> None:
        self.base_url = base_url.rstrip("/")
        self.token = token

    def request(
        self,
        path: str,
        *,
        data: bytes | None = None,
        headers: dict[str, str] | None = None,
        method: str | None = None,
        timeout: float = 240,
    ) -> tuple[int, bytes, str]:
        request_headers = dict(headers or {})
        if self.token:
            request_headers["Authorization"] = f"Bearer {self.token}"
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            headers=request_headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return (
                    response.status,
                    response.read(),
                    response.headers.get("Content-Type", ""),
                )
        except urllib.error.HTTPError as error:
            body = error.read()
            raise RuntimeError(
                f"{path} returned HTTP {error.code}: {body[:1000]!r}"
            ) from error

    def json(
        self,
        path: str,
        *,
        payload: dict[str, Any] | None = None,
        timeout: float = 240,
        method: str | None = None,
    ) -> Any:
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload).encode()
            headers["Content-Type"] = "application/json"
        status, body, _ = self.request(
            path,
            data=data,
            headers=headers,
            method=method,
            timeout=timeout,
        )
        if status not in {200, 201, 202}:
            raise RuntimeError(f"{path} returned HTTP {status}")
        return json.loads(body)

    def upload(self, path: Path) -> str:
        status, body, _ = self.request(
            "/api/v1/artifacts",
            data=path.read_bytes(),
            headers={
                "Content-Type": "application/octet-stream",
                "X-Artifact-Name": path.name,
            },
        )
        if status != 201:
            raise RuntimeError(f"artifact upload returned HTTP {status}")
        return str(json.loads(body)["artifact_id"])


def wait_for_network(
    api: Api,
    session_id: str,
    timeout: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    latest: dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest = api.json(f"/api/v1/sessions/{session_id}/network")
        if latest.get("status") in {"PASS", "FAIL"}:
            return latest
        time.sleep(0.5)
    raise RuntimeError(
        "network evidence did not reach PASS/FAIL: "
        + json.dumps(latest, sort_keys=True)
    )


def wait_for_running(
    api: Api,
    session_id: str,
    timeout: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout
    latest: dict[str, Any] = {}
    while time.monotonic() < deadline:
        latest = api.json(f"/api/v1/sessions/{session_id}")
        state = latest.get("state")
        if state == "running":
            return latest
        if state in {"stopped", "failed"}:
            raise RuntimeError(
                f"session reached {state}: {latest.get('error')}"
            )
        time.sleep(0.1)
    raise RuntimeError(
        "session did not reach running: "
        + json.dumps(latest, sort_keys=True)
    )


def unpack_evidence(
    payload: bytes,
) -> tuple[
    set[str],
    dict[str, Any],
    bytes,
    bytes,
    bytes,
]:
    names: set[str] = set()
    manifest: dict[str, Any] = {}
    serial = b""
    peer_log = b""
    pcap = b""
    if not payload:
        return names, manifest, serial, peer_log, pcap
    try:
        with zipfile.ZipFile(io.BytesIO(payload)) as archive:
            names = set(archive.namelist())
            manifest = (
                json.loads(archive.read("manifest.json"))
                if "manifest.json" in names
                else {}
            )
            serial = (
                archive.read("serial.log")
                if "serial.log" in names
                else b""
            )
            peer_log = (
                archive.read("ble-probe.log")
                if "ble-probe.log" in names
                else b""
            )
            pcap = (
                archive.read("network/capture.pcap")
                if "network/capture.pcap" in names
                else b""
            )
    except (OSError, ValueError, KeyError, zipfile.BadZipFile):
        return set(), {}, b"", b"", b""
    return names, manifest, serial, peer_log, pcap


def native_hci_health(qom: dict[str, Any]) -> dict[str, int]:
    node = (
        qom.get("nodes", {})
        .get("peripheral-anon", {})
        .get("children", {})
        .get("device[0]", {})
        .get("children", {})
    )
    keys = (
        "hli-valid",
        "hli-posts",
        "hli-consumed",
        "hli-errors",
        "hli-c2h-events",
        "hli-c2h-acls",
        "hli-queue-depth",
        "meta-queue-depth",
        "conn-pool-valid",
        "hs-conns-head",
        "conn-pool-free",
        "l2cap-pool-valid",
        "l2cap-pool-free",
        "gatts-pool-valid",
        "gatts-pool-free",
        "hci-trace-packets",
        "api-send-trace-packets",
        "hli-deferred-not-halted",
        "hli-fast-path-events",
        "hli-fast-path-acls",
        "hli-event-prealloc-depth",
        "hli-acl-prealloc-depth",
        "hli-prealloc-failures",
        "trace-hci-cmd-tx",
        "trace-hs-sched-reset",
        "trace-gap-adv-start",
        "trace-gap-adv-stop",
        "dropped-packets",
        "tx-queue-depth",
        "last-error",
        "peer-closed",
    )
    return {
        key: int(node.get(key, {}).get("value", 0))
        for key in keys
        if isinstance(node.get(key), dict)
    }


def native_hci_health_ok(hci_health: dict[str, int]) -> bool:
    last_error = hci_health.get("last-error", -1)
    peer_closed = hci_health.get("peer-closed", 0)
    dropped_packets = hci_health.get("dropped-packets", 0)
    tx_queue_depth = hci_health.get("tx-queue-depth", 0)
    peer_tail_error = last_error in {0, 3} or (
        last_error == 2 and (dropped_packets > 0 or tx_queue_depth > 0)
    )
    return bool(
        hci_health.get("hli-valid") == 1
        and hci_health.get("hli-posts", 0) > 0
        and hci_health.get("hli-consumed")
        == hci_health.get("hli-posts")
        and hci_health.get("hli-errors") == 0
        and hci_health.get("hli-queue-depth") == 0
        and hci_health.get("meta-queue-depth") == 0
        and (
            last_error == 0
            or (peer_tail_error and peer_closed > 0)
        )
        and (
            hci_health.get("hli-c2h-events", 0)
            + hci_health.get("hli-c2h-acls", 0)
            > 0
        )
        and (
            hci_health.get("hli-fast-path-events", 0)
            + hci_health.get("hli-fast-path-acls", 0)
            > 0
        )
    )


def qom_memory_bytes(qom: dict[str, Any]) -> int | None:
    memory = qom.get("nodes", {}).get("memory")
    if not isinstance(memory, dict):
        return None
    value = memory.get("value")
    if not isinstance(value, dict):
        return None
    size = value.get("size")
    if isinstance(size, bool) or not isinstance(size, int):
        return None
    return size


def parse_psram_stress(serial_text: str) -> dict[str, Any]:
    allocations = [
        tuple(int(value) for value in match.groups())
        for match in re.finditer(
            r"(?m)^UNIFIED_CORE2_PSRAM_ALLOC\s+(\d+)\s+(\d+)\s+(\d+)\s*$",
            serial_text,
        )
    ]
    sweeps = sorted(
        int(value)
        for value in re.findall(
            r"(?m)^UNIFIED_CORE2_PSRAM_SWEEP\s+(\d+)\s*$",
            serial_text,
        )
    )
    heartbeats = [
        tuple(int(value) for value in match.groups())
        for match in re.finditer(
            (
                r"(?m)^UNIFIED_CORE2_STRESS_HEARTBEAT\s+"
                r"(\d+)\s+(\d+)\s+(\d+)\s+(\d+)\s*$"
            ),
            serial_text,
        )
    ]
    return {
        "marker_present": bool(
            "UNIFIED_CORE2_PSRAM_" in serial_text
        ),
        "allocations": allocations,
        "external_heap_total_bytes": (
            allocations[0][0] if len(allocations) == 1 else None
        ),
        "requested_bytes": (
            allocations[0][1] if len(allocations) == 1 else None
        ),
        "allocated_bytes": (
            allocations[0][2] if len(allocations) == 1 else None
        ),
        "sweeps": sweeps,
        "init_pass_count": serial_text.count(
            "UNIFIED_CORE2_PSRAM_INIT_PASS"
        ),
        "stress_pass_count": serial_text.count(
            "UNIFIED_CORE2_PSRAM_STRESS_PASS"
        ),
        "heartbeats": heartbeats,
        "http_recheck_pass_count": serial_text.count(
            "UNIFIED_CORE2_HTTP_RECHECK_PASS"
        ),
        "public_recheck_pass_count": serial_text.count(
            "UNIFIED_CORE2_PUBLIC_RECHECK_PASS"
        ),
        "verified_bytes": (
            len(sweeps) * allocations[0][1]
            if len(allocations) == 1
            else None
        ),
        "error_markers": [
            marker
            for marker in (
                "UNIFIED_CORE2_PSRAM_ERROR",
                "UNIFIED_CORE2_PSRAM_STRESS_ERROR",
                "UNIFIED_CORE2_HTTP_RECHECK_ERROR",
                "UNIFIED_CORE2_PUBLIC_RECHECK_ERROR",
            )
            if marker in serial_text
        ],
    }


def psram_stress_ok(evidence: dict[str, Any]) -> bool:
    allocations = evidence.get("allocations")
    sweeps = evidence.get("sweeps")
    if not isinstance(allocations, list) or not isinstance(sweeps, list):
        return False
    if len(allocations) != 1 or len(allocations[0]) != 3:
        return False
    total, requested, allocated = allocations[0]
    contiguous_sweeps = sweeps == list(range(1, len(sweeps) + 1))
    return bool(
        total >= PSRAM_EXTERNAL_HEAP_MIN_BYTES
        and requested == PSRAM_REQUESTED_BYTES
        and allocated >= requested
        and len(sweeps) >= 3
        and contiguous_sweeps
        and evidence.get("init_pass_count") == 1
        and evidence.get("stress_pass_count") == 1
        and not evidence.get("error_markers")
    )


def sustained_stress_requirements(hold_seconds: float) -> dict[str, int]:
    return {
        # Three concurrent guests each completed 29 of 30 expected sweeps in
        # 120 seconds. Keep a conservative floor with one sweep per five
        # seconds under the highest current concurrency.
        "minimum_sweeps": max(3, int(hold_seconds // 5)),
        "minimum_heartbeats": max(0, int(hold_seconds // 20)),
        "minimum_http_rechecks": max(0, int(hold_seconds // 15)),
        "minimum_public_rechecks": max(0, int(hold_seconds // 60)),
    }


def attempt_batches(
    attempts: int,
    concurrency: int,
) -> list[list[int]]:
    return [
        list(range(start, min(start + concurrency, attempts + 1)))
        for start in range(1, attempts + 1, concurrency)
    ]


def maximum_interval_overlap(
    intervals: list[tuple[float, float]],
) -> int:
    events = sorted(
        [
            event
            for start, end in intervals
            if end >= start
            for event in ((start, 1), (end, -1))
        ],
        key=lambda event: (event[0], event[1]),
    )
    active = 0
    maximum = 0
    for _, delta in events:
        active += delta
        maximum = max(maximum, active)
    return maximum


def sustained_stress_ok(
    evidence: dict[str, Any],
    hold_seconds: float,
) -> bool:
    requirements = sustained_stress_requirements(hold_seconds)
    sweeps = evidence.get("sweeps")
    heartbeats = evidence.get("heartbeats")
    if not isinstance(sweeps, list) or not isinstance(heartbeats, list):
        return False
    latest_psram = heartbeats[-1][1] if heartbeats else 0
    latest_http = heartbeats[-1][2] if heartbeats else 0
    latest_public = heartbeats[-1][3] if heartbeats else 0
    monotonic_heartbeats = all(
        all(left <= right for left, right in zip(previous, current))
        for previous, current in zip(heartbeats, heartbeats[1:])
    )
    return bool(
        len(sweeps) >= requirements["minimum_sweeps"]
        and len(heartbeats) >= requirements["minimum_heartbeats"]
        and monotonic_heartbeats
        and latest_psram <= len(sweeps)
        and latest_http
        <= evidence.get("http_recheck_pass_count", 0)
        and latest_public
        <= evidence.get("public_recheck_pass_count", 0)
        and evidence.get("http_recheck_pass_count", 0)
        >= requirements["minimum_http_rechecks"]
        and evidence.get("public_recheck_pass_count", 0)
        >= requirements["minimum_public_rechecks"]
    )


def manifest_session_binding_ok(
    manifest: dict[str, Any],
    session_id: str | None,
) -> bool:
    if not session_id:
        return False
    session = manifest.get("session")
    return bool(
        isinstance(session, dict)
        and session.get("session_id") == session_id
    )


def run_attempt(
    api: Api,
    firmware_id: str,
    elf_artifact_id: str,
    attempt_dir: Path,
    timeout: float,
    hold_seconds: float,
    ble_reconnect_cycles: int,
    require_psram: bool,
    start_delay_seconds: float = 0,
) -> dict[str, Any]:
    if start_delay_seconds > 0:
        time.sleep(start_delay_seconds)
    attempt_dir.mkdir(parents=True, exist_ok=True)
    session_id: str | None = None
    phase = "create_session"
    failure: Exception | None = None
    network: dict[str, Any] = {}
    frame = b""
    qom: dict[str, Any] = {}
    evidence = b""
    names: set[str] = set()
    manifest: dict[str, Any] = {}
    serial = b""
    peer_log = b""
    pcap = b""
    frame_status = 0
    evidence_status = 0
    hold_stable = False
    hold_state = "not_running"
    hold_error: str | None = None
    session_started_epoch: float | None = None
    session_finished_epoch: float | None = None
    rss_samples: list[int] = []
    phys_footprint_samples: list[int] = []
    qemu_accelerator: str | None = None
    state_samples = 0

    try:
        session = api.json(
            "/api/v1/sessions",
            payload={
                "device_id": "core2",
                "runtime": "qemu-unified",
                "firmware_id": firmware_id,
                "ready_timeout_seconds": timeout,
                "network": {
                    "profile": PROFILE,
                    "elf_artifact_id": elf_artifact_id,
                    "attempts": 1,
                    "capture_pcap": True,
                    "ble_linger_seconds": max(
                        20,
                        hold_seconds + 60,
                    ),
                    "ble_reconnect_cycles": ble_reconnect_cycles,
                    "ble_reconnect_delay_seconds": 2,
                },
            },
        )
        session_id = str(session["session_id"])
        session_started_epoch = time.time()
        phase = "wait_ready"
        api.json(
            f"/api/v1/sessions/{session_id}/wait",
            payload={
                "ready_marker": READY_MARKER,
                "timeout_seconds": timeout,
            },
            timeout=timeout + 15,
        )
        phase = "wait_running"
        running_session = wait_for_running(api, session_id, timeout)
        # A reconnect-only run has hold_seconds=0 and never enters the hold
        # loop below. Sample the live QEMU command when the session first
        # becomes running so bounded-TCG evidence is independent of hold mode.
        qemu_accelerator = process_qemu_accelerator(
            running_session.get("pid")
        )
        phase = "wait_network"
        network = wait_for_network(api, session_id, timeout)
        phase = "hold"
        hold_deadline = time.monotonic() + hold_seconds
        hold_stable = True
        hold_state = "running"
        last_resource_sample: float | None = None
        poll_seconds = 5.0 if hold_seconds >= 60 else 0.5
        while time.monotonic() < hold_deadline:
            current = api.json(f"/api/v1/sessions/{session_id}")
            state_samples += 1
            elapsed = time.monotonic() - (
                hold_deadline - hold_seconds
            )
            if (
                last_resource_sample is None
                or elapsed - last_resource_sample >= 30
            ):
                memory = process_memory_sample(current.get("pid"))
                rss = memory["rss_kib"]
                phys_footprint = memory["phys_footprint_kib"]
                if qemu_accelerator is None:
                    qemu_accelerator = process_qemu_accelerator(
                        current.get("pid")
                    )
                if isinstance(rss, int):
                    rss_samples.append(rss)
                if isinstance(phys_footprint, int):
                    phys_footprint_samples.append(phys_footprint)
                last_resource_sample = elapsed
            if current.get("state") != "running":
                hold_stable = False
                hold_state = str(current.get("state") or "unknown")
                raw_error = current.get("error")
                hold_error = (
                    str(raw_error) if raw_error is not None else None
                )
                break
            time.sleep(
                min(
                    poll_seconds,
                    max(0.0, hold_deadline - time.monotonic()),
                )
            )
        phase = "capture_evidence"
        frame_status, frame, _ = api.request(
            f"/api/v1/sessions/{session_id}/frame.png"
        )
        qom = api.json(
            f"/api/v1/sessions/{session_id}/qom-snapshot",
            payload={
                "path": "/machine",
                "depth": 2,
                "max_nodes": 1000,
            },
        )
        evidence_status, evidence, _ = api.request(
            f"/api/v1/sessions/{session_id}/evidence"
            "?include=manifest,serial,frames,logs,network,qom"
        )
    except Exception as error:  # noqa: BLE001 - persist every attempt failure.
        failure = error

    final_session: dict[str, Any] = {}
    session_read_error: str | None = None
    cleanup_error: str | None = None
    if session_id:
        try:
            final_session = api.json(f"/api/v1/sessions/{session_id}")
        except (RuntimeError, OSError, ValueError) as error:
            session_read_error = str(error).replace(session_id, "<session>")
        hold_state = str(final_session.get("state") or hold_state)
        raw_error = final_session.get("error")
        if raw_error is not None:
            hold_error = str(raw_error)

        if not network:
            try:
                network = api.json(f"/api/v1/sessions/{session_id}/network")
            except (RuntimeError, OSError, ValueError):
                network = {}
        if not frame:
            try:
                frame_status, frame, _ = api.request(
                    f"/api/v1/sessions/{session_id}/frame.png"
                )
            except (RuntimeError, OSError, ValueError):
                frame_status = 0
                frame = b""
        if not qom:
            try:
                qom = api.json(
                    f"/api/v1/sessions/{session_id}/qom-snapshot",
                    payload={
                        "path": "/machine",
                        "depth": 2,
                        "max_nodes": 1000,
                    },
                )
            except (RuntimeError, OSError, ValueError):
                qom = {}
        if not evidence:
            try:
                evidence_status, evidence, _ = api.request(
                    f"/api/v1/sessions/{session_id}/evidence"
                    "?include=manifest,serial,frames,logs,network,qom"
                )
            except (RuntimeError, OSError, ValueError):
                evidence_status = 0
                evidence = b""

    if frame:
        (attempt_dir / "frame.png").write_bytes(frame)
    if qom:
        (attempt_dir / "qom.json").write_text(
            json.dumps(qom, indent=2) + "\n"
        )
    if evidence:
        (attempt_dir / "evidence.zip").write_bytes(evidence)
        names, manifest, serial, peer_log, pcap = unpack_evidence(evidence)

    if session_id:
        try:
            api.json(
                f"/api/v1/sessions/{session_id}?purge=0",
                payload={},
                method="DELETE",
            )
            session_finished_epoch = time.time()
        except (RuntimeError, OSError, ValueError) as error:
            cleanup_error = str(error).replace(session_id, "<session>")
            session_finished_epoch = time.time()

    if session_id and not evidence:
        try:
            evidence_status, evidence, _ = api.request(
                f"/api/v1/sessions/{session_id}/evidence"
                "?include=manifest,serial,frames,logs,network,qom"
            )
            if evidence:
                (attempt_dir / "evidence.zip").write_bytes(evidence)
                names, manifest, serial, peer_log, pcap = unpack_evidence(
                    evidence
                )
        except (RuntimeError, OSError, ValueError):
            evidence_status = 0
            evidence = b""

    network_checks = network.get("checks")
    network_checks = (
        network_checks if isinstance(network_checks, dict) else {}
    )
    transport = network.get("runtime", {}).get("hci_transport")
    expected_transport = "ESP32 native HCI device + HLI to Bumble"
    hci_health = native_hci_health(qom)
    machine_memory_bytes = qom_memory_bytes(qom)
    evidence_names = {
        "serial.log",
        "frames/current.png",
        "qom/snapshot.json",
        "network/evidence.json",
        "network/capture.pcap",
        "ble-probe.log",
        "manifest.json",
    }
    checks = {
        "api_evidence": evidence_status == 200,
        "frame_png": (
            frame_status == 200
            and frame.startswith(b"\x89PNG\r\n\x1a\n")
            and len(frame) > 1000
        ),
        "wifi_dhcp_http": all(
            network_checks.get(f"serial:{marker}", False)
            for marker in (
                "UNIFIED_CORE2_WIFI_CONNECTED",
                "UNIFIED_CORE2_HTTP_PASS",
            )
        ),
        "public_dns_http": all(
            network_checks.get(f"serial:{marker}", False)
            for marker in (
                "UNIFIED_CORE2_PUBLIC_DNS",
                "UNIFIED_CORE2_PUBLIC_HTTP_PASS",
            )
        ),
        "external_nus_gatt": (
            network.get("status") == "PASS"
            and bool(network_checks)
            and all(network_checks.values())
            and all(
                network_checks.get(f"serial:{marker}", False)
                for marker in (
                    "UNIFIED_CORE2_BLE_RX",
                    "UNIFIED_CORE2_BLE_ACK_SENT",
                )
            )
            and any(key.startswith("peer:") for key in network_checks)
            and all(
                value
                for key, value in network_checks.items()
                if key.startswith("peer:")
            )
        ),
        "native_hci_transport": transport == expected_transport,
        "bounded_tcg_cache": (
            qemu_accelerator == EXPECTED_QEMU_ACCELERATOR
        ),
        "native_hci_health": native_hci_health_ok(hci_health),
        "hold_stable": hold_stable,
        "active_ble_link_during_hold": (
            hold_seconds <= 0
            or hci_health.get("peer-closed") == 0
        ),
        "evidence_zip": evidence_names.issubset(names),
        "pcap_file_in_evidence_zip": len(pcap) > 0,
        "manifest_session_binding": manifest_session_binding_ok(
            manifest,
            session_id,
        ),
    }
    if not qom.get("nodes"):
        checks["api_evidence"] = False

    serial_text = serial.decode("utf-8", errors="replace")
    peer_text = peer_log.decode("utf-8", errors="replace")
    psram = parse_psram_stress(serial_text)
    psram_requirements = sustained_stress_requirements(hold_seconds)
    if require_psram:
        checks["psram_guest_stress"] = psram_stress_ok(psram)
        checks["psram_machine_capacity"] = (
            machine_memory_bytes is not None
            and machine_memory_bytes >= PSRAM_MACHINE_CAPACITY_MIN_BYTES
        )
        checks["psram_sustained_stress"] = sustained_stress_ok(
            psram,
            hold_seconds,
        )
    checks["ble_cycle_count"] = (
        peer_text.count("BLE_BUMBLE_CYCLE_PASS")
        >= ble_reconnect_cycles
        and serial_text.count("UNIFIED_CORE2_BLE_RX")
        >= ble_reconnect_cycles
    )
    observed_markers = [
        marker
        for marker in (
            "UNIFIED_CORE2_BOOT",
            "UNIFIED_CORE2_MAIN",
            "UNIFIED_CORE2_DISPLAY",
            READY_MARKER,
            "UNIFIED_CORE2_WIFI_CONNECTED",
            "UNIFIED_CORE2_HTTP_PASS",
            "UNIFIED_CORE2_PUBLIC_DNS",
            "UNIFIED_CORE2_PUBLIC_HTTP_PASS",
            "UNIFIED_CORE2_BLE_READY",
            "UNIFIED_CORE2_BLE_RX",
            "UNIFIED_CORE2_BLE_ACK_SENT",
            "UNIFIED_CORE2_PSRAM_INIT_PASS",
            "UNIFIED_CORE2_PSRAM_SWEEP",
            "UNIFIED_CORE2_PSRAM_STRESS_PASS",
            "UNIFIED_CORE2_HTTP_RECHECK_PASS",
            "UNIFIED_CORE2_PUBLIC_RECHECK_PASS",
            "UNIFIED_CORE2_STRESS_HEARTBEAT",
        )
        if marker in serial_text
    ]
    panic_events: list[dict[str, str | None]] = []
    panic_blocks = serial_text.split("Guru Meditation Error:")
    for raw_block in panic_blocks[1:]:
        kind_match = re.search(r"panic'ed \(([^)]+)\)", raw_block)
        pc_match = re.search(r"\bPC\s*:\s*(0x[0-9a-fA-F]+)", raw_block)
        exccaue_match = re.search(
            r"\bEXCCAUSE:\s*(0x[0-9a-fA-F]+)",
            raw_block,
        )
        panic_events.append(
            {
                "kind": kind_match.group(1) if kind_match else None,
                "pc": pc_match.group(1).lower() if pc_match else None,
                "exccaue": (
                    exccaue_match.group(1).lower()
                    if exccaue_match
                    else None
                ),
            }
        )
    if panic_events:
        panic_kind = str(panic_events[0].get("kind") or "unknown")
        normalized_kind = re.sub(
            r"(?<!^)(?=[A-Z])",
            "_",
            panic_kind,
        ).lower()
        failure_class = f"panic_{normalized_kind}"
    elif "GATT timeout" in peer_text:
        failure_class = "gatt_timeout"
    elif failure is not None:
        failure_class = "attempt_error"
    elif not all(checks.values()):
        failure_class = "check_failed"
    else:
        failure_class = None

    error_message = (
        f"{type(failure).__name__}: {failure}"
        if failure is not None
        else None
    )
    if session_id and error_message is not None:
        error_message = error_message.replace(session_id, "<session>")

    return {
        "attempt": attempt_dir.name,
        "status": "PASS" if all(checks.values()) else "FAIL",
        "checks": checks,
        "failure_phase": phase if failure is not None else None,
        "failure_class": failure_class,
        "failure_error": error_message,
        "frame_bytes": len(frame),
        "frame_sha256": (
            hashlib.sha256(frame).hexdigest() if frame else None
        ),
        "qom_nodes": len(qom.get("nodes", [])),
        "qom_memory_bytes": machine_memory_bytes,
        "evidence_bytes": len(evidence),
        "serial_sha256": (
            hashlib.sha256(serial).hexdigest() if serial else None
        ),
        "peer_log_sha256": (
            hashlib.sha256(peer_log).hexdigest() if peer_log else None
        ),
        "pcap_bytes": len(pcap),
        "hci_transport": str(transport or ""),
        "native_hci_health": hci_health,
        "psram": psram,
        "psram_requirements": psram_requirements,
        "network_status": str(network.get("status") or "UNAVAILABLE"),
        "hold_state": hold_state,
        "hold_error": hold_error,
        "session_started_epoch": session_started_epoch,
        "session_finished_epoch": session_finished_epoch,
        "qemu_accelerator": qemu_accelerator,
        "hold_resource_samples": {
            "state_polls": state_samples,
            "sample_interval_seconds": 30,
            "rss_kib_start": rss_samples[0] if rss_samples else None,
            "rss_kib_min": min(rss_samples) if rss_samples else None,
            "rss_kib_max": max(rss_samples) if rss_samples else None,
            "rss_kib_end": rss_samples[-1] if rss_samples else None,
            "rss_kib_delta": (
                rss_samples[-1] - rss_samples[0]
                if rss_samples
                else None
            ),
            "rss_kib_samples": rss_samples,
            "phys_footprint_kib_start": (
                phys_footprint_samples[0]
                if phys_footprint_samples
                else None
            ),
            "phys_footprint_kib_min": (
                min(phys_footprint_samples)
                if phys_footprint_samples
                else None
            ),
            "phys_footprint_kib_max": (
                max(phys_footprint_samples)
                if phys_footprint_samples
                else None
            ),
            "phys_footprint_kib_end": (
                phys_footprint_samples[-1]
                if phys_footprint_samples
                else None
            ),
            "phys_footprint_kib_delta": (
                phys_footprint_samples[-1]
                - phys_footprint_samples[0]
                if phys_footprint_samples
                else None
            ),
            "phys_footprint_kib_samples": phys_footprint_samples,
        },
        "failure_diagnostics": {
            "panic_count": len(panic_events),
            "first_panic": panic_events[0] if panic_events else None,
            "last_panic": panic_events[-1] if panic_events else None,
            "observed_serial_markers": observed_markers,
            "peer_gatt_timeout": "GATT timeout" in peer_text,
            "session_read_error": session_read_error,
            "cleanup_error": cleanup_error,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    parser.add_argument("--token")
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--attempts", type=int, default=5)
    parser.add_argument("--concurrency", type=int, default=1)
    parser.add_argument("--stagger-seconds", type=float, default=0)
    parser.add_argument("--hold-seconds", type=float, default=0)
    parser.add_argument("--timeout", type=float, default=180)
    parser.add_argument(
        "--ble-reconnect-cycles",
        type=int,
        default=1,
        help="complete GATT/disconnect cycles required from one BLE peer",
    )
    parser.add_argument(
        "--require-psram",
        action="store_true",
        help=(
            "require the Core2 guest to allocate a 1 MiB external-memory "
            "buffer and complete three read/write sweeps"
        ),
    )
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.attempts < 1 or args.attempts > 30:
        parser.error("--attempts must be from 1 to 30")
    if args.concurrency < 1 or args.concurrency > 4:
        parser.error("--concurrency must be from 1 to 4")
    if not 0 <= args.stagger_seconds <= 120:
        parser.error("--stagger-seconds must be from 0 to 120")
    if args.hold_seconds < 0 or args.hold_seconds > MAX_BLE_HOLD_SECONDS:
        parser.error(
            "--hold-seconds must be from 0 to "
            f"{MAX_BLE_HOLD_SECONDS}"
        )
    if args.require_psram and args.hold_seconds < 8:
        parser.error("--require-psram requires --hold-seconds >= 8")
    if (
        args.ble_reconnect_cycles < 1
        or args.ble_reconnect_cycles > MAX_BLE_RECONNECT_CYCLES
    ):
        parser.error(
            "--ble-reconnect-cycles must be from 1 to "
            f"{MAX_BLE_RECONNECT_CYCLES}"
        )
    for label, path in (
        ("image", args.image),
        ("ELF", args.elf),
        ("QEMU", args.qemu),
    ):
        if not path.is_file():
            parser.error(f"{label} does not exist: {path}")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    reconnect_delay_seconds = 2
    effective_timeout = max(
        args.timeout,
        reconnect_workload_timeout_seconds(
            args.ble_reconnect_cycles,
            reconnect_delay_seconds,
        ),
    )
    input_hashes = freeze_input_hashes(
        args.image,
        args.elf,
        args.qemu,
        TOOL_PATHS,
    )

    api = Api(args.base_url, args.token)
    firmware_artifact = api.upload(args.image)
    elf_artifact = api.upload(args.elf)
    if firmware_artifact != input_hashes["firmware_sha256"]:
        raise SystemExit(
            "firmware artifact hash changed between preflight and upload"
        )
    if elf_artifact != input_hashes["elf_sha256"]:
        raise SystemExit("ELF artifact hash changed between preflight and upload")
    firmware = api.json(
        "/api/v1/firmware",
        payload={
            "device_id": "core2",
            "kind": "merged",
            "artifact_id": firmware_artifact,
        },
    )
    runs = []
    batches = attempt_batches(args.attempts, args.concurrency)
    for batch in batches:
        with ThreadPoolExecutor(max_workers=len(batch)) as executor:
            futures = {
                attempt: executor.submit(
                    run_attempt,
                    api,
                    str(firmware["firmware_id"]),
                    elf_artifact,
                    args.out_dir / f"attempt-{attempt}",
                    effective_timeout,
                    args.hold_seconds,
                    args.ble_reconnect_cycles,
                    args.require_psram,
                    args.stagger_seconds * batch.index(attempt),
                )
                for attempt in batch
            }
            batch_results = {
                attempt: futures[attempt].result()
                for attempt in batch
            }
        runs.extend(batch_results[attempt] for attempt in batch)
        if any(result["status"] != "PASS" for result in runs):
            break
    attempts_passed = sum(run["status"] == "PASS" for run in runs)
    failed_runs = [run for run in runs if run["status"] != "PASS"]
    all_checks_passed = all(all(run["checks"].values()) for run in runs)
    post_run_hashes = freeze_input_hashes(
        args.image,
        args.elf,
        args.qemu,
        TOOL_PATHS,
    )
    input_assets_unchanged = post_run_hashes == input_hashes
    session_intervals = [
        (
            float(run["session_started_epoch"]),
            float(run["session_finished_epoch"]),
        )
        for run in runs
        if isinstance(run.get("session_started_epoch"), (int, float))
        and isinstance(run.get("session_finished_epoch"), (int, float))
    ]
    maximum_concurrent_sessions = maximum_interval_overlap(
        session_intervals
    )
    required_overlap = min(args.concurrency, args.attempts)
    concurrency_observed = maximum_concurrent_sessions >= required_overlap
    input_asset_drift = {
        key: {
            "before": input_hashes[key],
            "after": post_run_hashes[key],
        }
        for key in input_hashes
        if post_run_hashes[key] != input_hashes[key]
    }
    frame_hashes = {run["frame_sha256"] for run in runs}
    qom_node_counts = {run["qom_nodes"] for run in runs}
    checks_per_attempt = {
        name: (
            "PASS"
            if all(run["checks"].get(name, False) for run in runs)
            else "FAIL"
        )
        for name in sorted(runs[0]["checks"])
    } if runs else {}
    if runs:
        transport_pass = checks_per_attempt.pop("native_hci_transport")
        checks_per_attempt["hci_transport"] = (
            runs[0]["hci_transport"] if transport_pass == "PASS" else "FAIL"
        )
    checks_per_attempt.update(
        {
            "frame_sha256": (
                next(iter(frame_hashes))
                if len(frame_hashes) == 1
                else "MISMATCH"
            ),
            "qom_nodes": (
                next(iter(qom_node_counts))
                if len(qom_node_counts) == 1
                else "MISMATCH"
            ),
        }
    )
    status = (
        "PASS"
        if len(runs) == args.attempts
        and attempts_passed == args.attempts
        and all_checks_passed
        and input_assets_unchanged
        and concurrency_observed
        else "FAIL"
    )
    evidence = {
        "schema_version": 1,
        "kind": "m5stack-core2-native-hci-service-attempts",
        "stage": "HCI-4",
        "gate_result": status,
        "status": status,
        "validation": "virtual-device validation",
        "profile": PROFILE,
        "runtime": "qemu-unified",
        "service_api": "/api/v1",
        "firmware": {
            "sha256": input_hashes["firmware_sha256"],
            "bytes": input_hashes["firmware_bytes"],
        },
        "elf_sha256": input_hashes["elf_sha256"],
        "qemu_sha256": input_hashes["qemu_sha256"],
        "tool_hashes": {
            name: input_hashes[f"{name}_sha256"]
            for name in TOOL_PATHS
        },
        "input_hash_bound_at": "before_first_lease",
        "input_assets_unchanged_during_run": input_assets_unchanged,
        "input_asset_drift": input_asset_drift,
        "attempts_requested": args.attempts,
        "attempts_completed": len(runs),
        "attempts_passed": attempts_passed,
        "attempts_failed": len(failed_runs),
        "concurrency_requested": args.concurrency,
        "maximum_concurrent_sessions": maximum_concurrent_sessions,
        "concurrency_observed": concurrency_observed,
        "attempt_batches": batches,
        "stagger_seconds": args.stagger_seconds,
        "hold_seconds_per_attempt": args.hold_seconds,
        "ble_linger_seconds": max(20, args.hold_seconds + 60),
        "ble_reconnect_cycles": args.ble_reconnect_cycles,
        "psram_required": args.require_psram,
        "psram_gate": "NOT RUN",
        "ready_timeout_seconds_requested": args.timeout,
        "ready_timeout_seconds_effective": effective_timeout,
        "first_failure": (
            {
                key: failed_runs[0].get(key)
                for key in (
                    "attempt",
                    "failure_phase",
                    "failure_class",
                    "failure_error",
                    "network_status",
                    "hold_state",
                    "failure_diagnostics",
                )
            }
            if failed_runs
            else None
        ),
        "checks_per_attempt": checks_per_attempt,
        "runs": [
            {
                key: value
                for key, value in run.items()
                if key not in {"checks", "hci_transport"}
            }
            for run in runs
        ],
        "boundary": {
            "isolation": "trusted-host",
            "gdb_bridge": False,
            "session_reuse": (
                f"up to {args.attempts} independent leases and QEMU "
                f"processes with concurrency {args.concurrency}"
            ),
            "pcap": (
                "captured in each evidence ZIP; packet summaries are "
                "finalized during stop/retention handling"
            ),
            "not_claimed": [
                "bit-exact Espressif BT controller/baseband",
                "physical 8 MiB PSRAM capacity",
                "physical cache/PSRAM timing",
                "physical hardware or RF validation",
                "malware sandboxing",
            ],
        },
    }
    if args.require_psram:
        evidence["psram_gate"] = "PASS" if status == "PASS" else "FAIL"
    output = args.out_dir / "evidence.json"
    output.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))
    print(f"evidence={output}")
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

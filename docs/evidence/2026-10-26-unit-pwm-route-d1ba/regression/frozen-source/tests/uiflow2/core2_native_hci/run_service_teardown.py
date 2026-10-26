#!/usr/bin/env python3
"""Stop active Core2 BLE sessions and prove clean consecutive recovery."""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
THIS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "platform/tools"))
sys.path.insert(0, str(THIS_DIR))

import run_service_5x as common  # noqa: E402
from ble_runtime_limits import reconnect_workload_timeout_seconds  # noqa: E402

READY_MARKER = "UNIFIED_CORE2_READY"
TOOL_PATHS = {
    **common.TOOL_PATHS,
    "teardown_runner": Path(__file__).resolve(),
}


def process_running(pid: object) -> bool:
    if not isinstance(pid, int) or isinstance(pid, bool) or pid <= 0:
        return False
    try:
        result = subprocess_result = common.subprocess.run(
            ["ps", "-o", "pid=", "-p", str(pid)],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        )
    except (OSError, common.subprocess.SubprocessError):
        return False
    return bool(
        subprocess_result.returncode == 0
        and result.stdout.strip().isdigit()
    )


def wait_until_absent(pid: object, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not process_running(pid):
            return True
        time.sleep(0.05)
    return not process_running(pid)


def network_contract_pass(network: dict[str, Any]) -> bool:
    checks = network.get("checks")
    checks = checks if isinstance(checks, dict) else {}
    required_markers = (
        "UNIFIED_CORE2_WIFI_CONNECTED",
        "UNIFIED_CORE2_HTTP_PASS",
        "UNIFIED_CORE2_PUBLIC_DNS",
        "UNIFIED_CORE2_PUBLIC_HTTP_PASS",
        "UNIFIED_CORE2_BLE_RX",
        "UNIFIED_CORE2_BLE_ACK_SENT",
    )
    peer_checks = [
        value for key, value in checks.items() if key.startswith("peer:")
    ]
    return bool(
        network.get("status") == "PASS"
        and checks
        and all(checks.values())
        and all(checks.get(f"serial:{marker}", False) for marker in required_markers)
        and peer_checks
        and all(peer_checks)
    )


def companion_state(session: dict[str, Any], name: str) -> str:
    companions = session.get("companions")
    if not isinstance(companions, dict):
        return "missing"
    companion = companions.get(name)
    if not isinstance(companion, dict):
        return "missing"
    return str(companion.get("state") or "missing")


def companion_pid(session: dict[str, Any], name: str) -> int | None:
    companions = session.get("companions")
    if not isinstance(companions, dict):
        return None
    companion = companions.get(name)
    if not isinstance(companion, dict):
        return None
    pid = companion.get("pid")
    return pid if isinstance(pid, int) and not isinstance(pid, bool) else None


def run_attempt(
    api: common.Api,
    firmware_id: str,
    elf_artifact_id: str,
    attempt_dir: Path,
    timeout: float,
    linger_seconds: int,
) -> dict[str, Any]:
    attempt_dir.mkdir(parents=True, exist_ok=True)
    session_id: str | None = None
    failure: Exception | None = None
    phase = "create_session"
    pre_session: dict[str, Any] = {}
    final_session: dict[str, Any] = {}
    stop_result: dict[str, Any] = {}
    worker_after: dict[str, Any] = {}
    network: dict[str, Any] = {}
    qom: dict[str, Any] = {}
    evidence = b""
    names: set[str] = set()
    manifest: dict[str, Any] = {}
    serial = b""
    peer_log = b""
    pcap = b""
    frame = b""
    frame_status = 0
    evidence_status = 0
    stop_seconds: float | None = None
    qemu_pid: int | None = None
    ble_pid: int | None = None

    try:
        session = api.json(
            "/api/v1/sessions",
            payload={
                "device_id": "core2",
                "runtime": "qemu-unified",
                "firmware_id": firmware_id,
                "ready_timeout_seconds": timeout,
                "network": {
                    "profile": common.PROFILE,
                    "elf_artifact_id": elf_artifact_id,
                    "attempts": 1,
                    "capture_pcap": True,
                    "ble_linger_seconds": linger_seconds,
                    "ble_reconnect_cycles": 1,
                    "ble_reconnect_delay_seconds": 2,
                },
            },
        )
        session_id = str(session["session_id"])
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
        common.wait_for_running(api, session_id, timeout)
        phase = "wait_network"
        network = common.wait_for_network(api, session_id, timeout)
        phase = "capture_pre_stop"
        pre_session = api.json(f"/api/v1/sessions/{session_id}")
        qemu_pid = (
            pre_session.get("pid")
            if isinstance(pre_session.get("pid"), int)
            else None
        )
        ble_pid = companion_pid(pre_session, "ble_probe")
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
        phase = "active_stop"
        started = time.monotonic()
        stop_result = api.json(
            f"/api/v1/sessions/{session_id}?purge=0&retain_flash=0",
            payload={},
            method="DELETE",
            timeout=60,
        )
        stop_seconds = round(time.monotonic() - started, 3)
        phase = "verify_absence"
        qemu_absent = wait_until_absent(qemu_pid)
        ble_absent = wait_until_absent(ble_pid)
        final_session = api.json(f"/api/v1/sessions/{session_id}")
        worker_after = api.json("/api/v1/worker")
    except Exception as error:  # noqa: BLE001 - preserve every failure.
        failure = error
        qemu_absent = False
        ble_absent = False

    if evidence:
        (attempt_dir / "pre-stop-evidence.zip").write_bytes(evidence)
        names, manifest, serial, peer_log, pcap = common.unpack_evidence(
            evidence
        )
    if frame:
        (attempt_dir / "pre-stop-frame.png").write_bytes(frame)
    if qom:
        (attempt_dir / "pre-stop-qom.json").write_text(
            json.dumps(qom, indent=2) + "\n"
        )
    if pre_session:
        (attempt_dir / "pre-stop-session.json").write_text(
            json.dumps(pre_session, indent=2) + "\n"
        )
    if final_session:
        (attempt_dir / "final-session.json").write_text(
            json.dumps(final_session, indent=2) + "\n"
        )

    network_checks = network.get("checks")
    network_checks = (
        network_checks if isinstance(network_checks, dict) else {}
    )
    hci_health = common.native_hci_health(qom)
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
        "pre_stop_session_running": pre_session.get("state") == "running",
        "pre_stop_ble_companion_running": (
            companion_state(pre_session, "ble_probe") == "running"
            and isinstance(ble_pid, int)
        ),
        "pre_stop_http_companion_running": (
            companion_state(pre_session, "http_fixture") == "running"
        ),
        "pre_stop_network_pass": network_contract_pass(network),
        "pre_stop_public_dns_http": all(
            network_checks.get(f"serial:{marker}", False)
            for marker in (
                "UNIFIED_CORE2_PUBLIC_DNS",
                "UNIFIED_CORE2_PUBLIC_HTTP_PASS",
            )
        ),
        "pre_stop_external_nus_gatt": network_contract_pass(network),
        "pre_stop_native_hci_health": common.native_hci_health_ok(hci_health),
        "pre_stop_peer_open": hci_health.get("peer-closed") == 0,
        "frame_png": (
            frame_status == 200
            and frame.startswith(b"\x89PNG\r\n\x1a\n")
            and len(frame) > 1000
        ),
        "evidence_zip": evidence_names.issubset(names),
        "pcap_file_in_evidence_zip": len(pcap) > 0,
        "manifest_session_binding": (
            manifest.get("session", {}).get("session_id") == session_id
        ),
        "stop_final_state": final_session.get("state") == "stopped",
        "stop_had_no_error": final_session.get("error") is None,
        "stop_http_companion_terminated": (
            companion_state(final_session, "http_fixture") == "terminated"
        ),
        "stop_ble_companion_terminated": (
            companion_state(final_session, "ble_probe") == "terminated"
        ),
        "qemu_process_reaped": qemu_absent,
        "ble_peer_process_reaped": ble_absent,
        "worker_lease_released": (
            worker_after.get("active_lease_count") == 0
        ),
        "api_evidence": evidence_status == 200,
    }
    if not qom.get("nodes"):
        checks["api_evidence"] = False

    serial_text = serial.decode("utf-8", errors="replace")
    peer_text = peer_log.decode("utf-8", errors="replace")
    checks["ble_cycle_count"] = (
        peer_text.count("BLE_BUMBLE_CYCLE_PASS") >= 1
        and serial_text.count("UNIFIED_CORE2_BLE_RX") >= 1
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
        )
        if marker in serial_text
    ]
    status = "PASS" if all(checks.values()) and failure is None else "FAIL"
    error_message = (
        f"{type(failure).__name__}: {failure}"
        if failure is not None
        else None
    )
    if error_message is not None and session_id:
        error_message = error_message.replace(session_id, "<session>")
    return {
        "attempt": attempt_dir.name,
        "status": status,
        "checks": checks,
        "failure_phase": phase if failure is not None else None,
        "failure_error": error_message,
        "session_id": session_id,
        "qemu_pid_before_stop": qemu_pid,
        "ble_pid_before_stop": ble_pid,
        "stop_seconds": stop_seconds,
        "stop_result_state": stop_result.get("state"),
        "final_session": {
            "state": final_session.get("state"),
            "error": final_session.get("error"),
            "completed_at": final_session.get("completed_at"),
            "worker": final_session.get("worker"),
            "companions": final_session.get("companions"),
        },
        "worker_after": worker_after,
        "frame_bytes": len(frame),
        "frame_sha256": hashlib.sha256(frame).hexdigest() if frame else None,
        "qom_nodes": len(qom.get("nodes", [])),
        "evidence_bytes": len(evidence),
        "serial_sha256": hashlib.sha256(serial).hexdigest() if serial else None,
        "peer_log_sha256": (
            hashlib.sha256(peer_log).hexdigest() if peer_log else None
        ),
        "pcap_bytes": len(pcap),
        "network_status": str(network.get("status") or "UNAVAILABLE"),
        "native_hci_health": hci_health,
        "observed_serial_markers": observed_markers,
        "peer_gatt_timeout": "GATT timeout" in peer_text,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    parser.add_argument("--token")
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument("--qemu", type=Path, required=True)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=300)
    parser.add_argument("--linger-seconds", type=int, default=120)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.attempts < 1 or args.attempts > 5:
        parser.error("--attempts must be from 1 to 5")
    if args.linger_seconds < 20:
        parser.error("--linger-seconds must be at least 20")
    for label, path in (
        ("image", args.image),
        ("ELF", args.elf),
        ("QEMU", args.qemu),
    ):
        if not path.is_file():
            parser.error(f"{label} does not exist: {path}")
    effective_timeout = max(
        args.timeout,
        reconnect_workload_timeout_seconds(1, 2),
    )
    input_hashes = common.freeze_input_hashes(
        args.image,
        args.elf,
        args.qemu,
        TOOL_PATHS,
    )
    api = common.Api(args.base_url, args.token)
    firmware_artifact = api.upload(args.image)
    elf_artifact = api.upload(args.elf)
    if firmware_artifact != input_hashes["firmware_sha256"]:
        raise SystemExit("firmware artifact hash changed during upload")
    if elf_artifact != input_hashes["elf_sha256"]:
        raise SystemExit("ELF artifact hash changed during upload")
    firmware = api.json(
        "/api/v1/firmware",
        payload={
            "device_id": "core2",
            "kind": "merged",
            "artifact_id": firmware_artifact,
        },
    )

    runs = []
    for attempt in range(1, args.attempts + 1):
        run = run_attempt(
            api,
            str(firmware["firmware_id"]),
            elf_artifact,
            args.out_dir / f"attempt-{attempt}",
            effective_timeout,
            args.linger_seconds,
        )
        runs.append(run)
        if run["status"] != "PASS":
            break

    post_hashes = common.freeze_input_hashes(
        args.image,
        args.elf,
        args.qemu,
        TOOL_PATHS,
    )
    drift = {
        key: {"before": input_hashes[key], "after": post_hashes[key]}
        for key in input_hashes
        if post_hashes[key] != input_hashes[key]
    }
    passed = sum(run["status"] == "PASS" for run in runs)
    status = (
        "PASS"
        if len(runs) == args.attempts
        and passed == args.attempts
        and not drift
        else "FAIL"
    )
    checks_per_attempt = {
        name: (
            "PASS"
            if all(run["checks"].get(name, False) for run in runs)
            else "FAIL"
        )
        for name in sorted(runs[0]["checks"])
    } if runs else {}
    evidence = {
        "schema_version": 1,
        "kind": "m5stack-core2-native-hci-active-stop-recovery",
        "date": "2026-10-25",
        "stage": "CORE2-02",
        "gate_result": status,
        "status": status,
        "validation": "virtual-device validation",
        "profile": common.PROFILE,
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
        "input_assets_unchanged_during_run": not drift,
        "input_asset_drift": drift,
        "attempts_requested": args.attempts,
        "attempts_completed": len(runs),
        "attempts_passed": passed,
        "attempts_failed": len(runs) - passed,
        "ble_linger_seconds": args.linger_seconds,
        "ready_timeout_seconds_effective": effective_timeout,
        "checks_per_attempt": checks_per_attempt,
        "runs": runs,
        "boundary": {
            "isolation": "trusted-host",
            "gdb_bridge": False,
            "lifecycle": (
                "Each attempt deletes an already-ready session while its BLE "
                "peer is still inside the requested linger window; the next "
                "attempt creates a new session and QEMU process."
            ),
            "not_claimed": [
                "bit-exact Espressif BT controller/baseband",
                "physical cache/PSRAM timing",
                "physical hardware or RF validation",
                "cross-host QEMU migration",
                "malware sandboxing",
            ],
        },
    }
    output = args.out_dir / "evidence.json"
    output.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))
    print(f"evidence={output}")
    return 0 if status == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

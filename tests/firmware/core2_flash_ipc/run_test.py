#!/usr/bin/env python3
"""Exercise the Core2 flash/IPC timer and interrupt-watchdog diagnostic."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

SPINLOCK_ASSERT = (
    "assert failed: spinlock_release spinlock.h:190 "
    "(core_owner_id == lock->owner)"
)
EXPECTED_IMAGE_SHA256 = (
    "c2762e5f34d513e34a47739174fd452567f2f3ec87164a4d421a1a7141c68359"
)
EXPECTED_ELF_SHA256 = (
    "7636c3e5aa182621f9998e12938a2e037adf99689f7d1b7e5c154a7892aaf88b"
)
READY_PATTERN = re.compile(
    r"(?m)^CORE2_FLASH_IPC_READY core=([01]) "
    r"prid=0x([0-9a-fA-F]{8})\s*$"
)
MAIN_PATTERN = re.compile(
    r"(?m)^CORE2_FLASH_IPC_MAIN core=([01]) "
    r"prid=0x([0-9a-fA-F]{8})\s*$"
)
BACKTRACE_PATTERN = re.compile(
    r"(?m)^Backtrace: ([0-9a-fA-Fx: ]+)\r?$"
)


class Api:
    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def request(
        self,
        path: str,
        *,
        method: str = "GET",
        data: bytes | None = None,
        content_type: str | None = None,
        timeout: float = 60,
    ) -> tuple[int, bytes, str]:
        headers: dict[str, str] = {}
        if content_type is not None:
            headers["Content-Type"] = content_type
        request = urllib.request.Request(
            self.base_url + path,
            data=data,
            method=method,
            headers=headers,
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return (
                    response.status,
                    response.read(),
                    response.headers.get("Content-Type", ""),
                )
        except urllib.error.HTTPError as error:
            detail = error.read().decode(errors="replace")[:2000]
            raise RuntimeError(
                f"{path} returned HTTP {error.code}: {detail}"
            ) from error

    def json(
        self,
        path: str,
        *,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
        timeout: float = 60,
    ) -> Any:
        data = None
        content_type = None
        if payload is not None:
            data = json.dumps(payload).encode()
            content_type = "application/json"
        status, body, _ = self.request(
            path,
            method=method,
            data=data,
            content_type=content_type,
            timeout=timeout,
        )
        if status not in {200, 201, 202}:
            raise RuntimeError(f"{path} returned HTTP {status}")
        return json.loads(body)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_artifact_hashes(
    image_sha256: str,
    elf_sha256: str,
    *,
    expected_image_sha256: str,
    expected_elf_sha256: str,
) -> None:
    for label, actual, expected in (
        ("image", image_sha256.lower(), expected_image_sha256.lower()),
        ("ELF", elf_sha256.lower(), expected_elf_sha256.lower()),
    ):
        if not re.fullmatch(r"[0-9a-f]{64}", expected):
            raise ValueError(f"expected {label} SHA256 is not a 64-digit hex digest")
        if actual != expected:
            raise ValueError(
                f"{label} SHA256 mismatch: expected {expected}, got {actual}; "
                "pass an explicit matching hash only when intentionally "
                "rebuilding the probe"
            )


def first_boot_serial(serial: str) -> str:
    reboot = re.search(r"(?m)^Rebooting\.\.\.\s*$", serial)
    return serial[: reboot.start()] if reboot else serial


def classify_serial(serial: str) -> dict[str, Any]:
    first_boot = first_boot_serial(serial)
    ready = READY_PATTERN.search(first_boot)
    main = MAIN_PATTERN.search(first_boot)
    backtrace = BACKTRACE_PATTERN.search(first_boot)
    spinlock_assert = SPINLOCK_ASSERT in first_boot
    read_started = "CORE2_FLASH_IPC_READ_START" in first_boot
    progress_count = first_boot.count("CORE2_FLASH_IPC_PROGRESS")
    worker_pass_count = first_boot.count("CORE2_FLASH_IPC_WORKER_PASS")
    complete_pass_count = len(
        re.findall(r"(?m)^CORE2_FLASH_IPC_PASS\s*$", first_boot)
    )
    interrupt_wdt = "Interrupt wdt timeout" in first_boot
    reboot_observed = first_boot != serial

    if complete_pass_count == 1 and worker_pass_count == 1:
        status = "PASS"
    elif ready and spinlock_assert and not read_started:
        status = "REPRODUCED"
    elif spinlock_assert:
        status = "REPRODUCED_AFTER_READ_START"
    elif interrupt_wdt:
        status = "INTERRUPT_WDT"
    elif read_started:
        status = "INCOMPLETE"
    else:
        status = "OTHER_FAIL"

    return {
        "status": status,
        "main_core": int(main.group(1)) if main else None,
        "main_prid": f"0x{main.group(2).lower()}" if main else None,
        "worker_core": int(ready.group(1)) if ready else None,
        "worker_prid": f"0x{ready.group(2).lower()}" if ready else None,
        "spinlock_owner_assert": spinlock_assert,
        "flash_read_started": read_started,
        "progress_markers": progress_count,
        "worker_pass_markers": worker_pass_count,
        "complete_pass_markers": complete_pass_count,
        "interrupt_wdt_in_first_boot": interrupt_wdt,
        "reboot_observed": reboot_observed,
        "backtrace": backtrace.group(1) if backtrace else None,
    }


def wait_and_collect(
    api: Api,
    session_id: str,
    *,
    timeout: float,
    observe_seconds: float,
) -> tuple[dict[str, Any], str]:
    deadline = time.monotonic() + timeout
    running: dict[str, Any] = {}
    while time.monotonic() < deadline:
        running = api.json(f"/api/v1/sessions/{session_id}")
        if running.get("state") == "running":
            break
        if running.get("state") in {"failed", "stopped"}:
            break
        time.sleep(0.25)
    else:
        raise RuntimeError("session did not become observable before timeout")

    observe_deadline = time.monotonic() + observe_seconds
    serial = ""
    while time.monotonic() < observe_deadline:
        payload = api.json(
            f"/api/v1/sessions/{session_id}/serial?offset=0&limit=65536"
        )
        serial = str(payload.get("data") or "")
        if SPINLOCK_ASSERT in serial or "CORE2_FLASH_IPC_PASS" in serial:
            break
        time.sleep(0.25)
    return running, serial


def run_attempt(
    api: Api,
    firmware_id: str,
    attempt_dir: Path,
    *,
    timeout: float,
    observe_seconds: float,
) -> dict[str, Any]:
    attempt_dir.mkdir(parents=True, exist_ok=True)
    session_id = ""
    try:
        created = api.json(
            "/api/v1/sessions",
            method="POST",
            payload={
                "device_id": "core2",
                "firmware_id": firmware_id,
                "runtime": "qemu",
                "ttl_seconds": 120,
            },
        )
        session_id = str(created["session_id"])
        observed, serial = wait_and_collect(
            api,
            session_id,
            timeout=timeout,
            observe_seconds=observe_seconds,
        )
        (attempt_dir / "serial.log").write_text(serial)

        status, evidence, _ = api.request(
            f"/api/v1/sessions/{session_id}/evidence"
            "?include=manifest,serial,logs",
            timeout=timeout,
        )
        if evidence:
            (attempt_dir / "evidence.zip").write_bytes(evidence)

        classification = classify_serial(serial)
        classification.update(
            {
                "session_id_sha256": hashlib.sha256(
                    session_id.encode()
                ).hexdigest(),
                "session_state": observed.get("state"),
                "serial_sha256": hashlib.sha256(serial.encode()).hexdigest(),
                "evidence_zip": (
                    status == 200 and evidence.startswith(b"PK\x03\x04")
                ),
            }
        )
        return classification
    finally:
        if session_id:
            api.json(
                f"/api/v1/sessions/{session_id}?purge=0",
                method="DELETE",
                payload={},
            )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8787")
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--elf", type=Path, required=True)
    parser.add_argument(
        "--expected-image-sha256",
        default=EXPECTED_IMAGE_SHA256,
        help="fail closed unless the probe image has this SHA256",
    )
    parser.add_argument(
        "--expected-elf-sha256",
        default=EXPECTED_ELF_SHA256,
        help="fail closed unless the probe ELF has this SHA256",
    )
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--observe-seconds", type=float, default=15)
    parser.add_argument("--out-dir", type=Path, required=True)
    args = parser.parse_args()
    if args.attempts < 1 or args.attempts > 10:
        parser.error("--attempts must be from 1 to 10")
    if not args.image.is_file():
        parser.error(f"--image does not exist: {args.image}")
    if not args.elf.is_file():
        parser.error(f"--elf does not exist: {args.elf}")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    image_sha256 = sha256(args.image)
    elf_sha256 = sha256(args.elf)
    try:
        validate_artifact_hashes(
            image_sha256,
            elf_sha256,
            expected_image_sha256=args.expected_image_sha256,
            expected_elf_sha256=args.expected_elf_sha256,
        )
    except ValueError as error:
        parser.error(str(error))
    api = Api(args.base_url)
    status, body, _ = api.request(
        "/api/v1/artifacts",
        method="POST",
        data=args.image.read_bytes(),
        content_type="application/octet-stream",
        timeout=120,
    )
    artifact = json.loads(body)
    if status != 201 or artifact.get("sha256") != image_sha256:
        raise SystemExit("artifact upload did not preserve the image hash")
    firmware = api.json(
        "/api/v1/firmware",
        method="POST",
        payload={
            "device_id": "core2",
            "kind": "merged",
            "artifact_id": artifact["artifact_id"],
        },
    )

    runs = [
        run_attempt(
            api,
            str(firmware["firmware_id"]),
            args.out_dir / f"attempt-{attempt}",
            timeout=args.timeout,
            observe_seconds=args.observe_seconds,
        )
        for attempt in range(1, args.attempts + 1)
    ]
    reproduced = sum(run["status"] == "REPRODUCED" for run in runs)
    passed = sum(run["status"] == "PASS" for run in runs)
    interrupt_wdt = sum(run["status"] == "INTERRUPT_WDT" for run in runs)
    incomplete = sum(run["status"] == "INCOMPLETE" for run in runs)
    if passed == args.attempts:
        result_status = "PASS"
    elif reproduced == args.attempts:
        result_status = "REPRODUCED"
    elif incomplete:
        result_status = "INCOMPLETE"
    else:
        result_status = "MIXED"
    evidence = {
        "schema_version": 1,
        "kind": "m5stack-core2-flash-ipc-diagnostic",
        "validation": "virtual-device validation",
        "status": result_status,
        "classification": (
            "flash_partition_read_data_plane"
            if result_status == "PASS"
            else "runtime_model_gap_candidate"
        ),
        "firmware_sha256": image_sha256,
        "firmware_bytes": args.image.stat().st_size,
        "elf_sha256": elf_sha256,
        "artifact_hash_gate": "PASS",
        "expected_firmware_sha256": args.expected_image_sha256.lower(),
        "expected_elf_sha256": args.expected_elf_sha256.lower(),
        "attempts_requested": args.attempts,
        "attempts_passed": passed,
        "attempts_reproduced": reproduced,
        "attempts_interrupt_wdt": interrupt_wdt,
        "attempts_incomplete": incomplete,
        "runs": runs,
        "expected_success": "CORE2_FLASH_IPC_PASS",
        "failure_markers": [
            SPINLOCK_ASSERT,
            "Interrupt wdt timeout",
        ],
        "boundary": {
            "guest_path": (
                "ESP-IDF 5.5.4 FreeRTOS task on CPU1; CPU0 waits for the "
                "worker while CPU1 performs 1000 4 KiB esp_partition_read "
                "calls using a static buffer"
            ),
            "proven": [
                f"{passed}/{args.attempts} first boots completed all flash reads",
                f"{interrupt_wdt}/{args.attempts} first boots ended in interrupt-WDT",
                "the fixed probe produced no spinlock owner assertion",
            ],
            "not_proven": [
                "whether the same failure explains legacy UIFlow",
                "physical hardware behavior",
            ],
        },
    }
    evidence_path = args.out_dir / "evidence.json"
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))
    print(f"evidence={evidence_path}")
    return 0 if evidence["status"] == "PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())

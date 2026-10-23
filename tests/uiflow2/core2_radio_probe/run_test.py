#!/usr/bin/env python3
"""Run stock UIFlow2 Core2 WiFi or BLE paths in QEMU for baseline evidence."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import shutil
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROBE_ROOT = Path(__file__).resolve().parent
BASE = ROOT / "platform/.cache/firmware/core2/uiflow2.bin"
PROFILE_RUNNER = ROOT / "tests/uiflow2/run_profile_ui_test.py"
QEMU = ROOT / ".work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa"
ROM_DIR = ROOT / ".work/M5StopWatch-QEMU/build/qemu/pc-bios"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def display_path(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def build_image(probe_dir: Path, out_dir: Path) -> Path:
    command = [
        "python3",
        str(PROFILE_RUNNER),
        "--base",
        str(BASE),
        "--machine",
        "m5core2",
        "--files-dir",
        str(probe_dir),
        "--vfs-offset",
        "0x820000",
        "--vfs-size",
        "0x7DF000",
        "--flash-size",
        "0x1000000",
        "--expected-size",
        "320x240",
        "--efuse-driver",
        "none",
        "--memory",
        "0",
        "--out-dir",
        str(out_dir),
        "--build-only",
    ]
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(ROOT / ".work/py"), env.get("PYTHONPATH", "")])
    )
    subprocess.run(command, cwd=ROOT, env=env, check=True, timeout=60)
    image = out_dir / "uiflow2-ui-test.bin"
    if not image.is_file():
        raise RuntimeError(f"image build did not create {image}")
    return image


def run_qemu(
    qemu: Path,
    rom_dir: Path,
    image: Path,
    out_dir: Path,
    timeout: float,
    terminal_marker: str,
) -> tuple[int, str, str]:
    serial_path = out_dir / "serial.log"
    serial_path.unlink(missing_ok=True)
    command = [
        str(qemu),
        "-snapshot",
        "-accel",
        "tcg,thread=single",
        "-icount",
        "shift=auto,align=off,sleep=off",
        "-m",
        "0",
        "-M",
        "m5core2",
        "-drive",
        f"file={image},if=mtd,format=raw",
        "-L",
        str(rom_dir),
        "-display",
        "none",
        "-serial",
        f"file:{serial_path}",
        "-no-reboot",
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    deadline = time.time() + timeout
    try:
        while time.time() < deadline:
            serial = serial_path.read_text(errors="replace") if serial_path.exists() else ""
            if terminal_marker in serial:
                break
            if process.poll() is not None:
                break
            time.sleep(0.1)
    finally:
        if process.poll() is None:
            process.send_signal(signal.SIGTERM)
            try:
                process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=3)
    stderr = process.stderr.read() if process.stderr else ""
    serial = serial_path.read_text(errors="replace") if serial_path.exists() else ""
    return process.returncode or 0, serial, stderr


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--probe", choices=("wifi", "ble"), default="wifi")
    parser.add_argument("--out-dir", type=Path, default=Path("/tmp/core2-radio-probe"))
    parser.add_argument("--timeout", type=float, default=30)
    parser.add_argument("--attempts", type=int, default=3)
    parser.add_argument("--skip-build", action="store_true")
    parser.add_argument("--qemu", type=Path, default=QEMU)
    parser.add_argument("--rom-dir", type=Path, default=ROM_DIR)
    parser.add_argument("--retry-after-main-failure", action="store_true")
    args = parser.parse_args()
    for label, path in (("QEMU", args.qemu), ("ROM directory", args.rom_dir)):
        if not path.exists():
            parser.error(f"{label} does not exist: {path}")
    args.out_dir.mkdir(parents=True, exist_ok=True)
    probe_dir = PROBE_ROOT / args.probe
    prefix = "WIFI" if args.probe == "wifi" else "BLE"
    terminal_marker = f"CORE2_{prefix}_RESULT:"

    built_image = (
        args.out_dir / "uiflow2-ui-test.bin"
        if args.skip_build
        else build_image(probe_dir, args.out_dir)
    )
    image = args.out_dir / "firmware-under-test.bin"
    shutil.copyfile(built_image, image)
    firmware_sha256 = sha256(image)
    attempts = []
    selected = None
    for attempt_index in range(1, args.attempts + 1):
        attempt_dir = args.out_dir / f"attempt-{attempt_index}"
        attempt_dir.mkdir(parents=True, exist_ok=True)
        attempt_image = attempt_dir / "firmware-under-test.bin"
        shutil.copyfile(image, attempt_image)
        attempt_input_sha256 = sha256(attempt_image)
        qemu_exit, serial, qemu_stderr = run_qemu(
            args.qemu,
            args.rom_dir,
            attempt_image,
            attempt_dir,
            args.timeout,
            terminal_marker,
        )
        serial_path = attempt_dir / "serial.log"
        reached_main = f"CORE2_{prefix}_MAIN_START" in serial
        attempt_passed = (
            f"CORE2_{prefix}_ACTIVE True" in serial
            and f"CORE2_{prefix}_RESULT: PASSED" in serial
        )
        attempts.append(
            {
                "attempt": attempt_index,
                "status": "PASS" if attempt_passed else "FAIL",
                "reached_main": reached_main,
                "serial_path": str(serial_path),
                "serial_bytes": serial_path.stat().st_size,
                "serial_sha256": sha256(serial_path),
                "firmware_sha256_before": attempt_input_sha256,
                "firmware_sha256_after": sha256(attempt_image),
                "qemu_exit_code": qemu_exit,
                "qemu_stderr": qemu_stderr[-2000:],
            }
        )
        retry_after_main = (
            args.retry_after_main_failure
            and reached_main
            and not attempt_passed
        )
        if reached_main and not retry_after_main:
            selected = (attempt_dir, qemu_exit, serial, qemu_stderr)
            break
    if selected is None:
        attempt_dir = args.out_dir / f"attempt-{len(attempts)}"
        serial_path = attempt_dir / "serial.log"
        selected = (
            attempt_dir,
            attempts[-1]["qemu_exit_code"],
            serial_path.read_text(errors="replace"),
            attempts[-1]["qemu_stderr"],
        )
    selected_dir, qemu_exit, serial, qemu_stderr = selected
    passed = (
        f"CORE2_{prefix}_ACTIVE True" in serial
        and f"CORE2_{prefix}_RESULT: PASSED" in serial
    )
    marker_names = {
        "wifi": (
            "BOOT_FLAG",
            "MAIN_START",
            "OBJECT_READY",
            "ACTIVE",
            "SCAN_BEGIN",
            "SCAN_OK",
            "CONNECT_BEGIN",
            "CONNECT_RETURNED",
            "RESULT:",
        ),
        "ble": (
            "BOOT_FLAG",
            "MAIN_START",
            "OBJECT_READY",
            "ACTIVE",
            "CONFIG",
            "ADVERTISE_BEGIN",
            "ADVERTISE_OK",
            "RESULT:",
        ),
    }[args.probe]
    markers = [
        f"CORE2_{prefix}_{name}"
        for name in marker_names
        if f"CORE2_{prefix}_{name}" in serial
    ]
    evidence = {
        "schema_version": 1,
        "scope": "simulation-only-not-hardware-validation",
        "status": "PASS" if passed else "FAIL",
        "profile": f"uiflow2-core2-stock-{args.probe}",
        "firmware": {
            "path": display_path(image),
            "bytes": image.stat().st_size,
            "sha256": firmware_sha256,
            "build_output_sha256": sha256(built_image),
            "isolated_copy": True,
            "base_sha256": sha256(BASE),
        },
        "qemu": {
            "path": display_path(args.qemu),
            "sha256": sha256(args.qemu),
            "exit_code": qemu_exit,
            "stderr": qemu_stderr[-4000:],
        },
        "attempts": attempts,
        "selected_attempt": selected_dir.name,
        "reached_main": f"CORE2_{prefix}_MAIN_START" in serial,
        "serial": {
            "path": str(selected_dir / "serial.log"),
            "bytes": (selected_dir / "serial.log").stat().st_size,
            "sha256": sha256(selected_dir / "serial.log"),
            "markers": markers,
            "last_lines": serial.splitlines()[-20:],
        },
        "not_claimed": [
            "real-hardware behavior",
            "WiFi" if args.probe == "ble" else "BLE",
            "OpenETH equivalence to WiFi",
        ],
    }
    evidence_path = args.out_dir / "evidence.json"
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Run the registered M5Stack UIFlow2 virtual-host matrix."""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from esp_flash import flash_with_esp_emu, flash_with_qemu

ROOT = Path(__file__).resolve().parents[2]
MATRIX = ROOT / "tests/uiflow2/device_matrix.json"
RUNNER = ROOT / "tests/uiflow2/run_profile_ui_test.py"
TAB5_RUNNER = ROOT / "tests/uiflow2/run_tab5_ui_test.py"


def run_logged(label: str, command: list[str], out_dir: Path, timeout: float,
               env: dict[str, str]) -> tuple[int, str]:
    stdout_path = out_dir / f"{label}.stdout"
    stderr_path = out_dir / f"{label}.stderr"
    with stdout_path.open("wb") as stdout, stderr_path.open("wb") as stderr:
        try:
            result = subprocess.run(
                command,
                cwd=ROOT,
                env=env,
                stdout=stdout,
                stderr=stderr,
                timeout=timeout,
                check=False,
            )
            return result.returncode, stdout_path.read_text(errors="replace")
        except subprocess.TimeoutExpired:
            return 124, stdout_path.read_text(errors="replace")


def ui_command(
    device: dict,
    backend: dict,
    device_out: Path,
    *,
    prebuilt_image: Path | None = None,
    build_only: bool = False,
) -> list[str]:
    command = [
        sys.executable,
        str(RUNNER),
        "--base", str(ROOT / device["base"]),
        "--machine", device["machine"],
        "--files-dir", str(ROOT / device["files_dir"]),
        "--vfs-offset", device["vfs_offset"],
        "--vfs-size", device["vfs_size"],
        "--flash-size", device["flash_size"],
        "--expected-size", device["expected_size"],
        "--input", device["input"],
        "--wait", str(device.get("wait", 6)),
        "--post-input-wait", str(device.get("post_input_wait", 0.6)),
        "--efuse-driver", backend["efuse_driver"],
        "--qemu", str(ROOT / backend["qemu"]),
        "--rom-dir", str(ROOT / backend["rom_dir"]),
        "--out-dir", str(device_out),
    ]
    if prebuilt_image:
        command.extend(["--prebuilt-image", str(prebuilt_image)])
    if build_only:
        command.append("--build-only")
    if "efuse_pkg_version" in device:
        command.extend(["--efuse-pkg-version", str(device["efuse_pkg_version"])])
    if "memory" in device:
        command.extend(["--memory", device["memory"]])
    if "post_frame_color" in device:
        command.extend(["--post-frame-color", device["post_frame_color"]])
    serial_expect = device.get("serial_expect", [])
    if isinstance(serial_expect, str):
        serial_expect = [serial_expect]
    for marker in serial_expect:
        command.extend(["--serial-expect", marker])
    return command


def run_ui(
    device: dict,
    backend: dict,
    out_dir: Path,
    env: dict[str, str],
    flash_transport: str,
) -> dict:
    device_out = out_dir / device["id"]
    device_out.mkdir(parents=True, exist_ok=True)
    flash_info = {"transport": "host-image", "verified": True}
    prebuilt_image = None
    build_out = device_out / "build"
    build_out.mkdir(parents=True, exist_ok=True)
    esp_emu_chip = backend.get("esp_emu_chip")
    qemu_esptool_chip = backend.get("qemu_esptool_chip")
    esptool_transport = (
        "esp-emu-esptool" if esp_emu_chip else "qemu-esptool"
    )
    if flash_transport == "esp-emu" and (esp_emu_chip or qemu_esptool_chip):
        build_command = ui_command(
            device, backend, build_out, build_only=True
        )
        build_code, build_stdout = run_logged(
            f"{device['id']}-build",
            build_command,
            out_dir,
            device.get("timeout", 60),
            env,
        )
        built_image = build_out / "uiflow2-ui-test.bin"
        if build_code or not built_image.is_file():
            return {
                "status": "FAIL",
                "exit_code": build_code or 1,
                "command": build_command,
                "output": str(build_out),
                "flash": {"transport": esptool_transport, "verified": False},
                "reason": build_stdout[-1200:] or "test image build failed",
            }
        try:
            flash_args = {
                "chip": esp_emu_chip or qemu_esptool_chip,
                "image": built_image,
                "flash_size": int(device["flash_size"], 0),
                "out_dir": device_out / "flash",
                "env": env,
                "timeout": max(
                    device.get("timeout", 60),
                    600 if qemu_esptool_chip else 240,
                ),
            }
            if esp_emu_chip:
                flash_info = flash_with_esp_emu(**flash_args)
            else:
                flash_info = flash_with_qemu(
                    **flash_args,
                    machine=device["machine"],
                    qemu=ROOT / backend["qemu"],
                    rom_dir=ROOT / backend["rom_dir"],
                    memory=device.get("memory"),
                )
            prebuilt_image = Path(flash_info["virtual_flash"])
        except Exception as error:
            return {
                "status": "FAIL",
                "exit_code": 1,
                "command": build_command,
                "output": str(build_out),
                "flash": {
                    "transport": esptool_transport,
                    "verified": False,
                    "error": str(error),
                },
                "reason": str(error),
            }

    run_out = device_out / "run" if prebuilt_image else device_out
    run_out.mkdir(parents=True, exist_ok=True)
    command = ui_command(device, backend, run_out, prebuilt_image=prebuilt_image)
    code, stdout = run_logged(
        f"{device['id']}-run" if prebuilt_image else device["id"],
        command,
        out_dir,
        device.get("timeout", 60),
        env,
    )
    passed = code == 0 and "PASS " in stdout
    return {
        "status": "PASS" if passed else "FAIL",
        "exit_code": code,
        "command": command,
        "output": str(run_out),
        "flash": flash_info,
    }


def build_console_image(device: dict, device_out: Path,
                        env: dict[str, str]) -> Path:
    image = device_out / "uiflow2-console-test.bin"
    command = [
        sys.executable,
        str(ROOT / device["files_dir"] / "make_image.py"),
        "--base", str(ROOT / device["base"]),
        "--out", str(image),
    ]
    result = subprocess.run(
        command, cwd=ROOT, env=env, capture_output=True, text=True, check=False
    )
    (device_out / "build.stdout").write_text(result.stdout)
    (device_out / "build.stderr").write_text(result.stderr)
    if result.returncode:
        raise RuntimeError(result.stderr or result.stdout)
    return image


def run_console(
    device: dict,
    backend: dict,
    out_dir: Path,
    env: dict[str, str],
    flash_transport: str,
) -> dict:
    device_out = out_dir / device["id"]
    device_out.mkdir(parents=True, exist_ok=True)
    image = build_console_image(device, device_out, env)
    case_env = env.copy()
    case_env.update(device.get("env", {}))
    rmt_nec = device.get("rmt_nec")
    rmt_capture = None
    if rmt_nec:
        rmt_capture = Path(rmt_nec["capture"]).with_name(
            f"{device['id']}-{Path(rmt_nec['capture']).name}"
        )
        rmt_capture = device_out / rmt_capture.name
        case_env["M5SW_RMT_TX_FILE"] = str(rmt_capture)
    flash_info = {"transport": "host-image", "verified": True}
    esp_emu_chip = backend.get("esp_emu_chip")
    if flash_transport == "esp-emu" and esp_emu_chip:
        try:
            flash_info = flash_with_esp_emu(
                chip=esp_emu_chip,
                image=image,
                flash_size=int(device["flash_size"], 0),
                out_dir=device_out / "flash",
                env=case_env,
                timeout=max(device.get("timeout", 20), 120),
            )
            image = Path(flash_info["virtual_flash"])
        except Exception as error:
            return {
                "status": "FAIL",
                "exit_code": 1,
                "output": str(device_out),
                "flash": {
                    "transport": "esp-emu-esptool",
                    "verified": False,
                    "error": str(error),
                },
                "reason": str(error),
            }
    serial = device_out / "serial.log"
    command = [
        str(ROOT / backend["qemu"]),
        "-M", device["machine"],
        "-drive", f"file={image},if=mtd,format=raw",
        "-L", str(ROOT / backend["rom_dir"]),
        "-display", "none",
        "-serial", "null",
        "-serial", "null",
        "-serial", f"file:{serial}",
    ]
    deadline = time.time() + device.get("timeout", 20)
    proc = subprocess.Popen(
        command, cwd=ROOT, env=case_env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    expected = device["serial_expect"]
    matched = False
    try:
        while time.time() < deadline:
            text = serial.read_text(errors="replace") if serial.exists() else ""
            if all(marker in text for marker in expected):
                matched = True
                break
            if proc.poll() is not None:
                break
            time.sleep(0.1)
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
    text = serial.read_text(errors="replace") if serial.exists() else ""
    missing = [marker for marker in expected if marker not in text]
    if matched and rmt_nec and rmt_capture:
        validation = subprocess.run(
            [
                sys.executable,
                str(ROOT / "tests/uiflow2/check_rmt_nec.py"),
                str(rmt_capture),
                "--address", hex(int(rmt_nec["address"])),
                "--command", hex(int(rmt_nec["command"])),
            ],
            cwd=ROOT,
            env=case_env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            check=False,
        )
        if validation.returncode == 0:
            return {
                "status": "PASS",
                "exit_code": 0,
                "command": command,
                "output": str(device_out),
                "flash": flash_info,
                "rmt_nec": validation.stdout.strip(),
            }
        missing.append("RMT validation: " + validation.stdout.strip())
    elif matched:
        return {
            "status": "PASS",
            "exit_code": 0,
            "command": command,
            "output": str(device_out),
            "flash": flash_info,
        }
    return {
        "status": "FAIL",
        "exit_code": 1,
        "command": command,
        "output": str(device_out),
        "flash": flash_info,
        "reason": f"missing serial markers: {', '.join(missing)}",
    }


def run_blocked_smoke(device: dict, out_dir: Path,
                      env: dict[str, str]) -> dict:
    device_out = out_dir / device["id"]
    device_out.mkdir(parents=True, exist_ok=True)
    command = [
        str(ROOT / device["emulator"]),
        "--chip", "esp32p4",
        "--firmware", str(ROOT / device["base"]),
        "--timeout", f"{device.get('timeout', 12)}s",
        "--console", "uart0",
    ]
    code, stdout = run_logged(
        device["id"], command, out_dir, device.get("timeout", 12) + 10, env
    )
    stderr = (out_dir / f"{device['id']}.stderr").read_text(errors="replace")
    text = stdout + stderr
    if device["expected_error"] in text:
        return {
            "status": "BLOCKED",
            "exit_code": code,
            "command": command,
            "output": str(device_out),
            "reason": device["reason"],
        }
    return {
        "status": "FAIL",
        "exit_code": code,
        "command": command,
        "output": str(device_out),
        "reason": f"expected failure marker not observed: {device['expected_error']}",
    }


def run_tab5(
    device: dict,
    out_dir: Path,
    env: dict[str, str],
    flash_transport: str,
) -> dict:
    device_out = out_dir / device["id"]
    device_out.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        str(TAB5_RUNNER),
        "--base", str(ROOT / device["base"]),
        "--elf", str(ROOT / device["elf"]),
        "--files-dir", str(ROOT / device["files_dir"]),
        "--out-dir", str(device_out),
        "--emulator", str(ROOT / device["emulator"]),
        "--rom", str(ROOT / device["rom"]),
        "--efuse", str(ROOT / device["efuse"]),
        "--c6-firmware", str(ROOT / device["c6_firmware"]),
        "--expected-size", device["expected_size"],
        "--touch", device["touch"],
        "--timeout", str(device.get("timeout", 120)),
        "--flash-transport",
        "esptool" if flash_transport == "esp-emu" else "host-image",
    ]
    code, stdout = run_logged(
        device["id"],
        command,
        out_dir,
        device.get("matrix_timeout", 420),
        env,
    )
    result_path = device_out / "result.json"
    detail = (
        json.loads(result_path.read_text())
        if result_path.is_file()
        else {}
    )
    passed = code == 0 and "PASS " in stdout
    return {
        "status": "PASS" if passed else "FAIL",
        "exit_code": code,
        "command": command,
        "output": str(device_out),
        "flash": detail.get("flash", {
            "transport": "esp-emu-esptool" if flash_transport == "esp-emu"
            else "host-image",
            "verified": False,
        }),
        "detail": detail,
        **({} if passed else {"reason": stdout[-1200:]}),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", action="append", default=[],
                        help="device id; repeat to select multiple")
    parser.add_argument("--out-dir", type=Path,
                        default=Path("/tmp/m5-uiflow2-device-matrix"))
    parser.add_argument("--allow-blocked", action="store_true")
    parser.add_argument(
        "--flash-transport",
        choices=("direct", "esp-emu"),
        default="esp-emu",
        help="flash the test image through esptool where supported",
    )
    args = parser.parse_args()

    matrix = json.loads(MATRIX.read_text())
    backends = matrix["backends"]
    selected = set(args.device)
    devices = [
        device for device in matrix["devices"]
        if not selected or device["id"] in selected
    ]
    unknown = selected - {device["id"] for device in matrix["devices"]}
    if unknown:
        raise SystemExit(f"unknown device ids: {', '.join(sorted(unknown))}")

    args.out_dir.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(ROOT / ".work/py"), env.get("PYTHONPATH", "")])
    )

    results = {}
    for device in devices:
        print(f"[{device['id']}] {device['mode']}", flush=True)
        if device["mode"] == "ui":
            attempts = int(device.get("retries", 0)) + 1
            for attempt in range(attempts):
                attempt_root = (
                    args.out_dir
                    if attempt == 0
                    else args.out_dir / f"retry-{attempt}"
                )
                result = run_ui(
                    device,
                    backends[device["backend"]],
                    attempt_root,
                    env,
                    args.flash_transport,
                )
                result["attempts"] = attempt + 1
                if result["status"] == "PASS":
                    break
        elif device["mode"] == "console":
            result = run_console(
                device,
                backends[device["backend"]],
                args.out_dir,
                env,
                args.flash_transport,
            )
        elif device["mode"] == "blocked-smoke":
            result = run_blocked_smoke(device, args.out_dir, env)
        elif device["mode"] == "tab5-gdb-ui":
            result = run_tab5(
                device, args.out_dir, env, args.flash_transport
            )
        elif device["mode"] == "backend-required":
            result = {
                "status": "BLOCKED",
                "exit_code": 0,
                "reason": device["reason"],
            }
        elif device["mode"] == "excluded":
            result = {
                "status": "EXCLUDED",
                "exit_code": 0,
                "reason": device["reason"],
            }
        else:
            result = {
                "status": "FAIL",
                "exit_code": 2,
                "reason": f"unsupported mode: {device['mode']}",
            }
        results[device["id"]] = result
        print(f"[{device['id']}] {result['status']}", flush=True)

    summary = {
        "schema_version": 1,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "out_dir": str(args.out_dir),
        "results": results,
    }
    (args.out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n"
    )
    counts = {
        status: sum(result["status"] == status for result in results.values())
        for status in ("PASS", "FAIL", "BLOCKED", "EXCLUDED")
    }
    print(json.dumps(counts, sort_keys=True))
    if counts["FAIL"] or (counts["BLOCKED"] and not args.allow_blocked):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

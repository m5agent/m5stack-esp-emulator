#!/usr/bin/env python3
"""Run an official UIFlow2 image through the device-local WiFi probe."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
PROBE_DIR = Path(__file__).resolve().parent / "wifi"
MATRIX = ROOT / "tests/uiflow2/device_matrix.json"
PROFILE_RUNNER = ROOT / "tests/uiflow2/run_profile_ui_test.py"
NETWORK_LANE = ROOT / "platform/tools/network_lane.py"
EMULATOR = (
    ROOT
    / ".work/esp-emu-versions/0.50.0"
    / "esp-emu-0.50.0-aarch64-apple-darwin/esp-emu"
)
BACKEND_CHIPS = {
    "qemu-esp32s3": "esp32s3",
    "qemu-esp32c6": "esp32c6",
}
PROVENANCE_SCHEMA_VERSION = 1


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def display_path(path: Path) -> str:
    try:
        return str(path.resolve().relative_to(ROOT))
    except ValueError:
        return str(path.resolve())


def provenance_path(image: Path) -> Path:
    return image.with_suffix(".build.json")


def write_build_provenance(
    image: Path,
    base: Path,
    device: dict,
) -> dict:
    provenance = {
        "schema_version": PROVENANCE_SCHEMA_VERSION,
        "device_id": device["id"],
        "image": display_path(image),
        "image_sha256": sha256(image),
        "base": display_path(base),
        "base_sha256": sha256(base),
        "vfs_offset": device["vfs_offset"],
        "vfs_size": device["vfs_size"],
        "flash_size": device["flash_size"],
    }
    provenance_path(image).write_text(
        json.dumps(provenance, indent=2) + "\n"
    )
    return provenance


def load_build_provenance(image: Path, device_id: str) -> dict:
    path = provenance_path(image)
    if not path.is_file():
        raise RuntimeError(
            f"--skip-build requires build provenance: {path}"
        )
    try:
        provenance = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError(f"invalid build provenance {path}: {error}") from error
    if provenance.get("schema_version") != PROVENANCE_SCHEMA_VERSION:
        raise RuntimeError(
            f"unsupported build provenance schema in {path}: "
            f"{provenance.get('schema_version')!r}"
        )
    if provenance.get("device_id") != device_id:
        raise RuntimeError(
            f"build provenance is for {provenance.get('device_id')!r}, "
            f"not {device_id!r}: {path}"
        )
    if provenance.get("image_sha256") != sha256(image):
        raise RuntimeError(f"build provenance image hash mismatch: {path}")
    if not isinstance(provenance.get("base_sha256"), str):
        raise RuntimeError(f"build provenance has no base hash: {path}")
    return provenance


def build_image(device: dict, out_dir: Path) -> Path:
    command = [
        "python3",
        str(PROFILE_RUNNER),
        "--base",
        str(ROOT / device["base"]),
        "--machine",
        device["machine"],
        "--files-dir",
        str(PROBE_DIR),
        "--vfs-offset",
        device["vfs_offset"],
        "--vfs-size",
        device["vfs_size"],
        "--flash-size",
        device["flash_size"],
        "--expected-size",
        device.get("expected_size", "1x1"),
        "--out-dir",
        str(out_dir),
    ]
    if "efuse_pkg_version" in device:
        command.extend(
            ["--efuse-pkg-version", str(device["efuse_pkg_version"])]
        )
    if device.get("memory") is not None:
        command.extend(["--memory", str(device["memory"])])
    command.append("--build-only")
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, [str(ROOT / ".work/py"), env.get("PYTHONPATH", "")])
    )
    subprocess.run(command, cwd=ROOT, env=env, check=True, timeout=90)
    image = out_dir / "uiflow2-ui-test.bin"
    if not image.is_file():
        raise RuntimeError(f"image build did not create {image}")
    write_build_provenance(image, ROOT / device["base"], device)
    return image


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--device", required=True)
    parser.add_argument("--base", type=Path)
    parser.add_argument("--vfs-offset")
    parser.add_argument("--vfs-size")
    parser.add_argument("--out-dir", type=Path, required=True)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--skip-build", action="store_true")
    args = parser.parse_args()

    matrix = json.loads(MATRIX.read_text())
    devices = {device["id"]: device for device in matrix["devices"]}
    device = devices.get(args.device)
    if device is None:
        raise SystemExit(f"unknown UIFlow2 device: {args.device}")
    if args.device == "tab5":
        raise SystemExit("Tab5 is explicitly excluded")
    if args.base is not None:
        device = dict(device)
        device["base"] = str(args.base.resolve())
    if args.vfs_offset is not None or args.vfs_size is not None:
        device = dict(device)
        if args.vfs_offset is not None:
            device["vfs_offset"] = args.vfs_offset
        if args.vfs_size is not None:
            device["vfs_size"] = args.vfs_size
    chip = BACKEND_CHIPS.get(device.get("backend", ""))
    if chip is None:
        raise SystemExit(
            f"{args.device} is not an ESP32-S3/C6 UIFlow2 network target"
        )

    args.out_dir.mkdir(parents=True, exist_ok=True)
    network_dir = args.out_dir / "network"
    image = (
        args.out_dir / "uiflow2-ui-test.bin"
        if args.skip_build
        else build_image(device, args.out_dir)
    )
    provenance = (
        load_build_provenance(image, args.device)
        if args.skip_build
        else json.loads(provenance_path(image).read_text())
    )
    image_sha256 = sha256(image)
    command = [
        "python3",
        str(NETWORK_LANE),
        "--profile",
        "generic-observe",
        "--chip",
        chip,
        "--firmware",
        str(image),
        "--emulator",
        str(EMULATOR),
        "--out-dir",
        str(network_dir),
        "--timeout",
        str(args.timeout),
        "--net-mode",
        "user",
        "--console-mode",
        "auto",
        "--wifi",
        "--no-ble",
        "--no-tcp",
        *(["--psram-size", "0"] if chip == "esp32c6" else []),
        "--expect",
        "UIFLOW_WIFI_CONNECTED",
        "--expect",
        "UIFLOW_WIFI_RESULT: PASSED",
        "--json",
    ]
    completed = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=args.timeout + 30,
    )
    network_evidence_path = network_dir / "evidence.json"
    if not network_evidence_path.is_file():
        raise RuntimeError(
            f"network lane did not write evidence: {completed.stderr[-4000:]}"
        )
    network_evidence = json.loads(network_evidence_path.read_text())
    passed = (
        completed.returncode == 0
        and network_evidence.get("status") == "PASS"
        and network_evidence.get("checks", {}).get("marker:1") is True
        and network_evidence.get("checks", {}).get("marker:2") is True
    )
    evidence = {
        "schema_version": 1,
        "scope": "simulation-only-not-hardware-validation",
        "status": "PASS" if passed else "FAIL",
        "device_id": args.device,
        "chip": chip,
        "firmware": {
            "path": str(image),
            "bytes": image.stat().st_size,
            "sha256": image_sha256,
            "base": provenance["base"],
            "base_sha256": provenance["base_sha256"],
            "provenance": str(provenance_path(image)),
        },
        "network_evidence": str(network_evidence_path),
        "network_status": network_evidence.get("status"),
        "checks": network_evidence.get("checks", {}),
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
        "not_claimed": [
            "real-hardware behavior",
            "BLE",
            "stock user application behavior",
            "board peripherals in the same instance",
        ],
    }
    evidence_path = args.out_dir / "evidence.json"
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps(evidence, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

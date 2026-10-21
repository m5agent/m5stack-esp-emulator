#!/usr/bin/env python3
"""Verify CardputerZero factory UI startup and optional SPI panel first frame."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent


def ppm_stats(path: Path) -> dict:
    if not path.is_file():
        return {"status": "PARTIAL", "reason": "no panel frame emitted"}
    data = path.read_bytes()
    parts = data.split(b"\n", 3)
    if len(parts) != 4 or parts[0] != b"P6":
        return {"status": "FAIL", "reason": "invalid PPM"}
    pixels = parts[3]
    nonblack = sum(1 for value in pixels if value)
    return {
        "status": "PASS" if nonblack else "PARTIAL",
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        "nonblack_bytes": nonblack,
        "unique_bytes": len(set(pixels[:120000])),
        "reason": None if nonblack else "panel frame is black",
    }


def marker_int(text: str, marker: str, default: int = 0) -> int:
    match = re.search(rf"^{marker}=([0-9]+)$", text, re.MULTILINE)
    return int(match.group(1)) if match else default


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--image",
        type=Path,
        default=ROOT / ".work/cardputerzero/cardputerzero-work.img",
    )
    parser.add_argument(
        "--kernel",
        type=Path,
        default=ROOT / ".work/cardputerzero/boot/kernel8.img",
    )
    parser.add_argument(
        "--dtb",
        type=Path,
        default=ROOT / ".work/cardputerzero/boot/cardputerzero-v5-test.dtb",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("/tmp/m5-cardputerzero-factory-ui"),
    )
    parser.add_argument("--timeout", type=float, default=120)
    parser.add_argument("--require-frame", action="store_true")
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    panel_frame = args.out_dir / "panel.ppm"
    env = os.environ.copy()
    env.update(
        {
            "M5SW_BCM_SPI_PANEL": "1",
            "M5SW_BCM_SPI_PANEL_DUMP": str(panel_frame),
        }
    )
    append = (
        "console=ttyAMA1,115200 root=PARTUUID=f6c408b0-02 "
        "rootfstype=ext4 rootwait rw earlycon=pl011,0x3f201000 "
        "systemd.unit=multi-user.target m5.key_probe=1 "
        "m5.ui_probe=1"
    )
    subprocess.run(
        [
            "python3", str(HERE / "run_linux_boot.py"),
            "--machine", "raspi3b",
            "--memory", "512M",
            "--image", str(args.image),
            "--kernel", str(args.kernel),
            "--dtb", str(args.dtb),
            "--append", append,
            "--out-dir", str(args.out_dir),
            "--complete-marker", "M5_FACTORY_LOG_DONE",
            "--transient",
            "--timeout", str(args.timeout),
        ],
        cwd=ROOT,
        env=env,
        check=True,
    )

    console = (args.out_dir / "console.log").read_bytes()
    text = console.replace(b"\0", b"").decode("utf-8", "replace")
    startup_ok = (
        "using framebuffer display device: /dev/fb1" in text
        and "LVGL app started at 320x170" in text
    )
    frame = ppm_stats(panel_frame)
    fb_changed = "M5_UI_FRAME_CHANGED=1" in text
    fb_nonblack = marker_int(text, "M5_UI_FRAME_NONBLACK")
    fb_pixels = marker_int(text, "M5_UI_FRAME_PIXELS")
    fb_colors = marker_int(text, "M5_UI_FRAME_UNIQUE_RGB565")
    fb_frame = {
        "status": "PASS"
        if fb_changed and fb_pixels > 0 and fb_nonblack > 0
        else "PARTIAL",
        "changed": fb_changed,
        "pixels": fb_pixels,
        "nonblack_pixels": fb_nonblack,
        "unique_rgb565": fb_colors,
        "sha256": next(
            (
                line.split("=", 1)[1]
                for line in text.splitlines()
                if line.startswith("M5_UI_FRAME_HASH=")
            ),
            None,
        ),
    }
    frame_ok = frame["status"] == "PASS" or fb_frame["status"] == "PASS"
    result = {
        "status": (
            "PASS"
            if startup_ok and frame_ok
            else "PARTIAL"
            if startup_ok
            else "FAIL"
        ),
        "startup_ok": startup_ok,
        "frame": frame if frame["status"] == "PASS" else fb_frame,
        "panel_frame": frame,
    }
    (args.out_dir / "factory-ui-result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    )
    print(
        "FACTORY_UI",
        f"startup={'PASS' if startup_ok else 'FAIL'}",
        f"frame={result['frame']['status']}",
    )
    if not startup_ok or (args.require_frame and not frame_ok):
        raise SystemExit(1)


if __name__ == "__main__":
    main()

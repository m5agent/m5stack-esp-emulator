#!/usr/bin/env python3
"""Run the Tab5 UART1 RS-485 peer test through esp-emu."""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tests/uiflow2/run_tab5_ui_test.py"
VENV_PYTHON = ROOT / ".work/tab5-venv/bin/python"


def main() -> None:
    if (
        VENV_PYTHON.is_file()
        and Path(sys.executable).resolve() != VENV_PYTHON.resolve()
    ):
        os.execv(
            str(VENV_PYTHON),
            [str(VENV_PYTHON), str(Path(__file__).resolve()), *sys.argv[1:]],
        )

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--base",
        type=Path,
        default=ROOT / ".work/uiflow2-tab5/tab5-emulator-merged.bin",
    )
    parser.add_argument(
        "--elf",
        type=Path,
        default=ROOT / ".work/uiflow2-tab5/micropython.elf",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=Path("/tmp/m5-tab5-rs485"),
    )
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--touch", default="640,520")
    parser.add_argument(
        "--probe-only",
        action="store_true",
        help="skip framebuffer capture and touch verification",
    )
    args = parser.parse_args()

    command = [
        sys.executable,
        str(RUNNER),
        "--base", str(args.base),
        "--elf", str(args.elf),
        "--files-dir", str(ROOT / "tests/uiflow2/tab5_rs485"),
        "--out-dir", str(args.out_dir),
        "--timeout", str(args.timeout),
        "--uart1-peer",
        "--ready-marker", "TAB5_RS485_DONE PASS",
        "--touch", args.touch,
        "--i2c-dev", "1:0x41,fill=0,reg=0xFE=0x54,reg=0xFF=0x49",
        "--i2c-dev", "1:0x43,fill=0,reg=0x01=0xA2",
        "--i2c-dev", "1:0x44,fill=0,reg=0x01=0xA2",
        "--i2c-dev", "1:0x32,fill=0",
        "--i2c-dev", "1:0x68,fill=0,reg=0x00=0x24",
        "--i2c-dev", "1:0x55,fill=0",
    ]
    if args.probe_only:
        command.append("--probe-only")
    result = subprocess.run(command, cwd=ROOT, check=False)
    raise SystemExit(result.returncode)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Run an explicitly labelled USB source candidate through a selected service."""
import argparse
from pathlib import Path

import run_guest

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--api", required=True)
parser.add_argument("--token-file", type=Path, required=True)
parser.add_argument("--device", choices=("cores3", "cardputer-adv"), required=True)
parser.add_argument("--fixture-dir", type=Path, required=True)
parser.add_argument("--out-dir", type=Path, required=True)
parser.add_argument("--timeout", type=int, default=180)
args = parser.parse_args()
args.source = Path(__file__).with_name("probe_usb_buffer_correction.py")
args.done_marker = "USB_BUFFER_CORRECTION_DONE"
args.runtime = "qemu"
args.firmware_lane = "candidate-python-source"
raise SystemExit(run_guest.run(args))

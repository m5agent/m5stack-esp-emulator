#!/usr/bin/env python3
"""Build the CardputerZero test DTB and remove the duplicate invalid card."""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
from pathlib import Path


def require_tool(name: str) -> str:
    path = shutil.which(name)
    if not path:
        raise SystemExit(f"missing required tool: {name}")
    return path


def remove_node(text: str, marker: str, search_from: int = 0) -> tuple[str, int]:
    start = text.find(marker, search_from)
    if start < 0:
        raise ValueError(f"node marker not found: {marker!r}")
    brace = text.find("{", start)
    if brace < 0:
        raise ValueError(f"opening brace not found for {marker!r}")

    depth = 0
    end = -1
    for index in range(brace, len(text)):
        if text[index] == "{":
            depth += 1
        elif text[index] == "}":
            depth -= 1
            if depth == 0:
                end = index + 1
                break
    if end < 0:
        raise ValueError(f"closing brace not found for {marker!r}")

    semicolon = text.find(";", end)
    if semicolon < 0:
        raise ValueError(f"node terminator not found for {marker!r}")
    return text[:start] + text[semicolon + 1:], semicolon + 1


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-dtb", type=Path, required=True)
    parser.add_argument("--overlay-dir", type=Path, required=True)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--imx219",
        action="store_true",
        help="enable the official two-lane IMX219 overlay on CSI1",
    )
    args = parser.parse_args()

    overlays = [
        args.overlay_dir / "cardputerzero-v5-overlay.dtbo",
        args.overlay_dir / "bq27220_v5.dtbo",
        args.overlay_dir / "bmi270_bmm150_overlay.dtbo",
        args.overlay_dir / "es8389_m5stack.dtbo",
        args.overlay_dir / "dwc2.dtbo",
        args.overlay_dir / "gpio-ir.dtbo",
        args.overlay_dir / "gpio-ir-tx.dtbo",
    ]
    if args.imx219:
        overlays.append(args.overlay_dir / "imx219.dtbo")
    for path in (args.base_dtb, *overlays):
        if not path.is_file():
            raise SystemExit(f"missing input: {path}")

    args.out.parent.mkdir(parents=True, exist_ok=True)
    merged = args.out.with_suffix(".merged.dtb")
    merged_dts = args.out.with_suffix(".merged.dts")
    fixed_dts = args.out.with_suffix(".dts")

    subprocess.run(
        [
            require_tool("fdtoverlay"),
            "-i",
            str(args.base_dtb),
            "-o",
            str(merged),
            *(str(path) for path in overlays),
        ],
        check=True,
    )
    subprocess.run(
        [
            require_tool("dtc"),
            "-I",
            "dtb",
            "-O",
            "dts",
            "-o",
            str(merged_dts),
            str(merged),
        ],
        check=True,
    )

    text = merged_dts.read_text()
    if args.imx219:
        # QEMU does not implement the VideoCore firmware clock provider used
        # by the stock CSI1 "vpu" clock.  Unicam only requires this clock to
        # be at least 250 MHz; expose that fixed gate while keeping the CSI
        # lane clock on CPRMAN.
        clock_anchor = "\tinterrupt-parent = <0x01>;\n"
        clock_node = (
            clock_anchor
            + "\n"
            + "\tunicam_vpu_clk: unicam-vpu-clock {\n"
            + '\t\tcompatible = "fixed-clock";\n'
            + "\t\t#clock-cells = <0x00>;\n"
            + "\t\tclock-frequency = <250000000>;\n"
            + "\t};\n"
        )
        if text.count(clock_anchor) != 1:
            raise SystemExit("failed to add Unicam VPU fixed clock")
        text = text.replace(clock_anchor, clock_node, 1)
        old_clock = "clocks = <0x08 0x2e 0x14 0x04>;"
        new_clock = "clocks = <0x08 0x2e &unicam_vpu_clk>;"
        if text.count(old_clock) != 1:
            raise SystemExit("failed to retarget CSI1 VPU clock to CPRMAN")
        text = text.replace(old_clock, new_clock, 1)
        # Linux 6.18's fw_devlink resolves the camera graph into a cycle
        # between CSI1, the IMX219 supplier and raspberrypi-power.  QEMU
        # models the power/clock registers directly, so retain the CSI clock
        # and supply dependencies but remove only the synthetic devlink edge.
        pattern = (
            r"(csi1: csi: csi@7e801000 \{.*?)"
            r"power-domains = <0x10 0x0d>;\n"
        )
        text, count = re.subn(pattern, r"\1", text, count=1, flags=re.DOTALL)
        if count != 1:
            raise SystemExit("failed to normalize CSI1 power-domain link")
    sound_start = text.find("\tsound {")
    if sound_start < 0:
        raise SystemExit("merged DTB has no /sound node")
    text, _ = remove_node(
        text, "\n\t\tsimple-audio-card,dai-link {", sound_start
    )
    # The vendor IR overlays default to GPIO18, which is the I2S BCLK on
    # CardputerZero.  Move RX to schematic G13 and TX to schematic G12.
    replacements = (
        (
            r"(gpio_ir_pins@[0-9a-f]+ \{.*?brcm,pins = <)0x12",
            r"\g<1>0xd",
        ),
        (
            r"(ir-receiver@[0-9a-f]+ \{.*?gpios = <0x07 )0x12",
            r"\g<1>0xd",
        ),
        (
            r"(gpio_ir_tx_pins@[0-9a-f]+ \{.*?brcm,pins = <)0x12",
            r"\g<1>0xc",
        ),
        (
            r"(gpio-ir-transmitter@[0-9a-f]+ \{.*?gpios = <0x07 )0x12",
            r"\g<1>0xc",
        ),
    )
    for pattern, replacement in replacements:
        text, count = re.subn(
            pattern, replacement, text, count=1, flags=re.DOTALL
        )
        if count != 1:
            raise SystemExit(f"failed to retarget IR node: {pattern}")
    text, count = re.subn(
        r'(dwc2_usb: usb@[0-9a-f]+ \{.*?)dr_mode = "otg";',
        r'\g<1>dr_mode = "host";',
        text,
        count=1,
        flags=re.DOTALL,
    )
    if count != 1:
        raise SystemExit("failed to set DWC2 controller to host mode")
    fixed_dts.write_text(text)

    subprocess.run(
        [
            require_tool("dtc"),
            "-I",
            "dts",
            "-O",
            "dtb",
            "-o",
            str(args.out),
            str(fixed_dts),
        ],
        check=True,
    )
    print(args.out)


if __name__ == "__main__":
    main()

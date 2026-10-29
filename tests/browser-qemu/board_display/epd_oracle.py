# SPDX-License-Identifier: MIT
"""Recompute the pinned EPD QUALITY oracle without a guest or local source cache.

This independent mathematical implementation follows the published driver:
https://github.com/m5stack/M5GFX/tree/9bcedf4e19d4cab7a0793de0598ae5390b4689fe
The original driver identifies its license as FreeBSD; its source is not bundled.
Run with --check (default), --write, or --stdout from any working directory.
The result predicts controller output; it is not execution or hardware evidence.
"""

import argparse
from collections import Counter
from functools import lru_cache
import hashlib
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
OUTPUT = ROOT / "platform/tests/fixtures/browser_epd_quality_oracles.json"
COMMIT = "9bcedf4e19d4cab7a0793de0598ae5390b4689fe"
BAYER = (-30, 18, -22, 26, -14, 2, -6, 10,
         -18, 30, -26, 22, -2, 14, -10, 6)
# Native index, representative post-refresh RGB888, in the driver's tie order.
PALETTE = ((0, 0x000000), (1, 0xFFFFFF), (2, 0xFFF338),
           (3, 0xBF0000), (5, 0x6440FF), (6, 0x438A1C))
MONO = (0x000000, 0x505050, 0xB0B0B0, 0xFFFFFF)
SOURCE_PINS = (
    ("src/M5GFX.cpp", "4d1cf1345a6cb9477c371ce3a12fade45bb32f4e3fe53725a2a81ddb3588c997", "2120-2136,2327-2342"),
    ("src/lgfx/v1/panel/Panel_ED2208.cpp", "095d17534f2b78c37bfb044e6fcba517c63bc3c43ce279386923ee8c49078472", "31-51,92-141,185-231,425-451"),
    ("src/lgfx/v1/panel/Panel_SSD1677.cpp", "c87a4c6a95a24d50d4d2750fe99215c655d673b040337523e3ace13fba093f58", "36,485-509,616-625,888-906,994-998"),
    ("src/lgfx/v1/panel/Panel_HasBuffer.cpp", "ae27849955f1398682d17ae0e918f42c670b1eb172d317ac90390c6b70e25830", "75-84,141-173"),
    ("src/lgfx/v1/misc/colortype.hpp", "f436d81152c145ae97e287c3e3685601b21b9081fc6a4a2fe4638f52f2e9ea25", "454-469"),
)
FIXTURE_PINS = {
    "papercolor": "c18b09c5290562fcea2071faf5b9e7984f2b36b8a347fa76a85d4fdb2997448a",
    "papermono": "9ec71a31dfe6ad2d359e48a9bc1bdd9ce5eccb0080271fe819e3cfce109d403e",
}


def channels(rgb):
    return (rgb >> 16 & 255, rgb >> 8 & 255, rgb & 255)


def rgb565(rgb):
    return (rgb >> 19 & 31) << 11 | (rgb >> 10 & 63) << 5 | (rgb >> 3 & 31)


def biased(rgb, x, y):
    # Algebraic form of the driver's per-row recurrence, at absolute native x/y.
    period = 129 * 127
    phase = (y * (129 * 48) - (x + 1) * (127 * 29)) % period
    phases = (phase, (phase - period // 3) % period,
              (phase - 2 * (period // 3)) % period)
    signed = tuple(value * 2 - (period - 1) for value in phases)
    common = (sum(signed) * 140) >> 16
    # Python's signed >> matches the Xtensa/GCC arithmetic shift here.
    return tuple(value + common + ((bias * 140) >> 16)
                 for value, bias in zip(channels(rgb), signed))


@lru_cache(maxsize=None)
def color_pair(rgb, even_x, y):
    left, right = biased(rgb, even_x, y), biased(rgb, even_x + 1, y)
    best = None
    result = None
    for left_index, left_rgb in PALETTE:
        dl = tuple(a - b for a, b in zip(left, channels(left_rgb)))
        for right_index, right_rgb in PALETTE:
            dr = tuple(a - b for a, b in zip(right, channels(right_rgb)))
            distance = sum((a + b) ** 2 + a ** 2 + b ** 2
                           for a, b in zip(dl, dr))
            if best is None or distance < best:
                best, result = distance, (left_index, right_index)
    return result


def pixel(device, rgb, x, y):
    if device == "papercolor":
        index = color_pair(rgb, x & ~1, y)[x & 1]
        return rgb565(dict(PALETTE)[index])
    gray = (channels(rgb)[0] + 2 * channels(rgb)[1] + channels(rgb)[2]) >> 2
    # SDK rotation0 + board offset_rotation3; same inverse used by QEMU console.
    native_x, native_y = y, 479 - x
    level = max(0, min(3, (gray + BAYER[(native_x & 3) + ((native_y & 3) << 2)]) >> 6))
    return rgb565(MONO[level])


def region(device, rgb, rect, primary):
    hist = Counter()
    exceptions = []
    for y in range(rect["y"], rect["y"] + rect["height"]):
        for x in range(rect["x"], rect["x"] + rect["width"]):
            value = pixel(device, rgb, x, y)
            hist[value] += 1
            if value != primary:
                exceptions.append({"x": x, "y": y, "rgb565": value})
    return {"inputRGB888": rgb, "rect": rect, "primary": primary,
            "histogram": {str(value): hist[value] for value in sorted(hist)},
            "exceptions": exceptions}


def build():
    devices = {}
    for device, inputs, step, outputs in (
        ("papercolor", (0, 0xFFFFFF, 0xFFFF00, 0xFF0000, 0x0000FF, 0x00FF00),
         56, tuple(rgb565(rgb) for _, rgb in PALETTE)),
        ("papermono", (0, 0x555555, 0xAAAAAA, 0xFFFFFF),
         108, tuple(rgb565(rgb) for rgb in MONO)),
    ):
        fixture = "tests/browser-qemu/board_display/" + device + "_main.py"
        actual = hashlib.sha256((ROOT / fixture).read_bytes()).hexdigest()
        if actual != FIXTURE_PINS[device]:
            raise ValueError("Fixture source changed: " + fixture)
        marker = {"x": 16, "y": 16, "width": 16, "height": 16}
        bit = {"x": 26, "y": 274, "width": 30, "height": 30}
        devices[device] = {
            "mainPath": fixture, "mainSHA256": actual, "uiRotation": 0,
            "epdMode": "EPD_QUALITY", "scope": "fixed fixture count 0 -> 1",
            "palette": [region(device, rgb, {"x": 32 + index * step, "y": 110,
                                             "width": 8, "height": 8}, outputs[index])
                        for index, rgb in enumerate(inputs)],
            "marker": {"rect": marker, "before": region(device, 0, marker, 0),
                       "after": region(device, 0xFFFFFF, marker, 65535)},
            "bit0": {"rect": bit, "before": region(device, 0xFFFFFF, bit, 65535),
                     "after": region(device, 0, bit, 0)},
        }
    return {
        "schema_version": 1, "evidenceLevel": "source-derived-not-guest",
        "description": "Exact ROI patterns: fill primary, then overwrite absolute exception coordinates. Histograms are additional checks, not pixel tolerances.",
        "uiflow2": {"version": "2.5.3", "commit": "50e440780492aa847378c7d3477ab912f7063bac",
                    "m5gfxSubmodule": COMMIT,
                    "url": "https://github.com/m5stack/uiflow-micropython/tree/50e440780492aa847378c7d3477ab912f7063bac"},
        "sources": [{"repository": "m5stack/M5GFX", "commit": COMMIT,
                     "path": path, "sha256": digest, "lines": lines,
                     "url": "https://github.com/m5stack/M5GFX/blob/" + COMMIT + "/" + path}
                    for path, digest, lines in SOURCE_PINS],
        "qemuController": {"path": "hw/m5stopwatch/m5_epd_panel.c",
                           "sha256": "34a1b53b7265f7ae7d4d33cd0410bcb650a499979aa80192e76d53576d2d8a89",
                           "lines": "46-81,102-110",
                           "binding": "Source inspected; compiled WASM provenance and actual guest acceptance are separate gates."},
        "formulas": {
            "rgb888ToQemuRGB565": "((rgb >> 19 & 31) << 11) | ((rgb >> 10 & 63) << 5) | (rgb >> 3 & 31)",
            "ssd1677": "gray=(R+2*G+B)>>2; native=(logical_y,479-logical_x); level=clamp((gray+Bayer[(native_x&3)+4*(native_y&3)])>>6,0,3); QUALITY sends inverted planes, QEMU inverts them back.",
            "ssd1677Bayer": list(BAYER),
            "spectra6": "Native x/y, QUALITY dither=140; phase=(y*6192-(x+1)*3683)%16383; RGB phases differ by 5461. Signed channel bias=(phase*2-16382)*140>>16 plus common(sum signed)*140>>16. Adjacent pair minimizes summed block squared RGB error + individual squared errors, first palette pair wins ties.",
            "spectra6PaletteOrder": [{"index": index, "rgb888": rgb, "rgb565": rgb565(rgb)} for index, rgb in PALETTE],
        },
        "rgb888ToRGB565": {f"0x{rgb:06x}": rgb565(rgb) for rgb in sorted(set(MONO) | {rgb for _, rgb in PALETTE})},
        "reproduction": "python3 tests/browser-qemu/board_display/epd_oracle.py --check",
        "devices": devices,
        "limitations": ["Source arithmetic predicts controller frames; this file is not browser or hardware PASS.",
                        "Only the pinned sources, rotation 0, full QUALITY refresh, palette ROIs and count 0-to-1 marker/bit0 are covered.",
                        "Counter-text glyph identity is not supplied by this oracle; its separate ROI change check does not prove exact numeral pixels."]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--check", action="store_true")
    action.add_argument("--write", action="store_true")
    action.add_argument("--stdout", action="store_true")
    args = parser.parse_args()
    result = build()
    encoded = json.dumps(result, indent=2, ensure_ascii=False) + "\n"
    if args.write:
        OUTPUT.write_text(encoded, encoding="utf-8")
        print("Wrote " + str(OUTPUT.relative_to(ROOT)))
    elif args.stdout:
        print(encoded, end="")
    else:
        if json.loads(OUTPUT.read_text(encoding="utf-8")) != result:
            raise SystemExit("EPD source-derived oracle differs; inspect before regenerating")
        print("PASS: pinned EPD QUALITY ROI patterns, histograms and fixture hashes")


if __name__ == "__main__":
    main()

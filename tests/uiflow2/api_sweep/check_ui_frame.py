#!/usr/bin/env python3
"""Check an explicit UI data-plane oracle against a retained PNG.

A nonempty image alone never passes. Missing OCR/QR tooling remains a blocker;
unsupported shape descriptions remain pending instead of becoming visual PASS.
"""
from __future__ import annotations

import io
import json
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tempfile
from functools import lru_cache


@lru_cache(maxsize=1)
def mac_qr_reader():
    compiler = shutil.which("swiftc")
    if platform.system() != "Darwin" or compiler is None:
        return None
    directory = tempfile.TemporaryDirectory(prefix="m5-ui-qr-")
    binary = Path(directory.name) / "decode-qr"
    source = Path(__file__).with_name("decode_ui_qr.swift")
    result = subprocess.run([compiler, str(source), "-o", str(binary)], capture_output=True, timeout=60)
    if result.returncode:
        directory.cleanup()
        return None
    return directory, binary


def check_frame(raw: bytes, oracle: dict, tolerance: int = 8) -> dict:
    from PIL import Image

    image = Image.open(io.BytesIO(raw)).convert("RGB")
    kind = oracle["kind"]
    if kind == "color_region":
        box = oracle["box"]
        if not (0 <= box[0] < box[2] <= image.width and 0 <= box[1] < box[3] <= image.height):
            return {"status": "ORACLE_OUT_OF_BOUNDS", "box": box, "dimensions": list(image.size)}
        expected = oracle["rgb"]
        target = ((expected >> 16) & 255, (expected >> 8) & 255, expected & 255)
        matches = sum(max(abs(a - b) for a, b in zip(pixel, target)) <= tolerance for pixel in image.crop(box).getdata())
        minimum = oracle.get("minimum", 1)
        maximum = oracle.get("maximum", (box[2] - box[0]) * (box[3] - box[1]))
        return {"status": "FRAME_PASS" if minimum <= matches <= maximum else "FAIL", "matching_pixels": matches,
                "minimum": minimum, "maximum": maximum, "box": box, "rgb": expected}
    if kind == "pixels":
        observations = []
        for x, y, expected in oracle["points"]:
            if not (0 <= x < image.width and 0 <= y < image.height):
                return {"status": "ORACLE_OUT_OF_BOUNDS", "point": [x, y], "dimensions": list(image.size)}
            actual = image.getpixel((x, y))
            target = ((expected >> 16) & 255, (expected >> 8) & 255, expected & 255)
            observations.append({"point": [x, y], "actual": list(actual), "expected": list(target),
                                 "matches": max(abs(a - b) for a, b in zip(actual, target)) <= tolerance})
        return {"status": "FRAME_PASS" if observations and all(row["matches"] for row in observations) else "FAIL",
                "observations": observations, "tolerance": tolerance}
    if kind.startswith("text"):
        executable = shutil.which("tesseract")
        if executable is None:
            return {"status": "BLOCKED_ORACLE", "reason": "tesseract is required for an independent glyph oracle"}
        box = oracle["box"]
        if not (0 <= box[0] < box[2] <= image.width and 0 <= box[1] < box[3] <= image.height):
            return {"status": "ORACLE_OUT_OF_BOUNDS", "box": box, "dimensions": list(image.size)}
        crop = image.crop(box)
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary) / "glyphs.png"
            crop.resize((crop.width * 4, crop.height * 4)).save(source)
            result = subprocess.run([executable, str(source), "stdout", "--psm", "6"],
                                    capture_output=True, text=True, timeout=20)
        if result.returncode:
            return {"status": "BLOCKED_ORACLE", "reason": "tesseract failed", "exit_code": result.returncode}
        normalize = lambda value: re.sub(r"\s+", "", value).casefold()
        matches = normalize(oracle["text"]) in normalize(result.stdout)
        return {"status": "GLYPH_PASS" if matches else "ORACLE_MISMATCH", "recognized": result.stdout.strip(),
                "expected": oracle["text"], "scope": "glyph content only; alignment/color require separate pixel checks"}
    if kind == "qr_decode":
        if "box" in oracle:
            box = oracle["box"]
            if not (0 <= box[0] < box[2] <= image.width and 0 <= box[1] < box[3] <= image.height):
                return {"status": "ORACLE_OUT_OF_BOUNDS", "box": box, "dimensions": list(image.size)}
            image = image.crop(box)
        try:
            from pyzbar.pyzbar import decode
        except (ImportError, OSError):
            reader = mac_qr_reader()
            if reader is None:
                return {"status": "BLOCKED_ORACLE", "reason": "QR decode requires pyzbar/zbar or macOS Vision with swiftc"}
            with tempfile.TemporaryDirectory() as temporary:
                source = Path(temporary) / "frame.png"
                image.save(source)
                result = subprocess.run([str(reader[1]), str(source)], capture_output=True, text=True, timeout=20)
            if result.returncode:
                return {"status": "BLOCKED_ORACLE", "reason": "macOS Vision QR decoding failed"}
            messages = json.loads(result.stdout)
        else:
            messages = [item.data.decode("utf-8") for item in decode(image)]
        return {"status": "FRAME_PASS" if oracle["text"] in messages else "ORACLE_MISMATCH", "decoded": messages}
    return {"status": "PENDING_FRAME_REVIEW", "reason": "No exact evaluator for " + kind, "oracle": oracle}

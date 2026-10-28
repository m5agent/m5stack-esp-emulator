#!/usr/bin/env python3
"""Independently check retained camera raw scenes and encoded image colors.

Pillow parses guest-produced JPG/BMP bytes. The intended scene uses logical
RGB565 color values, independent of the native converter's input byte order.
An additional swapped-byte comparison is diagnostic and cannot grant PASS.
"""
import argparse
import hashlib
import io
import json
from pathlib import Path
import struct
import zipfile

from PIL import Image


def scene(seed, wire_order="msb-first"):
    raw, rgb, swapped = bytearray(), bytearray(), bytearray()
    bands = ((235, 48, 48), (235, 190, 35), (40, 190, 80), (35, 105, 235))
    for y in range(240):
        for x in range(320):
            r, g, b = bands[(y // 60 + seed) % 4]
            if x % 40 < 2 or y % 40 < 2:
                r = g = b = 245
            value = ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)
            raw.extend(struct.pack(">H" if wire_order == "msb-first" else "<H", value))
            rgb.extend(((value >> 8) & 0xf8, (value >> 3) & 0xfc, (value << 3) & 0xf8))
            other = ((value & 255) << 8) | (value >> 8)
            swapped.extend(((other >> 8) & 0xf8, (other >> 3) & 0xfc, (other << 3) & 0xf8))
    return bytes(raw), bytes(rgb), bytes(swapped)


def color_error(actual, expected, interior=False):
    differences = []
    for y in range(240):
        for x in range(320):
            if interior and (x % 40 < 6 or x % 40 > 35 or y % 40 < 6 or y % 40 > 35 or y % 60 < 4 or y % 60 > 55):
                continue
            offset = (y * 320 + x) * 3
            differences.extend(abs(actual[offset + c] - expected[offset + c]) for c in range(3))
    return {"mean_absolute_channel_error": round(sum(differences) / len(differences), 6),
            "max_channel_error": max(differences), "channels_compared": len(differences)}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("--seed", type=int, default=0)
    parser.add_argument("--wire-order", choices=("msb-first", "legacy-lsb-first"), default="msb-first")
    args = parser.parse_args()
    folder = args.folder
    report = json.loads((folder / "report.json").read_text())
    rows, metadata, chunks = [], {}, {}
    for line in (folder / "serial.txt").read_text().splitlines():
        if line.startswith("VISION_API "):
            rows.append(json.loads(line.split(" ", 1)[1]))
        elif line.startswith("CAMERA_BLOB "):
            value = json.loads(line.split(" ", 1)[1]); metadata[value["kind"]] = value
        elif line.startswith("CAMERA_BLOB_CHUNK "):
            value = json.loads(line.split(" ", 1)[1]); chunks.setdefault(value["kind"], []).append(value)
    expected_raw, expected_rgb, expected_swapped = scene(args.seed, args.wire_order)
    expected_hash = hashlib.sha256(expected_raw).hexdigest()
    Image.frombytes("RGB", (320, 240), expected_rgb).save(folder / "camera-expected-scene.png")
    actions = json.loads((folder / "host-actions.json").read_text())
    settings = {row.get("payload", {}).get("property"): row.get("payload", {}).get("value") for row in actions if row.get("status") == "OBSERVED" and row.get("payload", {}).get("path") == "/machine/m5-lcd-cam"}
    raw_rows = [row for row in rows if row["api"] in ("camera.capture", "camera.skip_frames", "camera.snapshot")]
    checks = {
        "executed_stock_lane": report.get("status") == "EXECUTED" and report.get("firmware_lane") == "stock-frozen",
        "explicit_fixed_scene": settings.get("frame-seed") == args.seed and settings.get("auto-increment") is False,
        "all_raw_observation_points": len(raw_rows) == 6 and sum(row["api"] == "camera.capture" for row in raw_rows) == 4,
        "complete_raw_scene_hashes": bool(raw_rows) and all(row.get("bytes") == 153600 and row.get("sha256") == expected_hash for row in raw_rows),
        "no_guest_api_failures": bool(rows) and not any(row["status"] in ("FAIL", "ERROR") for row in rows),
        "no_native_crash": not any(marker in (folder / "serial.txt").read_text() for marker in ("A fatal error occurred", "Guru Meditation", "stack overflow", "abort() was called")),
        "stopped_history_preserved": report.get("cleanup", {}).get("runtime_pid_gone") is True and report.get("cleanup", {}).get("history_preserved") is True,
        "evidence_zip_hash": hashlib.sha256((folder / "evidence.zip").read_bytes()).hexdigest() == report.get("evidence_sha256"),
    }
    with zipfile.ZipFile(folder / "evidence.zip") as archive:
        checks["evidence_zip_valid"] = archive.testzip() is None
    encoded = {}
    for kind in ("jpg", "bmp"):
        details = {"status": "FAIL"}
        try:
            data = bytearray()
            for part in chunks.get(kind, []):
                if part["offset"] != len(data):
                    raise ValueError("missing, duplicate or reordered encoded image chunk")
                data.extend(bytes.fromhex(part["hex"]))
            info = metadata[kind]
            if len(data) != info["bytes"] or hashlib.sha256(data).hexdigest() != info["sha256"]:
                raise ValueError("encoded image length/hash mismatch")
            (folder / ("camera-native." + kind)).write_bytes(data)
            with Image.open(io.BytesIO(data)) as parsed:
                image_format, image_size = parsed.format, parsed.size
                parsed.verify()
            with Image.open(io.BytesIO(data)) as parsed:
                decoded = parsed.convert("RGB")
                decoded.save(folder / ("camera-decoded-" + kind + ".png"))
                pixels = decoded.tobytes()
            if image_size != (320, 240):
                raise ValueError("decoded image is not QVGA")
            full = color_error(pixels, expected_rgb)
            interior = color_error(pixels, expected_rgb, interior=True)
            swapped = color_error(pixels, expected_swapped)
            # BMP is lossless. JPEG quality 80 permits bounded quantization and
            # chroma error, with a stricter interior check away from grid edges.
            color_ok = pixels == expected_rgb if kind == "bmp" else full["mean_absolute_channel_error"] <= 8 and interior["mean_absolute_channel_error"] <= 4 and interior["max_channel_error"] <= 24
            details.update(status="DATA_PLANE_PASS" if color_ok else "FAIL", bytes=len(data), format=image_format,
                size=list(image_size), expected_scene_error=full, interior_error=interior,
                swapped_byte_diagnostic_error=swapped, oracle="Independent Pillow decode compared with intended logical RGB565 scene; byte-swapped diagnostic cannot grant PASS.")
        except (OSError, ValueError, KeyError) as error:
            details["error"] = str(error)
        encoded[kind] = details
        checks[kind + "_decoded_scene_correct"] = details["status"] == "DATA_PLANE_PASS"
    result = {"schema_version": 1, "status": "DATA_PLANE_PASS" if all(checks.values()) else "PARTIAL",
        "validation": "virtual-device validation", "hardware_validation": "NOT RUN", "checks": checks,
        "wire_order": args.wire_order,
        "legacy_boundary": "Legacy little-endian raw hashes establish transfer of the old model's contents only; correct sensor wire order and image colors remain failed." if args.wire_order != "msb-first" else None,
        "expected_raw_sha256": expected_hash, "encoded_images": encoded,
        "scope": "CoreS3 QVGA RGB565 raw capture, snapshot and native JPG/BMP conversion; same-format reconfiguration and native deinit/reinit. skip_frames is a call plus subsequent exact-frame observation; discarded-frame count is not independently measured. Mirror getters are state assertions, and sensor image transforms are not implemented/proven.",
        "guest_methods": rows,
        "evidence": {"report": str(folder / "report.json"), "host_actions": str(folder / "host-actions.json"), **{key: report.get(key) for key in ("session_id", "source_sha256", "firmware_sha256", "runtime_binary_sha256", "evidence_sha256")}}}
    (folder / "camera-interfaces-oracle.json").write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "checks": checks, "encoded_images": encoded}))
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Run the M5StickT2 bare-metal probe and check the Lepton/panel data plane.

The probe (tests/uiflow2/stickt2_probe) is a freestanding ESP32 image loaded
with `-kernel`; it drives the real memory-mapped HSPI (Lepton VoSPI), GPIO
bit-banged I2C (FLIR Lepton CCI + encoder) and VSPI (ST7789) controllers.
This runner starts QEMU, injects the encoder value through QOM, collects the
probe markers and the Lepton model state, screenshots the panel and compares
the on-guest VoSPI frame digests with an independent host reconstruction of
the deterministic thermal fixture.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
PROBE_DIR = ROOT / "tests/uiflow2/stickt2_probe"
DEFAULT_QEMU = ROOT / ".work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa"
DEFAULT_ROM = ROOT / ".work/M5StopWatch-QEMU/build/qemu/pc-bios"
DEFAULT_ELF = ROOT / "platform/.cache/firmware/stickt2/probe/stickt2-probe.elf"

FLIR_W, FLIR_H = 160, 120
FRAME_BYTES = FLIR_W * FLIR_H * 2
SEGMENTS = 4
PACKETS_PER_SEGMENT = 60
PACKETS_PER_FRAME = SEGMENTS * PACKETS_PER_SEGMENT
TEMPERATURE_MARKERS = [
    "STICKT2_BOOT",
    "LEPTON_CCI_PING 0000",
    "LEPTON_CCI_SET_OK",
    "LEPTON_CCI_TEMP 30000 29950",
    "STICKT2_PANEL_INIT 135 240",
    "STICKT2_PANEL_OK 135 240",
    "STICKT2_STATUS ok",
]
FRAME_RE = re.compile(
    r"^VOPSI_FRAME (\d+) (\d+) (\d+) (\d+) (0x[0-9a-f]+) (\d+) (\d+)$"
)
ERRORS_RE = re.compile(r"^VOPSI_FRAME_ERRORS (\d+)$")
ENCODER_RE = re.compile(r"^STICKT2_ENCODER (\d+) (\d+)$")


def fixture_raw(x: int, y: int, seed: int) -> int:
    warm_x = 12 + ((seed * 13) % 96)
    warm_y = 10 + ((seed * 7) % 64)
    value = 5200 + ((x * 19 + y * 31 + seed * 337) % 2600)
    if warm_x <= x < warm_x + 40 and warm_y <= y < warm_y + 30:
        value += 2600
    if 118 <= x < 150 and 88 <= y < 114:
        value = 4300 + (seed * 11) % 600
    return value or 1


def fixture_frame(seed: int) -> bytes:
    data = bytearray(FRAME_BYTES)
    for y in range(FLIR_H):
        for x in range(FLIR_W):
            value = fixture_raw(x, y, seed)
            index = (y * FLIR_W + x) * 2
            data[index] = value >> 8
            data[index + 1] = value & 0xFF
    return bytes(data)


def fnv1a(data: bytes) -> int:
    value = 2166136261
    for byte in data:
        value ^= byte
        value = (value * 16777619) & 0xFFFFFFFF
    return value


def oracle_digests(count: int = 3) -> list[dict]:
    result = []
    for seed in range(count):
        frame = fixture_frame(seed)
        values = [
            int.from_bytes(frame[i:i + 2], "big")
            for i in range(0, len(frame), 2)
        ]
        result.append({
            "seed": seed,
            "digest": f"0x{fnv1a(frame):08x}",
            "bytes": len(frame),
            "raw_min": min(values),
            "raw_max": max(values),
            "sha256": hashlib.sha256(frame).hexdigest(),
        })
    return result


class Qmp:
    def __init__(self, path: Path):
        self.path = path
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        deadline = time.time() + 10
        while True:
            try:
                self.sock.connect(str(path))
                break
            except OSError:
                if time.time() > deadline:
                    raise
                time.sleep(0.05)
        self.file = self.sock.makefile("rwb")
        self.file.readline()  # greeting
        self.command({"execute": "qmp_capabilities"})

    def command(self, payload: dict) -> dict:
        self.file.write((json.dumps(payload) + "\n").encode())
        self.file.flush()
        while True:
            line = self.file.readline()
            if not line:
                raise RuntimeError("QMP closed")
            data = json.loads(line)
            if "return" in data or "error" in data:
                return data

    def qom_get(self, path: str, prop: str):
        data = self.command({
            "execute": "qom-get",
            "arguments": {"path": path, "property": prop},
        })
        if "error" in data:
            return None
        return data.get("return")

    def qom_set(self, path: str, prop: str, value) -> None:
        data = self.command({
            "execute": "qom-set",
            "arguments": {"path": path, "property": prop, "value": value},
        })
        if "error" in data:
            raise RuntimeError(f"qom-set {path}.{prop} failed: {data['error']}")

    def screendump(self, path: Path) -> None:
        data = self.command({
            "execute": "screendump",
            "arguments": {"filename": str(path), "format": "ppm"},
        })
        if "error" in data:
            raise RuntimeError(f"screendump failed: {data['error']}")

    def close(self) -> None:
        try:
            self.sock.close()
        except OSError:
            pass


def ppm_stats(path: Path) -> dict:
    data = path.read_bytes()
    if not data.startswith(b"P6"):
        raise ValueError("not a P6 PPM")
    fields = []
    index = 2
    while len(fields) < 3:
        while data[index:index + 1].isspace():
            index += 1
        if data[index:index + 1] == b"#":
            while data[index:index + 1] not in (b"\n", b""):
                index += 1
            continue
        start = index
        while not data[index:index + 1].isspace():
            index += 1
        fields.append(int(data[start:index]))
    index += 1
    width, height, _ = fields
    pixels = data[index:index + width * height * 3]
    nonblack = 0
    unique = set()
    color_sum = 0
    color_count = 0
    for offset in range(0, len(pixels), 3):
        red, green, blue = pixels[offset:offset + 3]
        color = (red << 16) | (green << 8) | blue
        unique.add(color)
        color_sum += red + green + blue
        color_count += 1
        if color != 0:
            nonblack += 1
    return {
        "width": width,
        "height": height,
        "sha256": hashlib.sha256(data).hexdigest(),
        "nonblack_pixels": nonblack,
        "unique_colors": len(unique),
        "mean_channel": round(color_sum / max(1, color_count * 3), 2),
    }


def build_probe(elf: Path) -> None:
    elf.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        [str(PROBE_DIR / "build.sh"), str(elf.parent)],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    built = elf.parent / "stickt2-probe.elf"
    if built != elf:
        built.replace(elf)


def run(args: argparse.Namespace) -> dict:
    out_dir = args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)
    elf = args.elf
    if args.build or not elf.is_file():
        build_probe(elf)
    serial = out_dir / "serial.log"
    qmp_path = Path("/tmp") / f"stickt2-probe-{os.getpid()}.sock"
    try:
        qmp_path.unlink()
    except FileNotFoundError:
        pass
    command = [
        str(args.qemu),
        "-M", "m5stickt2",
        "-accel", "tcg,thread=single",
        "-kernel", str(elf),
        "-L", str(args.rom_dir),
        "-display", "none",
        "-serial", f"file:{serial}",
        "-serial", "null",
        "-serial", "null",
        "-qmp", f"unix:{qmp_path},server=on,wait=off",
    ]
    env = os.environ.copy()
    env.update(args.env or {})
    proc = subprocess.Popen(
        command, cwd=ROOT, env=env,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    markers: list[str] = []
    encoder_injected = False
    qmp = None
    try:
        qmp = Qmp(qmp_path)
        # The probe reads the encoder on every frame; pre-load the injected
        # value before the first frame is captured and re-apply it if the
        # first marker appears later.
        qmp.qom_set("/machine/encoder", "increment", 5)
        encoder_injected = True
        deadline = time.time() + args.timeout
        text = ""
        while time.time() < deadline:
            if serial.is_file():
                text = serial.read_text(errors="replace")
            if not encoder_injected and ENCODER_RE.search(text):
                qmp.qom_set("/machine/encoder", "increment", 5)
                encoder_injected = True
            if "STICKT2_STATUS ok" in text:
                break
            if proc.poll() is not None:
                break
            time.sleep(0.05)
        text = serial.read_text(errors="replace") if serial.is_file() else ""
        markers = [line for line in text.splitlines() if line]
        time.sleep(0.2)
        ppm = out_dir / "panel.ppm"
        qmp.screendump(ppm)
        qom = {
            "lepton": {
                prop: qmp.qom_get("/machine/lepton", prop)
                for prop in (
                    "frames-started", "segments-served", "packets-served",
                    "vsyncs", "frame-seed", "frame-digest",
                    "segment-interval-us", "vsync-width-us",
                )
            },
            "lepton-cci": {
                prop: qmp.qom_get("/machine/lepton-cci", prop)
                for prop in ("commands", "gets", "sets", "fpa-temp-mk",
                             "aux-temp-mk")
            },
            "encoder": {
                prop: qmp.qom_get("/machine/encoder", prop)
                for prop in ("increment", "switch")
            },
        }
    finally:
        try:
            if qmp is not None:
                qmp.close()
        finally:
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
    stats = ppm_stats(out_dir / "panel.ppm")

    frames = []
    for line in markers:
        match = FRAME_RE.match(line)
        if match:
            frames.append({
                "index": int(match.group(1)),
                "width": int(match.group(2)),
                "height": int(match.group(3)),
                "bytes": int(match.group(4)),
                "digest": match.group(5),
                "raw_min": int(match.group(6)),
                "raw_max": int(match.group(7)),
            })
    errors = [int(m.group(1)) for m in
              (ERRORS_RE.match(line) for line in markers) if m]
    encoders = [
        {"increment": int(m.group(1)), "switch": int(m.group(2))}
        for m in (ENCODER_RE.match(line) for line in markers) if m
    ]

    expected = oracle_digests(3)
    errors_list: list[str] = []
    for marker in TEMPERATURE_MARKERS:
        if not any(marker in line for line in markers):
            errors_list.append(f"missing marker: {marker}")
    if len(frames) < 3:
        errors_list.append(f"expected 3 VoSPI frames, got {len(frames)}")
    else:
        for frame, oracle in zip(frames, expected):
            if frame["bytes"] != FRAME_BYTES:
                errors_list.append(f"frame {frame['index']}: wrong byte count")
            if frame["digest"] != oracle["digest"]:
                errors_list.append(
                    f"frame {frame['index']}: digest {frame['digest']} != "
                    f"oracle {oracle['digest']}"
                )
            if (frame["raw_min"], frame["raw_max"]) != (
                    oracle["raw_min"], oracle["raw_max"]):
                errors_list.append(
                    f"frame {frame['index']}: raw range mismatch"
                )
    if any(errors):
        errors_list.append(f"VoSPI packet errors: {errors}")
    if not any(enc["increment"] == 5 for enc in encoders):
        errors_list.append("encoder QOM injection not observed")
    if qom["lepton"]["packets-served"] is None:
        errors_list.append("missing Lepton QOM state")
    elif qom["lepton"]["packets-served"] < PACKETS_PER_FRAME * 3:
        errors_list.append(
            "Lepton served fewer packets than three full frames"
        )
    if stats["nonblack_pixels"] < 1000:
        errors_list.append(f"panel blank: {stats}")
    if stats["unique_colors"] < 8:
        errors_list.append(f"panel has too few colors: {stats}")

    result = {
        "status": "PASS" if not errors_list else "FAIL",
        "elf": str(elf),
        "elf_sha256": hashlib.sha256(elf.read_bytes()).hexdigest(),
        "command": command,
        "markers": markers,
        "frames": frames,
        "frame_errors": errors,
        "encoder": encoders,
        "qom": qom,
        "panel": stats,
        "oracle": expected,
        "errors": errors_list,
    }
    (out_dir / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qemu", type=Path, default=DEFAULT_QEMU)
    parser.add_argument("--rom-dir", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--elf", type=Path, default=DEFAULT_ELF)
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--out-dir", type=Path,
                        default=Path("/tmp/m5-stickt2-probe"))
    parser.add_argument("--json-out", type=Path)
    parser.add_argument("--timeout", type=float, default=40.0)
    parser.add_argument("--env", action="append", default=[])
    args = parser.parse_args()
    args.env = dict(item.split("=", 1) for item in args.env)
    result = run(args)
    if args.json_out:
        args.json_out.parent.mkdir(parents=True, exist_ok=True)
        args.json_out.write_text(json.dumps(result, indent=2) + "\n")
    if result["status"] == "PASS":
        print("STICKT2_PROBE_OK")
        print(json.dumps({
            "frames": [frame["digest"] for frame in result["frames"]],
            "panel": result["panel"],
            "qom": result["qom"],
        }, indent=2))
    else:
        print("STICKT2_PROBE_FAIL")
        for error in result["errors"]:
            print(" -", error)
        raise SystemExit(1)


if __name__ == "__main__":
    main()

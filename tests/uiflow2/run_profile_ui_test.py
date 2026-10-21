#!/usr/bin/env python3
"""Build and exercise a UIFlow2 board image in M5Stack QEMU.

The runner replaces only the user LittleFS files, injects one QMP input
event, and requires a non-empty screendump whose canonical pixels change.
It honors QEMU's 4-byte-aligned PPM rows and is intentionally profile
driven so additional ESP32 boards do not need a new bespoke runner.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import socket
import struct
import subprocess
import tempfile
import time
import zlib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]


def build_image(args) -> Path:
    image = bytearray(args.base.read_bytes())
    if len(image) > args.flash_size:
        raise SystemExit(f"base image is larger than flash size {args.flash_size}")
    image.extend(b"\xff" * (args.flash_size - len(image)))

    if args.mklittlefs:
        with tempfile.TemporaryDirectory(prefix="m5-littlefs-") as tmp:
            temp_root = Path(tmp)
            source = temp_root / "files"
            source.mkdir()
            for name in ("boot.py", "main.py"):
                shutil.copyfile(args.files_dir / name, source / name)
            vfs_path = temp_root / "vfs.bin"
            subprocess.run([
                str(args.mklittlefs),
                "-c", str(source),
                "-b", "4096",
                "-p", str(args.prog_size),
                "-s", str(args.vfs_size),
                str(vfs_path),
            ], check=True)
            vfs = bytearray(vfs_path.read_bytes())
    elif args.preserve_vfs:
        vfs = bytearray(image[args.vfs_offset:args.vfs_offset + args.vfs_size])
    else:
        vfs = bytearray([0xff]) * args.vfs_size
    if not args.mklittlefs:
        try:
            import littlefs
        except ImportError:
            raise SystemExit(
                "install littlefs-python: python3 -m pip install littlefs-python"
            )
        fs = littlefs.LittleFS(
            context=littlefs.UserContext(buffer=vfs),
            block_size=4096,
            block_count=args.vfs_size // 4096,
            read_size=128,
            prog_size=args.prog_size,
            lookahead_size=128,
            block_cycles=100,
            mount=False,
        )
        if not args.preserve_vfs:
            fs.format()
        fs.mount()
        for name in ("boot.py", "main.py"):
            with fs.open("/" + name, "w") as f:
                f.write((args.files_dir / name).read_text())
        fs.unmount()
    image[args.vfs_offset:args.vfs_offset + args.vfs_size] = vfs

    out = args.out_dir / "uiflow2-ui-test.bin"
    out.write_bytes(image)
    print(f"image: {out}")
    print(f"sha256: {hashlib.sha256(image).hexdigest()}")
    return out


class QMP:
    def __init__(self, path: Path):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(str(path))
        self.file = self.sock.makefile("rwb")
        self.file.readline()
        self.cmd("qmp_capabilities")

    def cmd(self, name, **arguments):
        request = {"execute": name}
        if arguments:
            request["arguments"] = arguments
        self.file.write((json.dumps(request) + "\n").encode())
        self.file.flush()
        while True:
            line = self.file.readline()
            if not line:
                raise RuntimeError("QMP connection closed")
            reply = json.loads(line)
            if "event" not in reply:
                return reply

    def close(self):
        self.sock.close()


def wait_qmp(path: Path, timeout=15) -> QMP:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists():
            try:
                return QMP(path)
            except OSError:
                pass
        time.sleep(0.1)
    raise RuntimeError(f"QMP socket did not appear: {path}")


def _ppm_token(data: bytes, offset: int) -> tuple[bytes, int]:
    while offset < len(data):
        if data[offset:offset + 1] == b"#":
            newline = data.find(b"\n", offset)
            if newline < 0:
                raise RuntimeError("unterminated PPM comment")
            offset = newline + 1
            continue
        if data[offset:offset + 1].isspace():
            offset += 1
            continue
        break
    end = offset
    while end < len(data) and not data[end:end + 1].isspace():
        end += 1
    if end == offset:
        raise RuntimeError("missing PPM header token")
    return data[offset:end], end


def read_ppm(path: Path) -> tuple[int, int, bytes]:
    with path.open("rb") as f:
        data = f.read()
    magic, offset = _ppm_token(data, 0)
    if magic != b"P6":
        raise RuntimeError(f"not a binary PPM: {path}")
    width_token, offset = _ppm_token(data, offset)
    height_token, offset = _ppm_token(data, offset)
    maxval_token, offset = _ppm_token(data, offset)
    width, height, maxval = map(int, (width_token, height_token, maxval_token))
    if maxval != 255:
        raise RuntimeError(f"unsupported PPM max value {maxval}: {path}")
    if offset >= len(data) or not data[offset:offset + 1].isspace():
        raise RuntimeError(f"missing PPM raster delimiter: {path}")
    if data[offset:offset + 2] == b"\r\n":
        offset += 2
    else:
        offset += 1
    pixels = data[offset:]

    packed_stride = width * 3
    padded_stride = (packed_stride + 3) & ~3
    if len(pixels) == height * packed_stride:
        stride = packed_stride
    elif len(pixels) == height * padded_stride:
        stride = padded_stride
    else:
        raise RuntimeError(
            f"unexpected PPM payload size {len(pixels)} for {width}x{height}: "
            f"expected {height * packed_stride} packed or "
            f"{height * padded_stride} padded bytes"
        )

    if stride == packed_stride:
        return width, height, pixels
    canonical = bytearray(width * height * 3)
    for y in range(height):
        source = pixels[y * stride:y * stride + packed_stride]
        destination = y * packed_stride
        canonical[destination:destination + packed_stride] = source
    return width, height, bytes(canonical)


def _png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xffffffff)
    )


def write_rgb_png(path: Path, width: int, height: int, pixels: bytes) -> None:
    stride = width * 3
    scanlines = bytearray()
    for y in range(height):
        scanlines.append(0)
        scanlines.extend(pixels[y * stride:(y + 1) * stride])
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    png = (
        b"\x89PNG\r\n\x1a\n"
        + _png_chunk(b"IHDR", header)
        + _png_chunk(b"IDAT", zlib.compress(bytes(scanlines), 9))
        + _png_chunk(b"IEND", b"")
    )
    path.write_bytes(png)


def canonicalize_screendump(path: Path) -> tuple[int, int, bytes]:
    width, height, pixels = read_ppm(path)
    packed = path.with_suffix(".packed.ppm")
    png = path.with_suffix(".png")
    packed.write_bytes(f"P6\n{width} {height}\n255\n".encode() + pixels)
    write_rgb_png(png, width, height, pixels)
    return width, height, pixels


def frame_stats(pixels: bytes) -> tuple[int, int]:
    nonblack = 0
    colors = set()
    for offset in range(0, len(pixels), 3):
        rgb = pixels[offset:offset + 3]
        if any(rgb):
            nonblack += 1
            if len(colors) < 256:
                colors.add(rgb)
    return nonblack, len(colors)


def send_input(
    qmp: QMP, spec: str, frame_size: tuple[int, int], settle: float
) -> None:
    kind, value = spec.split(":", 1)
    if kind == "key":
        for down in (True, False):
            event = {
                "type": "key",
                "data": {
                    "down": down,
                    "key": {"type": "qcode", "data": value},
                },
            }
            qmp.cmd("input-send-event", events=[event])
            time.sleep(0.45)
        time.sleep(settle)
        return
    if kind == "touch":
        x, y = map(int, value.split(","))
        width, height = frame_size
        events = [
            {"type": "abs", "data": {"axis": "x",
                                     "value": int(x * 32767 / max(width - 1, 1))}},
            {"type": "abs", "data": {"axis": "y",
                                     "value": int(y * 32767 / max(height - 1, 1))}},
            {"type": "btn", "data": {"down": True, "button": "left"}},
        ]
        qmp.cmd("input-send-event", events=events)
        time.sleep(0.45)
        events[-1] = {"type": "btn", "data": {"down": False, "button": "left"}}
        qmp.cmd("input-send-event", events=events)
        time.sleep(settle)
        return
    raise SystemExit(f"unsupported input spec: {spec}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, type=Path)
    parser.add_argument(
        "--prebuilt-image",
        type=Path,
        help="boot this already-built flash image instead of creating one",
    )
    parser.add_argument(
        "--build-only",
        action="store_true",
        help="create the test flash image and exit before starting QEMU",
    )
    parser.add_argument("--machine", required=True)
    parser.add_argument("--files-dir", required=True, type=Path)
    parser.add_argument("--vfs-offset", required=True, type=lambda x: int(x, 0))
    parser.add_argument("--vfs-size", required=True, type=lambda x: int(x, 0))
    parser.add_argument("--flash-size", required=True, type=lambda x: int(x, 0))
    parser.add_argument("--expected-size", required=True, help="WIDTHxHEIGHT")
    parser.add_argument("--input", required=True, help="key:a or touch:X,Y")
    parser.add_argument("--wait", type=float, default=6.0)
    parser.add_argument("--post-input-wait", type=float, default=0.6)
    parser.add_argument("--min-nonblack-pixels", type=int, default=16)
    parser.add_argument("--min-unique-colors", type=int, default=2)
    parser.add_argument(
        "--preserve-vfs",
        action="store_true",
        help="mount and modify the existing LittleFS image instead of formatting",
    )
    parser.add_argument(
        "--mklittlefs",
        type=Path,
        help="create a disk-version-1 LittleFS image with this mklittlefs binary",
    )
    parser.add_argument("--prog-size", type=int, default=32)
    parser.add_argument("--memory", help="optional QEMU -m value")
    parser.add_argument("--efuse-pkg-version", type=int, choices=(0, 1), default=0)
    parser.add_argument(
        "--efuse-driver",
        help="QEMU eFuse global driver; use 'none' to omit the eFuse drive",
    )
    parser.add_argument("--out-dir", type=Path, default=Path("/tmp/m5-profile-ui-test"))
    parser.add_argument(
        "--qemu",
        type=Path,
        default=PROJECT_ROOT / ".work/M5StopWatch-QEMU/bin/Darwin-arm64/qemu-system-xtensa",
    )
    parser.add_argument(
        "--rom-dir",
        type=Path,
        default=PROJECT_ROOT / ".work/M5StopWatch-QEMU/bin/Darwin-arm64",
    )
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    image = args.prebuilt_image or build_image(args)
    if args.build_only:
        return

    efuse = args.out_dir / "efuse.bin"
    efuse_data = bytearray(4096)
    if args.efuse_pkg_version:
        efuse_data[36:40] = (args.efuse_pkg_version << 21).to_bytes(4, "little")
    efuse.write_bytes(efuse_data)

    serial = args.out_dir / "serial.log"
    before = args.out_dir / "before.ppm"
    after = args.out_dir / "after.ppm"
    qmp_path = Path("/tmp") / f"m5-profile-{os.getpid()}.sock"
    try:
        qmp_path.unlink()
    except FileNotFoundError:
        pass

    command = [
        str(args.qemu),
        "-M", args.machine,
        "-drive", f"file={image},if=mtd,format=raw",
        "-drive", f"if=none,id=efuse,file={efuse},format=raw",
        "-L", str(args.rom_dir),
        "-display", "none",
        "-serial", f"file:{serial}",
        "-qmp", f"unix:{qmp_path},server=on,wait=off",
    ]
    if args.memory:
        command[1:1] = ["-m", args.memory]
    efuse_driver = args.efuse_driver
    if efuse_driver is None:
        efuse_driver = "nvram.esp32s3.efuse"
    if efuse_driver != "none":
        command.extend([
            "-global", f"driver={efuse_driver},property=drive,value=efuse",
        ])
    proc = subprocess.Popen(command)
    try:
        qmp = wait_qmp(qmp_path)
        time.sleep(args.wait)
        qmp.cmd("screendump", filename=str(before))
        expected = tuple(map(int, args.expected_size.lower().split("x")))
        actual = read_ppm(before)[:2]
        if actual != expected:
            raise RuntimeError(f"frame size {actual} != expected {expected}")
        send_input(qmp, args.input, actual, args.post_input_wait)
        qmp.cmd("screendump", filename=str(after))
        qmp.close()
        before_frame = canonicalize_screendump(before)
        after_frame = canonicalize_screendump(after)
        if before_frame[:2] != after_frame[:2]:
            raise RuntimeError(
                f"frame size changed: {before_frame[:2]} != {after_frame[:2]}"
            )
        for label, frame in (("before", before_frame), ("after", after_frame)):
            nonblack, unique_colors = frame_stats(frame[2])
            if nonblack < args.min_nonblack_pixels:
                raise RuntimeError(
                    f"{label} frame is blank: {nonblack} non-black pixels"
                )
            if unique_colors < args.min_unique_colors:
                raise RuntimeError(
                    f"{label} frame has too few colors: {unique_colors}"
                )
        if hashlib.sha256(before_frame[2]).digest() == hashlib.sha256(
            after_frame[2]
        ).digest():
            raise RuntimeError("input did not change the UIFlow2 frame")
        print(
            f"PASS machine={args.machine} size={actual[0]}x{actual[1]} "
            f"input={args.input}"
        )
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        try:
            qmp_path.unlink()
        except FileNotFoundError:
            pass


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Build and exercise a UIFlow2 board image in M5Stack QEMU.

The runner replaces only the user LittleFS files, injects QMP key/touch
click, drag, or long-press sequences, and requires a non-empty screendump
whose canonical pixels change. It can also capture animation frames and
the frame after every input. It honors QEMU's 4-byte-aligned PPM rows and
is intentionally profile driven so additional ESP32 boards do not need a
new bespoke runner.
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


def runtime_files(files_dir: Path) -> dict[Path, Path]:
    files = {}
    common_dir = PROJECT_ROOT / "tests/uiflow2/lib"
    if common_dir.is_dir():
        for path in common_dir.rglob("*.py"):
            files[path.relative_to(common_dir)] = path
    for path in files_dir.rglob("*.py"):
        files[path.relative_to(files_dir)] = path
    return files


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
            for relative, path in runtime_files(args.files_dir).items():
                target = source / relative
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(path, target)
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
        for relative_path, path in runtime_files(args.files_dir).items():
            relative = relative_path.as_posix()
            with fs.open("/" + relative, "w") as f:
                f.write(path.read_text())
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
                if "error" in reply:
                    raise RuntimeError(
                        f"QMP {name} failed: {reply['error'].get('desc', reply['error'])}"
                    )
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


def pointer_events(
    x: int, y: int, frame_size: tuple[int, int], down: bool | None = None
) -> list[dict]:
    width, height = frame_size
    events = [
        {
            "type": "abs",
            "data": {
                "axis": "x",
                "value": int(x * 32767 / max(width - 1, 1)),
            },
        },
        {
            "type": "abs",
            "data": {
                "axis": "y",
                "value": int(y * 32767 / max(height - 1, 1)),
            },
        },
    ]
    if down is not None:
        events.append(
            {"type": "btn", "data": {"down": down, "button": "left"}}
        )
    return events


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
        qmp.cmd("input-send-event", events=pointer_events(x, y, frame_size, True))
        time.sleep(0.45)
        qmp.cmd("input-send-event", events=pointer_events(x, y, frame_size, False))
        time.sleep(settle)
        return
    if kind == "longpress":
        parts = value.split(",")
        if len(parts) != 3:
            raise SystemExit(f"longpress expects x,y,seconds: {spec}")
        x, y = map(int, parts[:2])
        hold = float(parts[2])
        qmp.cmd("input-send-event", events=pointer_events(x, y, frame_size, True))
        time.sleep(hold)
        qmp.cmd("input-send-event", events=pointer_events(x, y, frame_size, False))
        time.sleep(settle)
        return
    if kind == "drag":
        parts = list(map(int, value.split(",")))
        if len(parts) != 4:
            raise SystemExit(f"drag expects x1,y1,x2,y2: {spec}")
        x1, y1, x2, y2 = parts
        qmp.cmd(
            "input-send-event", events=pointer_events(x1, y1, frame_size, True)
        )
        time.sleep(0.15)
        for step in range(1, 7):
            x = x1 + (x2 - x1) * step // 6
            y = y1 + (y2 - y1) * step // 6
            qmp.cmd("input-send-event", events=pointer_events(x, y, frame_size))
            time.sleep(0.08)
        qmp.cmd(
            "input-send-event", events=pointer_events(x2, y2, frame_size, False)
        )
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
    parser.add_argument(
        "--input",
        action="append",
        default=[],
        help=(
            "key:a, touch:X,Y, drag:X1,Y1,X2,Y2, or "
            "longpress:X,Y,SECONDS; repeat for multiple input events"
        ),
    )
    parser.add_argument(
        "--qom-set",
        action="append",
        nargs=3,
        metavar=("PATH", "PROPERTY", "VALUE"),
        default=[],
        help="set a QOM property after boot and before taking the before frame",
    )
    parser.add_argument(
        "--qom-set-boot",
        action="append",
        nargs=3,
        metavar=("PATH", "PROPERTY", "VALUE"),
        default=[],
        help="set a QOM property immediately after QMP starts, before firmware boot",
    )
    parser.add_argument(
        "--qom-step",
        action="append",
        nargs="+",
        metavar="STEP",
        default=[],
        help=(
            "after boot, optionally wait for a serial marker, sleep DELAY "
            "seconds, then set PATH PROPERTY VALUE; repeat to exercise "
            "runtime state transitions"
        ),
    )
    parser.add_argument("--qom-sequence-settle", type=float, default=0.5)
    parser.add_argument("--qom-settle", type=float, default=0.5)
    parser.add_argument(
        "--qom-expect",
        action="append",
        nargs=3,
        metavar=("PATH", "PROPERTY", "VALUE"),
        default=[],
        help="require a QOM property value after inputs; repeat as needed",
    )
    parser.add_argument("--wait", type=float, default=6.0)
    parser.add_argument("--post-input-wait", type=float, default=0.6)
    parser.add_argument(
        "--capture-frames",
        type=int,
        default=0,
        help="capture this many extra animation frames after the before frame",
    )
    parser.add_argument(
        "--capture-interval",
        type=float,
        default=0.12,
        help="seconds between extra animation frame captures",
    )
    parser.add_argument(
        "--capture-dir",
        type=Path,
        help="directory for extra animation frame PNGs",
    )
    parser.add_argument(
        "--capture-each-input",
        action="store_true",
        help="save a PNG after every injected touch, drag, hold, or key",
    )
    parser.add_argument(
        "--post-frame-color",
        help="require pixel X,Y=RRGGBB in the final frame",
    )
    parser.add_argument("--min-nonblack-pixels", type=int, default=16)
    parser.add_argument("--min-unique-colors", type=int, default=2)
    parser.add_argument(
        "--allow-static-frame",
        action="store_true",
        help="do not require the injected input to change the frame",
    )
    parser.add_argument(
        "--serial-expect",
        action="append",
        default=[],
        help="required serial marker; repeat for multiple markers",
    )
    parser.add_argument(
        "--serial1-expect",
        action="append",
        default=[],
        help="required UART1 marker; repeat for multiple markers",
    )
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
        default=(
            PROJECT_ROOT
            / ".work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa"
        ),
    )
    parser.add_argument(
        "--qemu-log",
        help="optional QEMU -d log mask, for example unimp or unimp,guest_errors",
    )
    parser.add_argument(
        "--sd-image",
        type=Path,
        help="raw SD card image to attach as the first QEMU SD drive",
    )
    parser.add_argument(
        "--rom-dir",
        type=Path,
        default=PROJECT_ROOT / ".work/M5StopWatch-QEMU/build/qemu/pc-bios",
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
    serial1 = args.out_dir / "serial1.log"
    before = args.out_dir / "before.ppm"
    after = args.out_dir / "after.ppm"
    capture_dir = args.capture_dir or (args.out_dir / "frames")
    if args.capture_frames or args.capture_each_input:
        capture_dir.mkdir(parents=True, exist_ok=True)
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
        "-serial", f"file:{serial1}",
        "-qmp", f"unix:{qmp_path},server=on,wait=off",
    ]
    if args.sd_image:
        command.extend([
            "-drive", f"file={args.sd_image},if=sd,format=raw",
        ])
    if args.memory:
        command[1:1] = ["-m", args.memory]
    if args.qemu_log:
        command.extend(["-d", args.qemu_log])
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
        for path, prop, raw_value in args.qom_set_boot:
            try:
                value = json.loads(raw_value)
            except json.JSONDecodeError:
                value = raw_value
            qmp.cmd("qom-set", path=path, property=prop, value=value)
            if os.environ.get("M5_QOM_DEBUG"):
                current = qmp.cmd("qom-get", path=path, property=prop)
                print(f"qom-boot {path} {prop}={current['return']}")
        if args.qom_set_boot:
            time.sleep(args.qom_settle)
        time.sleep(args.wait)
        for path, prop, raw_value in args.qom_set:
            try:
                value = json.loads(raw_value)
            except json.JSONDecodeError:
                value = raw_value
            qmp.cmd("qom-set", path=path, property=prop, value=value)
            if os.environ.get("M5_QOM_DEBUG"):
                current = qmp.cmd("qom-get", path=path, property=prop)
                print(f"qom {path} {prop}={current['return']}")
        if args.qom_set:
            time.sleep(args.qom_settle)
        for step in args.qom_step:
            if len(step) not in (4, 5):
                raise RuntimeError(
                    "--qom-step expects DELAY PATH PROPERTY VALUE "
                    "[WAIT_MARKER]"
                )
            raw_delay, path, prop, raw_value = step[:4]
            wait_marker = step[4] if len(step) == 5 else None
            if wait_marker:
                deadline = time.time() + 30
                while wait_marker not in serial.read_text(errors="replace"):
                    if proc.poll() is not None:
                        raise RuntimeError(
                            "process exited while waiting for QOM-step marker "
                            f"{wait_marker!r}"
                        )
                    if time.time() >= deadline:
                        raise RuntimeError(
                            f"timed out waiting for QOM-step marker "
                            f"{wait_marker!r}"
                        )
                    time.sleep(0.1)
            time.sleep(float(raw_delay))
            try:
                value = json.loads(raw_value)
            except json.JSONDecodeError:
                value = raw_value
            qmp.cmd("qom-set", path=path, property=prop, value=value)
            if os.environ.get("M5_QOM_DEBUG"):
                current = qmp.cmd("qom-get", path=path, property=prop)
                print(f"qom-step {path} {prop}={current['return']}")
        if args.qom_step:
            time.sleep(args.qom_sequence_settle)
        qmp.cmd("screendump", filename=str(before))
        expected = tuple(map(int, args.expected_size.lower().split("x")))
        actual = read_ppm(before)[:2]
        if actual != expected:
            raise RuntimeError(f"frame size {actual} != expected {expected}")
        captured = []
        for index in range(args.capture_frames):
            time.sleep(args.capture_interval)
            frame_path = capture_dir / f"frame-{index:03d}.ppm"
            qmp.cmd("screendump", filename=str(frame_path))
            frame = canonicalize_screendump(frame_path)
            if frame[:2] != actual:
                raise RuntimeError(
                    f"animation frame {index} size {frame[:2]} != {actual}"
                )
            nonblack, unique_colors = frame_stats(frame[2])
            if nonblack < args.min_nonblack_pixels:
                raise RuntimeError(
                    f"animation frame {index} is blank: "
                    f"{nonblack} non-black pixels"
                )
            if unique_colors < args.min_unique_colors:
                raise RuntimeError(
                    f"animation frame {index} has too few colors: "
                    f"{unique_colors}"
                )
            captured.append(frame[2])
        if captured:
            hashes = {hashlib.sha256(frame).digest() for frame in captured}
            if len(hashes) < 2:
                raise RuntimeError("captured animation frames did not change")
        for index, input_spec in enumerate(args.input):
            send_input(qmp, input_spec, actual, args.post_input_wait)
            if args.capture_each_input:
                input_path = capture_dir / f"input-{index:03d}.ppm"
                qmp.cmd("screendump", filename=str(input_path))
                input_frame = canonicalize_screendump(input_path)
                if input_frame[:2] != actual:
                    raise RuntimeError(
                        f"input frame {index} size {input_frame[:2]} != {actual}"
                    )
                nonblack, unique_colors = frame_stats(input_frame[2])
                if nonblack < args.min_nonblack_pixels:
                    raise RuntimeError(
                        f"input frame {index} is blank: "
                        f"{nonblack} non-black pixels"
                    )
                if unique_colors < args.min_unique_colors:
                    raise RuntimeError(
                        f"input frame {index} has too few colors: "
                        f"{unique_colors}"
                    )
        qmp.cmd("screendump", filename=str(after))
        for path, prop, raw_expected in args.qom_expect:
            try:
                expected = json.loads(raw_expected)
            except json.JSONDecodeError:
                expected = raw_expected
            current = qmp.cmd(
                "qom-get", path=path, property=prop
            )["return"]
            print(f"qom-expect {path} {prop}={current}")
            if current != expected:
                raise RuntimeError(
                    f"QOM {path}.{prop}={current!r}, expected {expected!r}"
                )
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
        if args.post_frame_color:
            try:
                x_raw, y_raw, color_raw = args.post_frame_color.split(",", 2)
                x = int(x_raw)
                y = int(y_raw)
                expected_color = int(color_raw, 16)
            except ValueError as error:
                raise RuntimeError(
                    f"invalid --post-frame-color {args.post_frame_color!r}"
                ) from error
            width, height = after_frame[:2]
            if not (0 <= x < width and 0 <= y < height):
                raise RuntimeError(
                    f"post-frame pixel ({x},{y}) is outside {width}x{height}"
                )
            offset = (y * width + x) * 3
            actual_color = after_frame[2][offset:offset + 3]
            expected_rgb = bytes(
                (
                    (expected_color >> 16) & 0xff,
                    (expected_color >> 8) & 0xff,
                    expected_color & 0xff,
                )
            )
            if actual_color != expected_rgb:
                raise RuntimeError(
                    f"post-frame pixel ({x},{y}) is "
                    f"{actual_color.hex()}, expected {expected_rgb.hex()}"
                )
        if (not args.allow_static_frame
                and hashlib.sha256(before_frame[2]).digest()
                == hashlib.sha256(after_frame[2]).digest()):
            raise RuntimeError("input did not change the UIFlow2 frame")
        serial_text = serial.read_text(errors="replace")
        missing = [
            marker for marker in args.serial_expect
            if marker not in serial_text
        ]
        if missing:
            raise RuntimeError(
                f"missing serial markers: {', '.join(missing)}"
            )
        serial1_text = serial1.read_text(errors="replace")
        missing = [
            marker for marker in args.serial1_expect
            if marker not in serial1_text
        ]
        if missing:
            raise RuntimeError(
                f"missing UART1 markers: {', '.join(missing)}"
            )
        print(
            f"PASS machine={args.machine} size={actual[0]}x{actual[1]} "
            f"inputs={','.join(args.input)}"
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

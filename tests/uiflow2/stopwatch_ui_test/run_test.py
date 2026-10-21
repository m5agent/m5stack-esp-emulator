#!/usr/bin/env python3
"""Build a StopWatch UIFlow2 test image, boot it in QEMU, and tap the UI.

The test replaces only the user LittleFS files (boot.py/main.py) inside a
merged 16 MiB UIFlow2 image.  The bootloader, application and system
partition are left untouched.
"""
import argparse
import hashlib
import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[3]
VFS_OFFSET = 0x820000
VFS_SIZE = 0x7DF000
FLASH_SIZE = 16 << 20


def make_image(base: Path, out: Path, files: Path) -> None:
    try:
        import littlefs
    except ImportError:
        raise SystemExit("install littlefs-python: python3 -m pip install littlefs-python")

    image = bytearray(base.read_bytes())
    if len(image) != FLASH_SIZE:
        raise SystemExit(f"base image must be exactly {FLASH_SIZE} bytes")

    vfs = image[VFS_OFFSET:VFS_OFFSET + VFS_SIZE]
    fs = littlefs.LittleFS(
        context=littlefs.UserContext(buffer=vfs),
        block_size=4096,
        block_count=VFS_SIZE // 4096,
        read_size=128,
        prog_size=128,
        lookahead_size=256,
        block_cycles=100,
        mount=False,
    )
    fs.mount()
    for name in ("boot.py", "main.py"):
        try:
            fs.remove("/" + name)
        except Exception:
            pass
        with fs.open("/" + name, "w") as f:
            f.write((files / name).read_text())
    fs.unmount()

    image[VFS_OFFSET:VFS_OFFSET + VFS_SIZE] = vfs
    out.write_bytes(image)
    print(f"image: {out}")
    print(f"sha256: {hashlib.sha256(image).hexdigest()}")


class QMP:
    def __init__(self, path: Path):
        self.sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.sock.connect(str(path))
        self.file = self.sock.makefile("rwb")
        self.file.readline()
        self.cmd("qmp_capabilities")

    def cmd(self, name, **args):
        self.file.write((json.dumps({"execute": name, "arguments": args}) + "\n").encode())
        self.file.flush()
        while True:
            line = self.file.readline().decode().strip()
            if not line:
                continue
            reply = json.loads(line)
            if "event" in reply:
                continue
            return reply

    def close(self):
        self.sock.close()


def wait_socket(path: Path, timeout=15):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists():
            try:
                return QMP(path)
            except OSError:
                pass
        time.sleep(0.1)
    raise RuntimeError(f"QMP socket did not appear: {path}")


def ppm_has_pixels(path: Path) -> bool:
    data = path.read_bytes()
    marker = data.find(b"255\n")
    return marker >= 0 and any(data[marker + 4:])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, type=Path,
                        help="official UIFlow2 merged image padded to 16 MiB")
    parser.add_argument("--out-dir", default=Path("/tmp/stopwatch-ui-test"), type=Path)
    parser.add_argument("--qemu", default=PROJECT_ROOT / ".work/M5StopWatch-QEMU/bin/Darwin-arm64/qemu-system-xtensa", type=Path)
    parser.add_argument("--rom-dir", default=PROJECT_ROOT / ".work/M5StopWatch-QEMU/bin/Darwin-arm64", type=Path)
    args = parser.parse_args()

    args.out_dir.mkdir(parents=True, exist_ok=True)
    image = args.out_dir / "uiflow2-ui-test.bin"
    make_image(args.base, image, Path(__file__).parent)

    serial = args.out_dir / "serial.log"
    before = args.out_dir / "before.ppm"
    after = args.out_dir / "after.ppm"
    qmp_path = Path("/tmp") / f"m5-ui-{os.getpid()}.sock"
    try:
        qmp_path.unlink()
    except FileNotFoundError:
        pass

    proc = subprocess.Popen([
        str(args.qemu), "-M", "m5stopwatch",
        "-drive", f"file={image},if=mtd,format=raw",
        "-L", str(args.rom_dir),
        "-display", "none",
        "-serial", f"file:{serial}",
        "-qmp", f"unix:{qmp_path},server=on,wait=off",
    ])
    try:
        qmp = wait_socket(qmp_path)
        time.sleep(10)
        qmp.cmd("screendump", filename=str(before))
        if not ppm_has_pixels(before):
            raise RuntimeError("UIFlow2 test UI did not draw before touch")

        events = [
            {"type": "abs", "data": {"axis": "x", "value": int(233 * 32767 / 465)}},
            {"type": "abs", "data": {"axis": "y", "value": int(348 * 32767 / 465)}},
            {"type": "btn", "data": {"down": True, "button": "left"}},
        ]
        qmp.cmd("input-send-event", events=events)
        time.sleep(0.35)
        events[-1] = {"type": "btn", "data": {"down": False, "button": "left"}}
        qmp.cmd("input-send-event", events=events)
        time.sleep(0.5)
        qmp.cmd("screendump", filename=str(after))
        qmp.close()

        if hashlib.sha256(before.read_bytes()).digest() == hashlib.sha256(after.read_bytes()).digest():
            raise RuntimeError("touch did not change the UIFlow2 UI")
        print(f"PASS before={before} after={after} serial={serial}")
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

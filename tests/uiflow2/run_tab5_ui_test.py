#!/usr/bin/env python3
"""Run the ESP32-P4 Tab5 UIFlow2 virtual-display test through esp-emu."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import signal
import socket
import struct
import subprocess
import time
import zlib
from pathlib import Path

from esp_flash import default_env, flash_with_esp_emu

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_EMU = (
    ROOT
    / ".work/esp-emu-versions/0.50.0/esp-emu-0.50.0-aarch64-apple-darwin/esp-emu"
)
DEFAULT_ROM = ROOT / ".work/roms/esp32p4_rev0_rom.elf"
DEFAULT_EFUSE = ROOT / ".work/efuse/tab5-p4-1.0.efuse"
DEFAULT_C6 = ROOT / "platform/.cache/firmware/tab5-c6/network_adapter-v2.12.6.bin"


def wait_for_path(path: Path, proc: subprocess.Popen, timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if path.exists():
            return
        if proc.poll() is not None:
            raise RuntimeError(f"process exited early with code {proc.returncode}")
        time.sleep(0.1)
    raise RuntimeError(f"timed out waiting for {path}")


def wait_for_port(port: int, proc: subprocess.Popen, timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"process exited early with code {proc.returncode}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"timed out waiting for TCP port {port}")


def wait_for_text(path: Path, marker: str, proc: subprocess.Popen,
                  timeout: float) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        text = path.read_text(errors="replace") if path.exists() else ""
        if marker in text:
            return
        if proc.poll() is not None:
            raise RuntimeError(
                f"process exited before marker {marker!r}, code={proc.returncode}"
            )
        time.sleep(0.15)
    raise RuntimeError(f"timed out waiting for serial marker: {marker}")


def run_gdb(
    *,
    elf: Path,
    gdb_port: int,
    out_dir: Path,
    name: str,
    commands: list[str],
) -> str:
    script = out_dir / f"{name}.gdb"
    script.write_text(
        "\n".join(
            [
                "set pagination off",
                "set confirm off",
                f"target remote host.docker.internal:{gdb_port}",
                *commands,
                "detach",
                "quit",
            ]
        )
        + "\n"
    )
    command = [
        "docker",
        "run",
        "--rm",
        "--add-host=host.docker.internal:host-gateway",
        "-v",
        f"{ROOT}:/workspace:ro",
        "-v",
        f"{elf.parent}:/elfdir:ro",
        "-v",
        f"{out_dir}:/out",
        "-w",
        "/workspace",
        "uiflow-idf:v5.5.4",
        "bash",
        "-lc",
        (
            "riscv32-esp-elf-gdb -q -batch "
            f"-x /out/{script.name} /elfdir/{elf.name}"
        ),
    ]
    result = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
        check=False,
    )
    (out_dir / f"{name}.stdout").write_text(result.stdout)
    (out_dir / f"{name}.stderr").write_text(result.stderr)
    if result.returncode:
        raise RuntimeError(
            f"GDB {name} failed ({result.returncode}): "
            f"{result.stderr[-1200:] or result.stdout[-1200:]}"
        )
    return result.stdout


def capture_framebuffer(
    elf: Path, gdb_port: int, out_dir: Path, name: str
) -> tuple[int, int, bytes, str]:
    dump = out_dir / f"{name}.rgb565"
    stdout = run_gdb(
        elf=elf,
        gdb_port=gdb_port,
        out_dir=out_dir,
        name=name,
        commands=[
            "set $fb = m5_emu_framebuffer",
            "set $w = m5_emu_framebuffer_width",
            "set $h = m5_emu_framebuffer_height",
            'printf "TAB5_GDB_FRAMEBUFFER %p %u %u\\n", $fb, $w, $h',
            f"dump binary memory /out/{dump.name} $fb ($fb + $w * $h * 2)",
        ],
    )
    line = next(
        (row for row in stdout.splitlines() if row.startswith("TAB5_GDB_FRAMEBUFFER ")),
        None,
    )
    if not line:
        raise RuntimeError("GDB did not report the framebuffer metadata")
    _, address, width_text, height_text = line.split()
    width, height = int(width_text), int(height_text)
    pixels = dump.read_bytes()
    expected = width * height * 2
    if len(pixels) != expected:
        raise RuntimeError(f"framebuffer size {len(pixels)} != expected {expected}")
    return width, height, pixels, address


def rgb565_to_rgb(pixels: bytes) -> bytes:
    rgb = bytearray(len(pixels) // 2 * 3)
    output = 0
    for offset in range(0, len(pixels), 2):
        value = pixels[offset] | (pixels[offset + 1] << 8)
        r = ((value >> 11) & 0x1F) * 255 // 31
        g = ((value >> 5) & 0x3F) * 255 // 63
        b = (value & 0x1F) * 255 // 31
        rgb[output:output + 3] = bytes((r, g, b))
        output += 3
    return bytes(rgb)


def orient_rgb565(
    pixels: bytes, raw_width: int, raw_height: int, rotation: int
) -> tuple[int, int, bytes]:
    rotation &= 3
    if rotation == 0:
        return raw_width, raw_height, pixels
    if rotation == 2:
        output = bytearray(len(pixels))
        for y in range(raw_height):
            source_row = (raw_height - 1 - y) * raw_width * 2
            for x in range(raw_width):
                source = source_row + (raw_width - 1 - x) * 2
                target = (y * raw_width + x) * 2
                output[target:target + 2] = pixels[source:source + 2]
        return raw_width, raw_height, bytes(output)

    width, height = raw_height, raw_width
    output = bytearray(len(pixels))
    for raw_y in range(raw_height):
        source_row = raw_y * raw_width * 2
        for raw_x in range(raw_width):
            if rotation == 1:
                x = raw_y
                y = raw_width - 1 - raw_x
            else:
                x = raw_height - 1 - raw_y
                y = raw_x
            source = source_row + raw_x * 2
            target = (y * width + x) * 2
            output[target:target + 2] = pixels[source:source + 2]
    return width, height, bytes(output)


def logical_to_raw_touch(
    x: int, y: int, raw_width: int, raw_height: int, rotation: int
) -> tuple[int, int]:
    rotation &= 3
    if rotation == 0:
        return x, y
    if rotation == 1:
        return raw_width - 1 - y, x
    if rotation == 2:
        return raw_width - 1 - x, raw_height - 1 - y
    return raw_width - 1 - y, raw_height - 1 - x


def frame_stats(pixels: bytes) -> dict:
    nonblack = 0
    colors = set()
    for offset in range(0, len(pixels), 3):
        rgb = pixels[offset:offset + 3]
        if any(rgb):
            nonblack += 1
            if len(colors) < 512:
                colors.add(rgb)
    return {"nonblack_pixels": nonblack, "unique_colors": len(colors)}


def png_chunk(kind: bytes, payload: bytes) -> bytes:
    return (
        struct.pack(">I", len(payload))
        + kind
        + payload
        + struct.pack(">I", zlib.crc32(kind + payload) & 0xFFFFFFFF)
    )


def write_png(path: Path, width: int, height: int, pixels: bytes) -> None:
    rows = bytearray()
    stride = width * 3
    for y in range(height):
        rows.append(0)
        rows.extend(pixels[y * stride:(y + 1) * stride])
    header = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + png_chunk(b"IHDR", header)
        + png_chunk(b"IDAT", zlib.compress(bytes(rows), 9))
        + png_chunk(b"IEND", b"")
    )


def inject_touch(
    elf: Path, gdb_port: int, out_dir: Path, name: str,
    *, down: bool, x: int = 0, y: int = 0,
) -> None:
    run_gdb(
        elf=elf,
        gdb_port=gdb_port,
        out_dir=out_dir,
        name=name,
        commands=[
            f"set {{unsigned int}}&m5_emu_touch_state[0] = {1 if down else 0}",
            f"set {{unsigned int}}&m5_emu_touch_state[1] = {x}",
            f"set {{unsigned int}}&m5_emu_touch_state[2] = {y}",
            "set {unsigned int}&m5_emu_touch_state[3] = 0",
            "set {unsigned int}&m5_emu_touch_state[4] = 18",
            "set {unsigned int}&m5_emu_touch_state[5] = m5_emu_touch_state[5] + 1",
            'printf "TAB5_TOUCH_STATE %u %u %u %u %u %u\\n", '
            "m5_emu_touch_state[0], m5_emu_touch_state[1], "
            "m5_emu_touch_state[2], m5_emu_touch_state[3], "
            "m5_emu_touch_state[4], m5_emu_touch_state[5]",
        ],
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True, type=Path,
                        help="16 MiB merged image produced from the same emulator ELF")
    parser.add_argument("--prebuilt-image", type=Path,
                        help="boot this exact image instead of rebuilding its VFS")
    parser.add_argument("--elf", required=True, type=Path)
    parser.add_argument("--files-dir", type=Path,
                        default=ROOT / "tests/uiflow2/tab5_ui_test")
    parser.add_argument("--out-dir", type=Path,
                        default=Path("/tmp/m5-tab5-ui-test"))
    parser.add_argument("--emulator", type=Path, default=DEFAULT_EMU)
    parser.add_argument("--rom", type=Path, default=DEFAULT_ROM)
    parser.add_argument("--efuse", type=Path, default=DEFAULT_EFUSE)
    parser.add_argument("--c6-firmware", type=Path, default=DEFAULT_C6)
    parser.add_argument("--flash-transport", choices=("host-image", "esptool"),
                        default="host-image")
    parser.add_argument("--flash-chunk-size", type=lambda x: int(x, 0),
                        default=0x100000)
    parser.add_argument("--gdb-port", type=int, default=3333)
    parser.add_argument("--rotation", type=int, choices=(0, 1, 2, 3), default=1)
    parser.add_argument("--expected-size", default="1280x720")
    parser.add_argument("--touch", default="640,520")
    parser.add_argument("--timeout", type=float, default=90)
    args = parser.parse_args()

    required_paths = [
        args.base, args.elf, args.emulator, args.rom, args.efuse,
        args.c6_firmware,
    ]
    if args.prebuilt_image:
        required_paths.append(args.prebuilt_image)
    for path in required_paths:
        if not path.is_file():
            raise SystemExit(f"missing required file: {path}")
    args.out_dir.mkdir(parents=True, exist_ok=True)

    if args.prebuilt_image:
        image = args.prebuilt_image
    else:
        image = args.out_dir / "tab5-ui-test.bin"
        image_env = os.environ.copy()
        image_env["PYTHONPATH"] = os.pathsep.join(
            filter(None, [str(ROOT / ".work/py"), image_env.get("PYTHONPATH", "")])
        )
        subprocess.run(
            [
                "python3",
                str(args.files_dir / "make_image.py"),
                "--base", str(args.base),
                "--out", str(image),
            ],
            cwd=ROOT,
            env=image_env,
            check=True,
        )

    flash_info = {"transport": "host-image", "verified": True}
    run_image = image
    if args.flash_transport == "esptool":
        flash_info = flash_with_esp_emu(
            chip="esp32p4",
            image=image,
            flash_size=16 << 20,
            out_dir=args.out_dir / "flash",
            env=default_env(),
            timeout=args.timeout,
            emulator=args.emulator,
            rom=args.rom,
            efuse=args.efuse,
            extra_args=["--psram-size", "32M"],
            no_stub=True,
            chunk_size=args.flash_chunk_size,
            chunk_ranges=[(0, 0x500000), (0x610000, 0x7F0000)],
            restart_per_chunk=True,
        )
        run_image = Path(flash_info["virtual_flash"])

    socket_path = Path("/tmp") / f"m5-tab5-{os.getpid()}.sock"
    try:
        socket_path.unlink()
    except FileNotFoundError:
        pass

    c6_log = args.out_dir / "c6.log"
    p4_log = args.out_dir / "p4.log"
    c6_handle = c6_log.open("wb")
    c6 = subprocess.Popen(
        [
            str(args.emulator),
            "--chip", "esp32c6",
            "--firmware", str(args.c6_firmware),
            "--hosted", f"bridge:slave:{socket_path}",
            "--net", "user",
        ],
        cwd=ROOT,
        stdout=c6_handle,
        stderr=subprocess.STDOUT,
    )
    p4 = None
    p4_handle = None
    try:
        wait_for_path(socket_path, c6, 20)
        p4_handle = p4_log.open("wb")
        p4 = subprocess.Popen(
            [
                str(args.emulator),
                "--chip", "esp32p4",
                "--firmware", str(run_image),
                "--elf", str(args.elf),
                "--rom", str(args.rom),
                "--efuse", str(args.efuse),
                "--hosted", f"bridge:host:{socket_path}",
                "--hosted-reset-gpio", "15",
                "--hosted-reset-active-high",
                "--psram-size", "32M",
                "--console", "uart0",
                "--gdb", str(args.gdb_port),
                "--timeout", f"{int(args.timeout)}s",
            ],
            cwd=ROOT,
            stdout=p4_handle,
            stderr=subprocess.STDOUT,
        )
        wait_for_port(args.gdb_port, p4, 20)
        wait_for_text(p4_log, "TAB5_UI_DRAWN", p4, args.timeout)

        raw_width, raw_height, raw_before565, address = capture_framebuffer(
            args.elf, args.gdb_port, args.out_dir, "before"
        )
        width, height, before565 = orient_rgb565(
            raw_before565, raw_width, raw_height, args.rotation
        )
        if f"{width}x{height}" != args.expected_size:
            raise RuntimeError(
                f"oriented framebuffer is {width}x{height}, "
                f"expected {args.expected_size}"
            )
        before = rgb565_to_rgb(before565)
        write_png(args.out_dir / "before.png", width, height, before)
        before_stats = frame_stats(before)
        if before_stats["nonblack_pixels"] < 100 or before_stats["unique_colors"] < 3:
            raise RuntimeError(f"initial frame is not a rendered UI: {before_stats}")

        x, y = (int(value) for value in args.touch.split(",", 1))
        raw_x, raw_y = logical_to_raw_touch(
            x, y, raw_width, raw_height, args.rotation
        )
        inject_touch(
            args.elf, args.gdb_port, args.out_dir, "touch-down",
            down=True, x=raw_x, y=raw_y,
        )
        wait_for_text(p4_log, "TAB5_DRAW_AFTER_TOUCH", p4, 20)
        inject_touch(
            args.elf, args.gdb_port, args.out_dir, "touch-up",
            down=False, x=raw_x, y=raw_y,
        )
        time.sleep(0.3)

        after_raw_width, after_raw_height, raw_after565, _ = capture_framebuffer(
            args.elf, args.gdb_port, args.out_dir, "after"
        )
        if (after_raw_width, after_raw_height) != (raw_width, raw_height):
            raise RuntimeError("framebuffer dimensions changed after touch")
        after_width, after_height, after565 = orient_rgb565(
            raw_after565, after_raw_width, after_raw_height, args.rotation
        )
        if (after_width, after_height) != (width, height):
            raise RuntimeError("oriented framebuffer dimensions changed after touch")
        after = rgb565_to_rgb(after565)
        write_png(args.out_dir / "after.png", width, height, after)
        after_stats = frame_stats(after)

        changed = sum(left != right for left, right in zip(before, after))
        if changed == 0:
            raise RuntimeError("touch did not change the framebuffer")

        result = {
            "status": "PASS",
            "machine": "tab5-esp-emu-gdb",
            "size": f"{width}x{height}",
            "raw_framebuffer_size": f"{raw_width}x{raw_height}",
            "rotation": args.rotation,
            "touch_logical": [x, y],
            "touch_raw": [raw_x, raw_y],
            "framebuffer": address,
            "before": before_stats,
            "after": after_stats,
            "changed_channels": changed,
            "image": str(image),
            "image_sha256": hashlib.sha256(image.read_bytes()).hexdigest(),
            "flash": flash_info,
            "serial_markers": ["TAB5_UI_DRAWN", "TAB5_DRAW_AFTER_TOUCH"],
        }
        (args.out_dir / "result.json").write_text(
            json.dumps(result, ensure_ascii=False, indent=2) + "\n"
        )
        print(
            f"PASS machine=tab5-esp-emu-gdb size={width}x{height} "
            f"touch={x},{y} changed={changed}"
        )
    finally:
        for proc in (p4, c6):
            if proc and proc.poll() is None:
                proc.send_signal(signal.SIGINT)
        for proc in (p4, c6):
            if not proc:
                continue
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=5)
        try:
            socket_path.unlink()
        except FileNotFoundError:
            pass
        c6_handle.close()
        if p4_handle:
            p4_handle.close()


if __name__ == "__main__":
    main()

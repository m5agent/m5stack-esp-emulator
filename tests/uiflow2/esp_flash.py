#!/usr/bin/env python3
"""Flash merged images through emulator-backed esptool socket transports."""
from __future__ import annotations

import os
import hashlib
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_ESP_EMU = ROOT / ".work/bin/esp-emu"


def free_local_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_for_port(port: int, proc: subprocess.Popen, timeout: float = 15) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"esp-emu exited early with code {proc.returncode}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.2):
                return
        except OSError:
            time.sleep(0.1)
    raise RuntimeError(f"esp-emu UART port did not open: {port}")


def padded_image(image: Path, flash_size: int) -> bytes:
    data = image.read_bytes()
    if len(data) > flash_size:
        raise ValueError(
            f"image is larger than flash size: {len(data)} > {flash_size}"
        )
    return data + b"\xff" * (flash_size - len(data))


def wait_for_qemu_download(port: int, proc: subprocess.Popen,
                           out_dir: Path, timeout: float = 15) -> None:
    """Observe the real ROM UART download banner before esptool sends SYNC."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            raise RuntimeError(f"QEMU exited before ROM download readiness: {proc.returncode}")
        try:
            peer = socket.create_connection(("127.0.0.1", port), timeout=0.2)
            break
        except OSError:
            time.sleep(0.05)
    else:
        raise RuntimeError("QEMU ROM download UART did not open")
    data = bytearray()
    try:
        peer.settimeout(0.2)
        while time.monotonic() < deadline:
            try:
                chunk = peer.recv(4096)
            except socket.timeout:
                continue
            if not chunk:
                raise RuntimeError("QEMU ROM download UART closed before readiness")
            data.extend(chunk)
            if len(data) > 65536:
                raise RuntimeError("QEMU ROM download banner exceeded 64 KiB")
            if b"UART_BOOT(UART0))\r\n" in data:
                return
        raise RuntimeError("QEMU did not report ROM UART download mode")
    finally:
        peer.close()
        (out_dir / "rom-download.log").write_bytes(data)


def download_protocol_evidence(raw: bytes) -> dict:
    """Summarize actual guest-to-host SLIP replies from QEMU's chardev log."""
    frames, current, escape = [], None, False
    for byte in raw:
        if byte == 0xC0:
            if current:
                frames.append(bytes(current))
            current, escape = bytearray(), False
        elif current is not None:
            if escape:
                if byte not in (0xDC, 0xDD):
                    current, escape = None, False
                    continue
                current.append({0xDC: 0xC0, 0xDD: 0xDB}[byte])
                escape = False
            elif byte == 0xDB:
                escape = True
            else:
                current.append(byte)
    counts = {}
    for frame in frames:
        if (len(frame) >= 8 and frame[0] == 1
                and int.from_bytes(frame[2:4], "little") == len(frame) - 8):
            opcode = f"0x{frame[1]:02x}"
            counts[opcode] = counts.get(opcode, 0) + 1
    return {"stub_ohai": b"OHAI" in frames, "reply_opcodes": counts,
            "uart_log_sha256": hashlib.sha256(raw).hexdigest()}


def flash_with_esp_emu(
    *,
    chip: str,
    image: Path,
    flash_size: int,
    out_dir: Path,
    env: dict[str, str],
    timeout: float = 180,
    emulator: Path = DEFAULT_ESP_EMU,
    rom: Path | None = None,
    efuse: Path | None = None,
    extra_args: list[str] | None = None,
    no_stub: bool = False,
    chunk_size: int | None = None,
    chunk_ranges: list[tuple[int, int]] | None = None,
    restart_per_chunk: bool = False,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    virtual_flash = out_dir / "virtual-flash.bin"
    virtual_flash.write_bytes(b"\xff" * flash_size)
    emu: subprocess.Popen | None = None
    emu_stdout = None
    emu_stderr = None

    def stop_emulator() -> None:
        nonlocal emu, emu_stdout, emu_stderr
        if emu is not None:
            if emu.poll() is None:
                emu.send_signal(signal.SIGINT)
            try:
                emu.wait(timeout=20)
            except subprocess.TimeoutExpired:
                emu.kill()
                emu.wait(timeout=5)
            emu = None
        if emu_stdout is not None:
            emu_stdout.close()
            emu_stdout = None
        if emu_stderr is not None:
            emu_stderr.close()
            emu_stderr = None

    def start_emulator() -> int:
        nonlocal emu, emu_stdout, emu_stderr
        port = free_local_port()
        emu_stdout = (out_dir / "esp-emu.stdout").open("ab")
        emu_stderr = (out_dir / "esp-emu.stderr").open("ab")
        command = [
            str(emulator),
            "--chip", chip,
            "--firmware", str(virtual_flash),
            "--strap-mode", "0x02",
            "--uart-tcp", f"127.0.0.1:{port}",
            "--save-state",
            "--timeout", f"{int(timeout)}s",
        ]
        if rom:
            command.extend(["--rom", str(rom)])
        if efuse:
            command.extend(["--efuse", str(efuse)])
        command.extend(extra_args or [])

        emu = subprocess.Popen(
            command,
            cwd=ROOT,
            env=env,
            stdout=emu_stdout,
            stderr=emu_stderr,
        )
        wait_for_port(port, emu)
        return port

    try:
        writes: list[tuple[int, Path]] = []
        if chunk_ranges:
            data = image.read_bytes()
            for range_start, range_end in chunk_ranges:
                if not 0 <= range_start < range_end <= len(data):
                    raise ValueError(
                        f"invalid chunk range: {range_start:#x}-{range_end:#x}"
                    )
                step = chunk_size or (range_end - range_start)
                for offset in range(range_start, range_end, step):
                    chunk = data[offset:min(offset + step, range_end)]
                    if not any(value != 0xFF for value in chunk):
                        continue
                    chunk_path = out_dir / f"chunk-{offset:08x}.bin"
                    chunk_path.write_bytes(chunk)
                    writes.append((offset, chunk_path))
        elif chunk_size:
            data = image.read_bytes()
            for offset in range(0, len(data), chunk_size):
                chunk = data[offset:offset + chunk_size]
                if not any(value != 0xFF for value in chunk):
                    continue
                chunk_path = out_dir / f"chunk-{offset:08x}.bin"
                chunk_path.write_bytes(chunk)
                writes.append((offset, chunk_path))
        else:
            writes.append((0, image))

        stdout_parts: list[str] = []
        stderr_parts: list[str] = []
        port = start_emulator()
        for write_index, (offset, source) in enumerate(writes):
            if restart_per_chunk and write_index:
                stop_emulator()
                port = start_emulator()
            base_command = [
                sys.executable,
                "-m", "esptool",
                "--port", f"socket://127.0.0.1:{port}",
                "--chip", chip,
                "--before", "no-reset",
                "--after", "no-reset",
            ]
            if no_stub:
                base_command.append("--no-stub")
            command = base_command + [
                "write-flash", hex(offset), str(source)
            ]
            result = subprocess.run(
                command,
                cwd=ROOT,
                env=env,
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
            stdout_parts.append(
                f"== write {offset:#x} {source.name} ==\n{result.stdout}"
            )
            stderr_parts.append(result.stderr)
            if result.returncode:
                (out_dir / "esptool.stdout").write_text("".join(stdout_parts))
                (out_dir / "esptool.stderr").write_text("".join(stderr_parts))
                raise RuntimeError(
                    f"esptool write failed at {offset:#x} "
                    f"({result.returncode}): "
                    f"{result.stderr[-1200:] or result.stdout[-1200:]}"
                )
        (out_dir / "esptool.stdout").write_text("".join(stdout_parts))
        (out_dir / "esptool.stderr").write_text("".join(stderr_parts))
    finally:
        stop_emulator()

    expected = padded_image(image, flash_size)
    actual = virtual_flash.read_bytes()
    if actual != expected:
        first_diff = next(
            (index for index, (left, right) in enumerate(zip(actual, expected))
             if left != right),
            None,
        )
        raise RuntimeError(
            f"virtual flash mismatch after esptool write; first diff={first_diff}"
        )
    return {
        "transport": "esp-emu-esptool",
        "chip": chip,
        "image": str(image),
        "virtual_flash": str(virtual_flash),
        "flash_size": flash_size,
        "verified": True,
    }


class _StubUploadError(RuntimeError):
    """The ROM reached stub upload but did not complete the UART exchange."""

    def __init__(self, message: str, reason: str, uart_log_sha256: str):
        super().__init__(message)
        self.reason = reason
        self.uart_log_sha256 = uart_log_sha256


def flash_with_qemu(
    *,
    chip: str,
    machine: str,
    image: Path,
    flash_size: int,
    out_dir: Path,
    env: dict[str, str],
    qemu: Path,
    rom_dir: Path,
    timeout: float = 180,
    memory: str | None = None,
    no_stub: bool = False,
    baud_scale: int = 16,
) -> dict:
    """Use ROM MEM_DATA to upload stock esptool's guest stub, then write SPI.

    Retry a ROM stub-upload transport failure once with slower UART pacing.
    Each attempt has its own fresh VM and virtual Flash.
    ROM-only FLASH_DATA is retained as an explicit diagnostic option. It is
    not a fallback: that lane has independent checksum/format failures.
    """
    started = time.monotonic()
    settings = dict(chip=chip, machine=machine, image=image, flash_size=flash_size,
                    env=env, qemu=qemu, rom_dir=rom_dir, memory=memory,
                    no_stub=no_stub)
    try:
        return _flash_with_qemu_attempt(
            **settings, out_dir=out_dir, timeout=timeout, baud_scale=baud_scale,
        )
    except _StubUploadError as error:
        remaining = timeout - (time.monotonic() - started)
        if no_stub or baud_scale <= 8 or remaining <= 0:
            raise
        retry_dir = Path(tempfile.mkdtemp(prefix="stub-upload-retry-", dir=out_dir))
        (retry_dir / "first-attempt.txt").write_text(f"baud_scale={baud_scale}\n{error}\n")
        result = _flash_with_qemu_attempt(
            **settings, out_dir=retry_dir, timeout=remaining, baud_scale=8,
        )
        result["protocol"]["first_attempt"] = {
            "baud_scale": baud_scale,
            "phase": "rom-stub-upload",
            "reason": error.reason,
            "uart_log_sha256": error.uart_log_sha256,
        }
        return result


def _flash_with_qemu_attempt(
    *, chip: str, machine: str, image: Path, flash_size: int, out_dir: Path,
    env: dict[str, str], qemu: Path, rom_dir: Path, timeout: float,
    memory: str | None, no_stub: bool, baud_scale: int,
) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    virtual_flash = out_dir / "virtual-flash.bin"
    virtual_flash.write_bytes(b"\xff" * flash_size)
    port = free_local_port()
    uart_log = out_dir / "uart-download.bin"
    command = [
        str(qemu),
        "-M", machine,
        "-drive", f"file={virtual_flash},if=mtd,format=raw",
        "-L", str(rom_dir),
        "-display", "none",
        "-monitor", "none",
        "-chardev", (f"socket,id=download-uart,host=127.0.0.1,port={port},"
                     f"server=on,wait=off,nodelay=on,logfile={uart_log}"),
        "-serial", "chardev:download-uart",
        "-global", "driver=esp32.gpio,property=strap_mode,value=0x0f",
        "-global",
        f"driver=esp_soc.uart,property=baud-scale,value={baud_scale}",
    ]
    if memory is not None:
        command.extend(["-m", str(memory)])

    emu_stdout = (out_dir / "qemu.stdout").open("wb")
    emu_stderr = (out_dir / "qemu.stderr").open("wb")
    emu = subprocess.Popen(
        command,
        cwd=ROOT,
        env=env,
        stdout=emu_stdout,
        stderr=emu_stderr,
    )
    try:
        wait_for_qemu_download(port, emu, out_dir)
        version = subprocess.run(
            [sys.executable, "-m", "esptool", "version"], cwd=ROOT, env=env,
            capture_output=True, text=True, timeout=15, check=False,
        )
        if version.returncode:
            raise RuntimeError("esptool version probe failed: " + version.stderr[-600:])
        tool_version = version.stdout.strip().splitlines()[-1]
        esptool_command = [
            sys.executable,
            "-m", "esptool",
            "--port", f"socket://127.0.0.1:{port}",
            "--chip", chip,
            "--before", "no-reset",
            "--after", "no-reset",
        ]
        if no_stub:
            esptool_command.append("--no-stub")
        image_data = image.read_bytes()
        if len(image_data) > flash_size:
            raise ValueError(
                f"image is larger than flash size: {len(image_data)} > {flash_size}"
            )
        write_size = len(image_data.rstrip(b"\xff"))
        write_image = image
        if write_size < len(image_data):
            write_image = out_dir / "image-without-trailing-ff.bin"
            write_image.write_bytes(image_data[:write_size])
        esptool_command.extend([
            "write-flash", "0x0", str(write_image),
        ])
        result = subprocess.run(
            esptool_command,
            cwd=ROOT,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        (out_dir / "esptool.stdout").write_text(result.stdout)
        (out_dir / "esptool.stderr").write_text(result.stderr)
    finally:
        if emu.poll() is None:
            emu.terminate()
        try:
            emu.wait(timeout=20)
        except subprocess.TimeoutExpired:
            emu.kill()
            emu.wait(timeout=5)
        emu_stdout.close()
        emu_stderr.close()

    protocol = download_protocol_evidence(uart_log.read_bytes())
    if result.returncode:
        message = (
            f"QEMU esptool {tool_version} write failed ({result.returncode}, "
            f"loader={'rom-only' if no_stub else 'stock-stub'}): "
            f"{result.stderr[-1200:] or result.stdout[-1200:]}"
        )
        if (not no_stub and not protocol["stub_ohai"]
                and "0x05" in protocol["reply_opcodes"]
                and "Uploading stub flasher" in result.stdout):
            for pattern, reason in (
                ("Failed to write to target RAM (result was 0107:", "checksum-0107"),
                ("Serial data stream stopped", "serial-stream-stopped"),
            ):
                if pattern in result.stderr:
                    raise _StubUploadError(message, reason, protocol["uart_log_sha256"])
        raise RuntimeError(message)
    if not no_stub and not protocol["stub_ohai"]:
        raise RuntimeError("stock esptool stub OHAI was not observed in the real UART log")
    expected = padded_image(image, flash_size)
    actual = virtual_flash.read_bytes()
    if actual != expected:
        first_diff = next(
            (index for index, (left, right) in enumerate(zip(actual, expected))
             if left != right),
            None,
        )
        raise RuntimeError(
            f"virtual flash mismatch after QEMU esptool write; "
            f"first diff={first_diff}"
        )
    return {
        "transport": "qemu-esptool",
        "chip": chip,
        "machine": machine,
        "image": str(image),
        "virtual_flash": str(virtual_flash),
        "flash_size": flash_size,
        "verified": True,
        "no_stub": no_stub,
        "loader": "rom-only-diagnostic" if no_stub else "stock-esptool-stub",
        "esptool_version": tool_version,
        "runtime_binary_sha256": hashlib.sha256(qemu.read_bytes()).hexdigest(),
        "image_sha256": hashlib.sha256(expected).hexdigest(),
        "readback_sha256": hashlib.sha256(actual).hexdigest(),
        "byte_compare": "equal",
        "rom_download_ready": True,
        "protocol": protocol,
        "baud_scale": baud_scale,
    }


def default_env() -> dict[str, str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = os.pathsep.join(
        filter(None, [
            env.get("M5_PYTHON_DEPS", str(ROOT / ".work/py")),
            env.get("PYTHONPATH", ""),
        ])
    )
    return env

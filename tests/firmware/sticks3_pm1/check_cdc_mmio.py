#!/usr/bin/env python3
"""Check StickS3 USB Serial/JTAG IN timing against the actual QEMU MMIO model."""

import argparse
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import time

USB = 0x60038000

def check(qemu, rom, output):
    sock = output / 'test.sock'
    cdc = output / 'cdc.log'
    with (output / 'qemu.stderr').open('wb') as stderr:
        proc = subprocess.Popen(
            [str(qemu), '-M', 'm5sticks3', '-accel', 'qtest', '-L', str(rom),
             '-display', 'none', '-serial', 'null', '-nic', 'none',
             '-qtest', f'unix:{sock},server=on,wait=off',
             '-chardev', f'file,id=usb-serial-jtag,path={cdc}'],
            stdout=subprocess.DEVNULL, stderr=stderr)
        try:
            end = time.monotonic() + 5
            while not sock.is_socket():
                assert proc.poll() is None and time.monotonic() < end, 'qtest unavailable'
                time.sleep(.02)
            with socket.socket(socket.AF_UNIX) as client:
                client.settimeout(3)
                client.connect(str(sock))
                with client.makefile('rwb', buffering=0) as wire:
                    def cmd(text):
                        wire.write((text + '\n').encode())
                        line = wire.readline().decode().split()
                        assert line[0] == 'OK', (text, line)
                        return int(line[1],0) if len(line) > 1 else None
                    def read(reg):
                        return cmd(f'readl {USB + reg:#x}')
                    def write(reg, value):
                        cmd(f'writel {USB + reg:#x} {value:#x}')
                    def step(ns):
                        return cmd(f'clock_step {ns}')
                    def expect(description, observed, expected):
                        assert observed == expected, (description, observed, expected)
                    expect('initial frame', read(0x24), 0)
                    expect('initial IN-empty', read(0x08), 8)
                    write(0x10, 8)
                    expect('enabled IN-empty', read(0x0c), 8)
                    write(0x04, 1)
                    expect('ZLP is in flight', read(0x04), 0)
                    expect('IN-empty deasserted in flight', read(0x0c), 0)
                    step(7999)
                    expect('ZLP not yet drained', read(0x04), 0)
                    step(1)
                    expect('ZLP drained independently from next SOF', read(0x04), 2)
                    expect('ZLP completion interrupt', read(0x0c), 8)
                    expect('ZLP does not produce file bytes', cdc.read_bytes(), b'')
                    expect('SOF unchanged by ZLP', read(0x24), 0)
                    write(0x14, 8)
                    expect('IN-empty W1C', read(0x0c), 0)
                    message = bytes(range(64))
                    for value in message[:-1]:
                        write(0x00, value)
                    expect('uncommitted FIFO is writable', read(0x04), 2)
                    step(992000)
                    expect('SOF independent of uncommitted packet', read(0x24), 1)
                    expect('SOF is latched', read(0x08), 2)
                    expect('uncommitted bytes stay buffered', cdc.read_bytes(), b'')
                    write(0x14, 2)
                    expect('SOF W1C', read(0x08), 0)
                    write(0x00, message[-1])
                    expect('64 bytes auto-commit', read(0x04), 0)
                    step(63999)
                    expect('data packet still in flight', cdc.read_bytes(), b'')
                    step(1)
                    expect('full packet delivered without WR_DONE', cdc.read_bytes(), message)
                    expect('FIFO writable after host completion', read(0x04), 2)
                    write(0x18, 0)
                    write(0x00, ord('X'))
                    write(0x04, 1)
                    step(2_000_000)
                    expect('detached pad receives no SOF', read(0x24), 1)
                    expect('detached host receives no data', cdc.read_bytes(), message)
                    write(0x18, 0x4200)
                    step(64000)
                    expect('reattach delivers held packet', cdc.read_bytes(), message + b'X')
                    return {'status': 'PASS', 'qemu_sha256': hashlib.sha256(qemu.read_bytes()).hexdigest(),
                            'cdc_sha256': hashlib.sha256(cdc.read_bytes()).hexdigest(),
                            'cdc_bytes': len(cdc.read_bytes())}
        finally:
            if proc.poll() is None:
                proc.terminate()
                try:
                    proc.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait()

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", required=True, type=Path)
    parser.add_argument("--rom-dir", required=True, type=Path)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="cdc-ep1-") as temp:
        result = check(args.qemu.resolve(), args.rom_dir.resolve(), Path(temp))
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

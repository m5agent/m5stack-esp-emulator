#!/usr/bin/env python3
"""Exercise real EXTMEM MMIO and memory regions with CPUs stopped (opt-in)."""
import argparse
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import time


def connect(path, process):
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError("QEMU exited during connection")
        sock = socket.socket(socket.AF_UNIX)
        try:
            sock.connect(str(path))
            sock.settimeout(5)
            return sock, sock.makefile("rwb", buffering=0)
        except OSError:
            sock.close()
            time.sleep(0.05)
    raise TimeoutError(str(path))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--qemu", required=True, type=Path)
    parser.add_argument("--rom-dir", required=True, type=Path)
    parser.add_argument("--out-dir", required=True, type=Path)
    args = parser.parse_args()
    args.out_dir.mkdir(parents=True, exist_ok=True)
    # Deliberately non-executable synthetic flash, never a consumer BIN.
    flash = args.out_dir / "flash.bin"
    flash.write_bytes(b"\x11\x22\x33\x44" * (8 * 1024 * 1024 // 4))
    original_hash = hashlib.sha256(flash.read_bytes()).hexdigest()
    checks = []
    with tempfile.TemporaryDirectory(prefix="m5-occupy-") as tmp:
        tmp = Path(tmp)
        cmd = [str(args.qemu.resolve()), "-M", "m5cardputer", "-m", "0", "-S",
               "-L", str(args.rom_dir.resolve()), "-display", "none", "-serial", "null",
               "-drive", f"file={flash.resolve()},if=mtd,format=raw",
               "-qtest", f"unix:{tmp / 'qtest'},server=on,wait=off",
               "-qtest-log", str((args.out_dir / "qtest.log").resolve()),
               "-qmp", f"unix:{tmp / 'qmp'},server=on,wait=off"]
        with (args.out_dir / "qemu.stderr").open("wb") as err:
            proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=err)
            sockets = []
            try:
                qs, qf = connect(tmp / "qtest", proc)
                ms, mf = connect(tmp / "qmp", proc)
                sockets = [(qs, qf), (ms, mf)]
                json.loads(mf.readline())

                def qmp(name):
                    mf.write((json.dumps({"execute": name}) + "\n").encode())
                    while True:
                        reply = json.loads(mf.readline())
                        if "return" in reply:
                            return reply["return"]
                        if "error" in reply:
                            raise RuntimeError(reply)

                def qtest(command):
                    qf.write((command + "\n").encode())
                    while True:
                        reply = qf.readline().decode().strip()
                        if reply.startswith("IRQ"):
                            continue
                        if not reply.startswith("OK"):
                            raise RuntimeError((command, reply))
                        return reply

                def read(address):
                    return int(qtest(f"readl {address:#x}").split()[1], 16)

                def write(address, value):
                    qtest(f"writel {address:#x} {value:#x}")

                def check(name, condition):
                    if not condition:
                        raise AssertionError(name)
                    checks.append(name)

                qmp("qmp_capabilities")
                ctrl, addr, size = 0x600c4034, 0x600c4038, 0x600c403c
                drom, irom, pattern = 0x3c000000, 0x42000000, 0x44332211
                check("reset_done_address_size", (read(ctrl), read(addr), read(size)) == (2, 0, 0))
                write(ctrl, 0)
                check("done_read_only", read(ctrl) == 2)
                mmu, cache_ctrl = 0x600c5000, 0x600c4000
                write(mmu, 0)  # Real flash page through the existing MMU.
                write(mmu + 4, 1)
                check("flash_mmu_views", read(drom) == pattern and read(irom) == pattern)
                write(cache_ctrl, 9)  # Original BIN: 32 KiB cache, 32-byte lines.
                write(addr, drom)
                write(size, 0xffff0001)
                check("size_mask", read(size) == 1)
                write(ctrl, 0xffffffff)
                check("command_done_ena_reserved", read(ctrl) == 2)
                write(drom, 0xaabbccdd)
                check("mapped_drom_stays_read_only", read(drom) == pattern)
                check("mapped_irom_preserved", read(irom) == pattern)
                underlying = read(drom)
                outside = read(drom + 0x4000)
                write(size, 0x200)  # IDF reserves exactly 16 KiB despite mapped MMU0.
                write(ctrl, 1)
                write(drom, 0xaabbccdd)
                write(drom + 0x3ffc, 0x12345678)
                check("reserved_sram_read_write", read(drom) == 0xaabbccdd and read(drom + 0x3ffc) == 0x12345678)
                check("irom_not_sram", read(irom) == underlying)
                write(drom + 0x4000, 0)
                check("precise_16kb_boundary", read(drom + 0x4000) == outside)
                check("neighbor_mapped_flash_preserved", read(drom + 0x10000) == pattern)
                write(ctrl, 1)
                check("repeat_preserves_sram", read(ctrl) == 2 and read(drom) == 0xaabbccdd)
                for name, address, count in [
                    ("ordinary_mapped_drom", drom + 0x10000, 0x200),
                    ("outside_drom", 0x40000000, 0x400),
                    ("partial_range", drom, 1),
                    ("oversized_range", drom, 0x1000),
                    ("misaligned_range", drom + 1, 0x200),
                    ("empty_range", drom, 0),
                ]:
                    write(addr, address)
                    write(size, count)
                    write(ctrl, 1)
                    check(name + "_does_not_move_sram", read(drom) == 0xaabbccdd and read(drom + 0x10000) == pattern)
                write(drom + 0x10000, 0)
                check("other_occupied_flash_stays_read_only", read(drom + 0x10000) == pattern)
                write(mmu, 0)
                check("new_mmu_mapping_removes_sram", read(drom) == pattern)
                write(addr, drom)
                write(size, 1)
                write(ctrl, 1)
                write(drom, 0)
                check("same_range_mapped_flash_stays_read_only", read(drom) == pattern)
                write(mmu, 0x4000)
                check("unmapping_does_not_restore_stale_sram", read(drom) != 0xaabbccdd)
                write(size, 0x400)
                write(cache_ctrl, 5)  # 64 KiB mode is not the reserved-heap path.
                write(ctrl, 1)
                check("64kb_mode_does_not_reserve_heap", read(drom) != 0xaabbccdd)
                write(cache_ctrl, 9)  # 32-byte lines, same documented 16 KiB area.
                write(size, 0x200)
                write(ctrl, 1)
                write(drom, 0x87654321)
                check("line_count_conversion_and_ctrl_readback", read(cache_ctrl) == 9 and read(drom) == 0x87654321)
                qmp("system_reset")
                check("reset_clears_command_state", (read(ctrl), read(addr), read(size)) == (2, 0, 0))
                check("reset_removes_sram_window", read(drom) != 0x87654321)
                check("flash_image_unchanged", hashlib.sha256(flash.read_bytes()).hexdigest() == original_hash)
            finally:
                for sock, stream in sockets:
                    stream.close()
                    sock.close()
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    proc.wait(timeout=5)
    summary = {"status": "PASS", "lane": "QEMU qtest controller validation; CPUs stopped",
               "qemu_sha256": hashlib.sha256(args.qemu.read_bytes()).hexdigest(),
               "flash_sha256": original_hash, "checks": checks,
               "guest_execution": "NOT RUN in this controller-only probe"}
    (args.out_dir / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()

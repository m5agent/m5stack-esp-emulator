#!/usr/bin/env python3
"""Check the StickS3 USB reset fence against the actual QEMU MMIO model."""
from __future__ import annotations

import argparse
from pathlib import Path
import hashlib
import json
import socket
import subprocess
import tempfile
import time


def digest(file):
    with file.open("rb") as fp:
        return hashlib.file_digest(fp, "sha256").hexdigest()

def probe(qemu: Path, rom: Path, out: Path, expect_fence: bool):
    testpath, qmppath = out / "test.sock", out / "qmp.sock"
    args = [str(qemu), "-M", "m5sticks3", "-display", "none", "-nic", "none",
            "-serial", "null", "-L", str(rom), "-S", "-qtest", f"unix:{testpath},server=on,wait=off",
            "-qmp", f"unix:{qmppath},server=on,wait=off"]
    with (out / "qemu.stderr").open("wb") as err:
        process = subprocess.Popen(args, stdout=subprocess.DEVNULL, stderr=err)
        try:
            deadline = time.monotonic() + 8
            while not (testpath.is_socket() and qmppath.is_socket()):
                if time.monotonic() > deadline or process.poll() is not None:
                    raise RuntimeError("QEMU diagnostic sockets were unavailable")
                time.sleep(0.02)
            with socket.socket(socket.AF_UNIX) as qs, socket.socket(socket.AF_UNIX) as ms:
                qs.settimeout(3)
                ms.settimeout(3)
                qs.connect(str(testpath))
                ms.connect(str(qmppath))
                qf = qs.makefile("rwb", buffering=0)
                mf = ms.makefile("rwb", buffering=0)
                assert "QMP" in json.loads(mf.readline())
                def qmp(execute, args=None):
                    req = {"execute":execute}
                    if args:
                        req["arguments"] = args
                    mf.write(json.dumps(req).encode()+b"\n")
                    while True:
                        raw = json.loads(mf.readline())
                        if "event" not in raw:
                            assert "return" in raw, raw
                            return raw["return"]
                def mmio(command):
                    qf.write((command+"\n").encode())
                    line=qf.readline().decode().strip()
                    assert line.startswith("OK"),line
                    return int(line.split()[1],16) if " " in line else None
                qmp("qmp_capabilities")
                def usb(packet):
                    path="/machine/soc/usb-otg"
                    qmp("qom-set",{"path":path,"property":"host-packet","value":packet})
                    return qmp("qom-get",{"path":path,"property":"host-response"})
                assert mmio("readl 0x60080040") == 0x4f54400a
                mmio("writel 0x6008000c 0x40001440")
                mmio("writel 0x60080804 0x2000")
                assert usb("reset") == "ACK"
                pending = mmio("readl 0x60080014")
                setup = "setup 8006000100001200"
                before = usb(setup)
                before_status = mmio("readl 0x6008001c")
                mmio("writel 0x60080014 0x1000")
                mmio("writel 0x60080010 0x10") # Guest DCD flushes its receive FIFO during USBRST.
                after_flush = mmio("readl 0x6008001c")
                half = usb(setup)
                mmio("writel 0x60080010 0x10") # Clear the negative-control injection.
                mmio("writel 0x60080014 0x2000")
                after = usb(setup)
                status = mmio("readl 0x60080020")
                words = [mmio("readl 0x60081000"),mmio("readl 0x60081000")]
                assert pending & 0x3000 == 0x3000 and after_flush == 0
                assert after == "ACK" and status == 0xc0080 and words == [0x01000680,0x00120000]
                expected_response = "NAK" if expect_fence else "ACK"
                assert before == half == expected_response
                assert before_status == (0 if expect_fence else 0xc0080)
                return {"qemu_sha256":digest(qemu),"reset_and_enum_pending":hex(pending),
                        "early_setup":before,"setup_while_enum_pending":half,
                        "early_fifo_status":hex(before_status),
                        "fifo_status_after_reset_flush":hex(after_flush),
                        "setup_after_ack":after,"fifo_words":[hex(w) for w in words]}
        finally:
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            testpath.unlink(missing_ok=True)
            qmppath.unlink(missing_ok=True)

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", required=True, type=Path)
    parser.add_argument("--rom-dir", required=True, type=Path)
    parser.add_argument("--unfenced-qemu", type=Path, help="Optional 0172-era negative control")
    args = parser.parse_args()
    results = {}
    with tempfile.TemporaryDirectory(prefix="usb-fence-") as directory:
        root = Path(directory)
        if args.unfenced_qemu:
            before = root / "before"
            before.mkdir()
            results["unfenced"] = probe(
                args.unfenced_qemu.resolve(), args.rom_dir.resolve(), before, False
            )
        after = root / "after"
        after.mkdir()
        results["fenced"] = probe(args.qemu.resolve(), args.rom_dir.resolve(), after, True)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()

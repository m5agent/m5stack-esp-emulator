#!/usr/bin/env python3
"""Verify classic ESP32 BT low-power and modem clock registers via QEMU qtest."""

import argparse
import hashlib
import json
from pathlib import Path
import socket
import subprocess
import tempfile
import time


DIV_INT = 0x3FF000D4
DIV_FRAC = 0x3FF000D8
WIFI_CLK_EN = 0x3FF000CC
WIFI_CLK_RESET = 0xFFFCE030
PHY_REQUIRED_CLOCKS = 0x8F8F
RESET_VALUES = (0x000000FF, 0x02001001)
WRITABLE_MASKS = (0x00001FFF, 0x0FFFFFFF)
XTAL_DIVIDER = 79
XTAL_SELECT = 1 << 26
RC_FAST_SELECT = 1 << 25


def connect(path, process):
    deadline = time.monotonic() + 8
    while not path.is_socket():
        if process.poll() is not None or time.monotonic() >= deadline:
            raise RuntimeError(f"QEMU did not open {path.name}")
        time.sleep(0.02)
    client = socket.socket(socket.AF_UNIX)
    client.settimeout(5)
    try:
        client.connect(str(path))
    except OSError:
        client.close()
        raise
    return client


def request_reset(qmp):
    if "QMP" not in json.loads(qmp.readline()):
        raise RuntimeError("missing QMP greeting")
    reset_seen = False
    for command in ("qmp_capabilities", "system_reset"):
        qmp.write(json.dumps({"execute": command, "id": command}).encode() + b"\n")
        while True:
            response = json.loads(qmp.readline())
            reset_seen |= response.get("event") == "RESET"
            if response.get("id") == command:
                if "return" not in response:
                    raise RuntimeError(f"QMP {command} failed: {response}")
                break
    # QEMU can send RESET either before or after the system_reset reply.
    while not reset_seen:
        reset_seen = json.loads(qmp.readline()).get("event") == "RESET"


def sample(test, qmp, expected_bt_clock, expected_wifi_clock):
    def mmio(command):
        test.write((command + "\n").encode())
        reply = test.readline().decode().split()
        if not reply or reply[0] != "OK":
            raise RuntimeError(f"qtest {command} failed: {reply}")
        return int(reply[1], 0) if len(reply) == 2 else None

    def read_pair():
        return tuple(mmio(f"readl {address:#x}") for address in (DIV_INT, DIV_FRAC))

    def write_pair(integer, fractional):
        mmio(f"writel {DIV_INT:#x} {integer:#x}")
        mmio(f"writel {DIV_FRAC:#x} {fractional:#x}")

    def read_wifi():
        return mmio(f"readl {WIFI_CLK_EN:#x}")

    def write_wifi(value):
        mmio(f"writel {WIFI_CLK_EN:#x} {value:#x}")

    wifi_reset = read_wifi()
    write_wifi(wifi_reset | PHY_REQUIRED_CLOCKS)
    wifi_phy_enabled = read_wifi()
    write_wifi(0xFFFFFFFF)
    wifi_all_ones = read_wifi()
    write_wifi(0)
    wifi_cleared = read_wifi()
    reset = read_pair()
    frac = (reset[1] & ~RC_FAST_SELECT) | XTAL_SELECT
    write_pair(XTAL_DIVIDER, frac)
    xtal = read_pair()
    write_pair(0xFFFFFFFF, 0xFFFFFFFF)
    masked = read_pair()
    write_pair(0, 0)
    cleared = read_pair()
    write_pair(XTAL_DIVIDER, frac)
    request_reset(qmp)
    after_reset = read_pair()
    observed = {
        "power_on": reset,
        "xtal_readback": xtal,
        "all_ones_readback": masked,
        "cleared": cleared,
        "after_system_reset": after_reset,
    }
    expected = {
        "power_on": RESET_VALUES,
        "xtal_readback": (XTAL_DIVIDER, 0x04001001),
        "all_ones_readback": WRITABLE_MASKS,
        "cleared": (0, 0),
        "after_system_reset": RESET_VALUES,
    }
    if not expected_bt_clock:
        expected = dict.fromkeys(expected, (0, 0))
    if observed != expected:
        raise AssertionError(f"unexpected DPORT registers: {observed} != {expected}")
    wifi_observed = {
        "power_on": wifi_reset,
        "phy_clocks_readback": wifi_phy_enabled,
        "all_ones_readback": wifi_all_ones,
        "cleared": wifi_cleared,
        "after_system_reset": read_wifi(),
    }
    wifi_expected = {
        "power_on": WIFI_CLK_RESET,
        "phy_clocks_readback": WIFI_CLK_RESET | PHY_REQUIRED_CLOCKS,
        "all_ones_readback": 0xFFFFFFFF,
        "cleared": 0,
        "after_system_reset": WIFI_CLK_RESET,
    }
    if not expected_wifi_clock:
        wifi_expected = dict.fromkeys(wifi_expected, 0)
    if wifi_observed != wifi_expected:
        raise AssertionError(f"unexpected DPORT modem clock: {wifi_observed} != {wifi_expected}")
    return {
        "bt_lp_clock": {
            key: [f"{value:#010x}" for value in values] for key, values in observed.items()
        },
        "wifi_clock_enable": {key: f"{value:#010x}" for key, value in wifi_observed.items()},
    }


def check(qemu, rom_dir, expected_bt_clock, expected_wifi_clock):
    with tempfile.TemporaryDirectory(prefix="m5-bt-lpck-") as temporary:
        root = Path(temporary)
        test_path, qmp_path = root / "qtest.sock", root / "qmp.sock"
        command = [
            str(qemu), "-M", "m5stickcplus2", "-S", "-L", str(rom_dir),
            "-display", "none", "-serial", "null", "-nic", "none",
            "-qtest", f"unix:{test_path},server=on,wait=off",
            "-qmp", f"unix:{qmp_path},server=on,wait=off",
        ]
        with (root / "qemu.stderr").open("wb") as stderr:
            process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=stderr)
            try:
                with (
                    connect(test_path, process) as test_socket,
                    connect(qmp_path, process) as qmp_socket,
                    test_socket.makefile("rwb", buffering=0) as test,
                    qmp_socket.makefile("rwb", buffering=0) as qmp,
                ):
                    result = sample(test, qmp, expected_bt_clock, expected_wifi_clock)
            except (OSError, RuntimeError) as error:
                detail = (root / "qemu.stderr").read_text(errors="replace")[-4000:]
                raise RuntimeError(f"{error}\n{detail}") from error
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
    with qemu.open("rb") as binary:
        result["qemu_sha256"] = hashlib.file_digest(binary, "sha256").hexdigest()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", required=True, type=Path)
    parser.add_argument("--rom-dir", required=True, type=Path)
    parser.add_argument("--unpatched-qemu", type=Path, help="optional pre-0195 control")
    parser.add_argument("--bt-clock-only-qemu", type=Path, help="optional 0195-only control")
    args = parser.parse_args()
    rom_dir = args.rom_dir.resolve()
    result = {}
    if args.unpatched_qemu:
        result["unpatched"] = check(args.unpatched_qemu.resolve(), rom_dir, False, False)
    if args.bt_clock_only_qemu:
        result["bt_clock_only"] = check(args.bt_clock_only_qemu.resolve(), rom_dir, True, False)
    result["patched"] = check(args.qemu.resolve(), rom_dir, True, True)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

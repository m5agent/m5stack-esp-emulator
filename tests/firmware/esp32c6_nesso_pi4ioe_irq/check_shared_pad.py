"""Exercise the Nesso PI4IOE and touch GPIO3 pad through real I2C and QMP."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import time


I2C = 0x60004000
I2C_CONTROL = I2C + 0x04
I2C_STATUS = I2C + 0x08
I2C_FIFO_CONTROL = I2C + 0x18
I2C_FIFO = I2C + 0x1C
I2C_IRQ_RAW = I2C + 0x20
I2C_IRQ_CLEAR = I2C + 0x24
I2C_COMMAND = I2C + 0x58
GPIO_IN = 0x6009103C
GPIO_SYS_IRQ = 1 << 3

PI4IOE1, PI4IOE2, TOUCH = 0x43, 0x44, 0x38
DEVICE_ID, DIRECTION, INPUT_DEFAULT = 0x01, 0x03, 0x09
INPUT_STATUS, INTERRUPT_MASK, INTERRUPT_STATUS = 0x0F, 0x11, 0x13
BUTTON_A, BUTTON_B = 1, 2

RESTART = 6 << 11
STOP = 2 << 11
WRITE = (1 << 11) | (1 << 8)
READ_ONE_WITH_NACK = (3 << 11) | (1 << 10) | 1


def connect(path, process):
    deadline = time.monotonic() + 5
    sock = socket.socket(socket.AF_UNIX)
    sock.settimeout(5)
    try:
        while process.poll() is None and time.monotonic() < deadline:
            try:
                sock.connect(str(path))
                return sock
            except (FileNotFoundError, ConnectionRefusedError):
                time.sleep(0.02)
    except BaseException:
        sock.close()
        raise
    sock.close()
    raise RuntimeError(f"QEMU did not open {path.name}")


class NessoProbe:
    def __init__(self, qtest, qmp):
        self.qtest = qtest
        self.qmp = qmp
        assert "QMP" in json.loads(qmp.readline())
        self.request("qmp_capabilities")
        assert self.request("query-status")["running"]

    def request(self, name, **arguments):
        self.qmp.write(json.dumps({"execute": name, "arguments": arguments}).encode() + b"\n")
        while True:
            reply = json.loads(self.qmp.readline())
            if "return" in reply:
                return reply["return"]
            if "error" in reply:
                raise RuntimeError(f"{name}: {reply['error']}")

    def command(self, words):
        self.qtest.write((words + "\n").encode())
        response = self.qtest.readline().decode().split()
        if not response or response[0] != "OK":
            raise RuntimeError(f"qtest {words}: {response}")
        return int(response[1], 0) if len(response) == 2 else None

    def read(self, address):
        return self.command(f"readl {address:#x}")

    def write(self, address, value):
        self.command(f"writel {address:#x} {value:#x}")

    def transaction(self, outgoing, commands, *, read_byte=False):
        self.write(I2C_FIFO_CONTROL, (1 << 12) | (1 << 13))
        self.write(I2C_IRQ_CLEAR, 0xFFFFFFFF)
        for byte in outgoing:
            self.write(I2C_FIFO, byte)
        for index, command in enumerate(commands):
            self.write(I2C_COMMAND + 4 * index, command)
        self.write(I2C_CONTROL, (1 << 4) | (1 << 5))
        interrupts = self.read(I2C_IRQ_RAW)
        assert interrupts & (1 << 7) and not interrupts & (1 << 10), hex(interrupts)
        count = (self.read(I2C_STATUS) >> 8) & 0x3F
        assert count == int(read_byte), count
        return self.read(I2C_FIFO) if read_byte else None

    def get(self, slave, register):
        return self.transaction((slave << 1, register, (slave << 1) | 1),
                                (RESTART, WRITE | 2, RESTART, WRITE | 1,
                                 READ_ONE_WITH_NACK, STOP), read_byte=True)

    def put(self, slave, register, value):
        self.transaction((slave << 1, register, value), (RESTART, WRITE | 3, STOP))

    def pad(self):
        return bool(self.read(GPIO_IN) & GPIO_SYS_IRQ)

    def key(self, qcode, down):
        self.request("input-send-event", events=[{"type": "key", "data": {
            "key": {"type": "qcode", "data": qcode}, "down": down}}])

    def touch(self, down):
        self.request("input-send-event", events=[
            {"type": "abs", "data": {"axis": "x", "value": 12000}},
            {"type": "abs", "data": {"axis": "y", "value": 17000}},
            {"type": "btn", "data": {"button": "left", "down": down}},
        ])


def checks(dev):
    assert dev.get(PI4IOE1, DEVICE_ID) & 0xFC == 0xA0
    assert dev.get(PI4IOE2, DEVICE_ID) & 0xFC == 0xA0
    for address in (PI4IOE1, PI4IOE2):
        dev.put(address, DIRECTION, 0)
        dev.put(address, INPUT_DEFAULT, 0x03 if address == PI4IOE1 else 0)
        dev.put(address, INTERRUPT_MASK, 0)
        dev.get(address, INTERRUPT_STATUS)
    assert dev.pad()
    assert dev.get(PI4IOE1, INPUT_STATUS) & 3 == 3

    cases = {}
    dev.key("b", True)
    cases["unmasked_press_pulls_pad_low"] = not dev.pad()
    cases["input_status_is_live_and_does_not_clear_pad"] = (
        dev.get(PI4IOE1, INPUT_STATUS) & 3 == BUTTON_A and not dev.pad()
    )
    value = dev.get(PI4IOE1, INTERRUPT_STATUS)
    cases["status_read_returns_bit_and_releases_pad"] = value == BUTTON_B and dev.pad()
    dev.key("b", True)
    cases["same_level_does_not_retrigger"] = dev.get(PI4IOE1, INTERRUPT_STATUS) == 0
    dev.key("b", False)
    cases["return_to_default_does_not_latch"] = dev.get(PI4IOE1, INTERRUPT_STATUS) == 0
    dev.key("b", True)
    cases["second_away_transition_rearms"] = not dev.pad() and dev.get(PI4IOE1, INTERRUPT_STATUS) == BUTTON_B
    dev.get(PI4IOE1, INTERRUPT_STATUS)
    dev.key("b", False)
    dev.get(PI4IOE1, INTERRUPT_STATUS)

    dev.put(PI4IOE1, INTERRUPT_MASK, BUTTON_B)
    dev.key("b", True)
    masked_high = dev.pad()
    dev.put(PI4IOE1, INTERRUPT_MASK, 0)
    unmasked_low = not dev.pad()
    dev.put(PI4IOE1, INTERRUPT_MASK, BUTTON_B)
    remasked_high = dev.pad()
    value = dev.get(PI4IOE1, INTERRUPT_STATUS)
    cases["mask_gates_pad_without_destroying_pending"] = (
        masked_high and unmasked_low and remasked_high and value == BUTTON_B
    )
    dev.key("b", False)
    dev.get(PI4IOE1, INTERRUPT_STATUS)
    dev.put(PI4IOE1, INTERRUPT_MASK, 0)

    dev.put(PI4IOE1, DIRECTION, BUTTON_B)
    dev.key("b", True)
    cases["output_does_not_latch_external_transition"] = (
        dev.pad() and dev.get(PI4IOE1, INPUT_STATUS) & BUTTON_B == 0
        and dev.get(PI4IOE1, INTERRUPT_STATUS) == 0
    )
    dev.key("b", False)
    dev.put(PI4IOE1, DIRECTION, 0)
    dev.get(PI4IOE1, INTERRUPT_STATUS)

    dev.put(PI4IOE1, INPUT_DEFAULT, BUTTON_B)
    dev.get(PI4IOE1, INTERRUPT_STATUS)
    dev.key("a", True)
    cases["default_low_means_press_is_return_to_default"] = (
        dev.pad() and dev.get(PI4IOE1, INTERRUPT_STATUS) == 0
    )
    dev.key("a", False)
    value = dev.get(PI4IOE1, INTERRUPT_STATUS)
    cases["default_low_means_release_is_away_transition"] = value == BUTTON_A and dev.pad()
    dev.put(PI4IOE1, INPUT_DEFAULT, 3)
    dev.get(PI4IOE1, INTERRUPT_STATUS)

    dev.key("b", True)
    dev.touch(True)
    touch_count = dev.get(TOUCH, 0x02)
    other_status = dev.get(PI4IOE2, INTERRUPT_STATUS)
    cases["touch_and_expander_share_active_low_pad"] = touch_count == 1 and not dev.pad()
    cases["second_expander_does_not_consume_first_pending"] = (
        other_status == 0 and dev.get(PI4IOE1, INTERRUPT_STATUS) == BUTTON_B
    )
    cases["reading_pi4ioe_cannot_release_active_touch"] = not dev.pad()
    dev.key("b", False)
    dev.get(PI4IOE1, INTERRUPT_STATUS)
    dev.touch(False)
    cases["both_released_pull_pad_high"] = dev.pad() and dev.get(TOUCH, 0x02) == 0
    dev.key("b", True)
    dev.touch(True)
    dev.touch(False)
    cases["touch_release_cannot_clear_active_pi4ioe"] = not dev.pad()
    dev.get(PI4IOE1, INTERRUPT_STATUS)
    dev.key("b", False)

    dev.touch(True)
    dev.put(PI4IOE2, DEVICE_ID, 1)
    dev.get(PI4IOE2, INTERRUPT_STATUS)
    cases["second_expander_reset_and_read_do_not_release_touch"] = not dev.pad()
    dev.touch(False)
    dev.get(PI4IOE1, INTERRUPT_STATUS)
    dev.key("b", True)
    dev.put(PI4IOE1, DEVICE_ID, 1)
    cases["software_reset_clears_pending_and_restores_defaults"] = (
        dev.pad() and dev.get(PI4IOE1, INTERRUPT_STATUS) == 0
        and dev.get(PI4IOE1, DIRECTION) == 0 and dev.get(PI4IOE1, INPUT_DEFAULT) == 0
        and dev.get(PI4IOE1, INTERRUPT_MASK) == 0
    )
    return cases


def write_wait_fixture(path):
    # ELF32 RISC-V with an 8-byte RX segment in on-chip SRAM. No C toolchain,
    # firmware drivers, peripheral writes or ROM startup path are required.
    entry = 0x40800000
    elf_ident = b"\x7fELF\x01\x01\x01" + bytes(9)
    header = struct.pack("<16sHHIIIIIHHHHHH", elf_ident, 2, 243, 1, entry,
                         52, 0, 0, 52, 32, 1, 0, 0, 0)
    segment = struct.pack("<IIIIIIII", 1, 0x100, entry, entry, 8, 8, 5, 4)
    # wfi; jal x0, -4
    program = struct.pack("<II", 0x10500073, 0xFFDFF06F)
    path.write_bytes((header + segment).ljust(0x100, b"\x00") + program)


def run(binary, rom_dir):
    with tempfile.TemporaryDirectory(prefix="nesso-pi4ioe-") as directory:
        root = Path(directory)
        qtest, qmp, log = root / "test.sock", root / "qmp.sock", root / "qemu.log"
        flash = root / "erased-flash.bin"
        flash.write_bytes(b"\xff" * (8 * 1024 * 1024))
        kernel = root / "wait.elf"
        write_wait_fixture(kernel)
        command = [str(binary), "-M", "esp32c6", "-accel", "tcg,thread=single",
                   "-L", str(rom_dir), "-kernel", str(kernel),
                   "-drive", f"file={flash},if=mtd,format=raw",
                   "-display", "none", "-serial", "null", "-nic", "none",
                   "-qtest", f"unix:{qtest},server=on,wait=off",
                   "-qmp", f"unix:{qmp},server=on,wait=off"]
        with log.open("wb") as stderr:
            proc = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=stderr,
                                    env={**os.environ, "M5SW_C6_BOARD": "nesso-n1"})
            try:
                with (connect(qtest, proc) as test_socket, connect(qmp, proc) as qmp_socket,
                      test_socket.makefile("rwb", buffering=0) as test,
                      qmp_socket.makefile("rwb", buffering=0) as monitor):
                    board = NessoProbe(test, monitor)
                    result = checks(board)
                    cpu = board.request("human-monitor-command", **{"command-line": "info registers"})
                    lines = [line.split() for line in cpu.splitlines()]
                    pc = [int(words[1], 16) for words in lines if words and words[0] == "pc"]
                    assert pc in ([0x40800000], [0x40800004]), cpu
                    return result, sha(kernel)
            except (OSError, RuntimeError, ValueError, AssertionError) as error:
                detail = log.read_text(errors="replace")[-4000:]
                raise RuntimeError(f"{error}\n{detail}") from error
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()


def sha(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--qemu", type=lambda path: Path(path).resolve(), required=True)
    parser.add_argument("--rom-dir", type=lambda path: Path(path).resolve(), required=True)
    parser.add_argument("--baseline", action="store_true")
    args = parser.parse_args()
    observed, fixture_sha256 = run(args.qemu, args.rom_dir)
    assert len(observed) == 17
    failed = {name for name, value in observed.items() if not value}
    if args.baseline:
        assert failed == {
            "unmasked_press_pulls_pad_low",
            "input_status_is_live_and_does_not_clear_pad",
            "return_to_default_does_not_latch",
            "second_away_transition_rearms",
            "mask_gates_pad_without_destroying_pending",
            "output_does_not_latch_external_transition",
            "default_low_means_press_is_return_to_default",
            "reading_pi4ioe_cannot_release_active_touch",
            "touch_release_cannot_clear_active_pi4ioe",
        }, failed
    else:
        assert not failed, failed
    print(json.dumps({"status": "PASS", "baseline": args.baseline,
                      "runtime_sha256": sha(args.qemu),
                      "rom_sha256": sha(args.rom_dir / "esp32c6-rom.bin"),
                      "synthetic_guest": "SRAM WFI/JAL loop",
                      "fixture_elf_sha256": fixture_sha256,
                      "cpu_interrupt_delivery": "NOT RUN",
                      "observations": observed}, indent=2))


if __name__ == "__main__":
    main()

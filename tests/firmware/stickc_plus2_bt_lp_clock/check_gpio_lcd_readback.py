"""Probe the physical Plus2 GPIO wiring through actual QEMU MMIO."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from check_mmio import connect, request_reset


GPIO = 0x3FF44000
IOMUX = 0x3FF49000
PINS = {5: 0x6C, 13: 0x38, 14: 0x30, 15: 0x3C}
CS, SCK, DC, SDA = PINS


def verify(test, qmp, expected_id, machine):
    def command(words):
        test.write((words + '\n').encode())
        reply = test.readline().decode().split()
        if not reply or reply[0] != 'OK':
            raise RuntimeError(f'qtest {words} failed: {reply}')
        return int(reply[1], 0) if len(reply) >= 2 else None

    def write(address, value):
        command(f'writel {address:#x} {value:#x}')

    def pin_level(pin, high):
        write(GPIO + (0x08 if high else 0x0C), 1 << pin)

    def direction(pin, output, *, input_enabled=True):
        write(IOMUX + PINS[pin], (2 << 12) | (int(input_enabled) << 9))
        write(GPIO + 0x530 + pin * 4, 256)
        write(GPIO + (0x24 if output else 0x28), 1 << pin)

    def initialize():
        for pin in PINS:
            pin_level(pin, pin == CS)
            direction(pin, True)

    def clock():
        pin_level(SCK, True)
        pin_level(SCK, False)

    def send(byte, size=8):
        for bit in range(7, 7 - size, -1):
            pin_level(SDA, (byte >> bit) & 1)
            clock()

    def read_word():
        result = 0
        for byte in range(4):
            value = 0
            for _ in range(8):
                value = (value << 1) | ((command(f'readl {GPIO + 0x3C:#x}') >> SDA) & 1)
                clock()
            result |= value << (byte * 8)
        return result

    def select():
        direction(SDA, True)
        pin_level(DC, False)
        pin_level(CS, False)

    def turnaround():
        pin_level(DC, True)
        direction(SDA, False)
        clock()

    def deselect():
        pin_level(CS, True)

    initialize()
    report = {}
    send(4)
    turnaround()
    report['cs_high_ignores_command'] = read_word()
    assert report['cs_high_ignores_command'] == 0xFFFFFFFF

    select()
    send(0x05)
    turnaround()
    report['different_command_no_id'] = read_word()
    assert report['different_command_no_id'] == 0xFFFFFFFF
    deselect()

    select()
    pin_level(DC, True)
    send(0x04)
    turnaround()
    report['data_phase_no_id'] = read_word()
    assert report['data_phase_no_id'] == 0xFFFFFFFF
    deselect()

    select()
    send(4, size=7)
    deselect()
    select()
    clock()
    turnaround()
    report['partial_command_discarded'] = read_word()
    assert report['partial_command_discarded'] == 0xFFFFFFFF
    deselect()

    select()
    send(4)
    pin_level(DC, True)
    pin_level(SDA, False)
    clock()
    report['host_still_drives_no_panel_response'] = read_word()
    assert report['host_still_drives_no_panel_response'] == 0
    deselect()

    select()
    send(4)
    turnaround()
    report['gpio_rddid'] = read_word()
    assert report['gpio_rddid'] == expected_id, hex(report['gpio_rddid'])
    deselect()
    assert read_word() == 0xFFFFFFFF

    select()
    send(4)
    pin_level(DC, True)
    direction(SDA, False, input_enabled=False)
    clock()
    report['disabled_host_receiver_no_reply'] = read_word()
    assert report['disabled_host_receiver_no_reply'] == 0xFFFFFFFF
    deselect()

    select()
    send(4)
    pin_level(DC, True)
    # A peripheral route with software OE set is not known to be high-Z.
    # With an open-drain high latch the old GPIO receiver still exposes an
    # external low, so this independently detects unintended panel drive.
    pin_level(SDA, True)
    write(GPIO + 0x88 + SDA * 4, 1 << 2)
    write(GPIO + 0x530 + SDA * 4, (1 << 10) | 1)
    clock()
    report['active_unknown_route_no_reply'] = read_word()
    assert report['active_unknown_route_no_reply'] == 0xFFFFFFFF
    deselect()
    write(GPIO + 0x88 + SDA * 4, 0)

    select()
    send(4)
    pin_level(DC, True)
    direction(SDA, False)
    report['without_turnaround_no_bit_yet'] = (command(f'readl {GPIO + 0x3C:#x}') >> SDA) & 1
    assert report['without_turnaround_no_bit_yet'] == 1
    clock()
    report['reselected_rddid'] = read_word()
    assert report['reselected_rddid'] == expected_id, hex(report['reselected_rddid'])
    deselect()

    select()
    send(4)
    turnaround()
    deselect()
    report['cs_release_mid_reply'] = read_word()
    assert report['cs_release_mid_reply'] == 0xFFFFFFFF

    select()
    send(4)
    turnaround()
    direction(SDA, True)
    pin_level(SDA, True)
    report['host_reclaims_sda_mid_reply'] = read_word()
    assert report['host_reclaims_sda_mid_reply'] == 0xFFFFFFFF
    deselect()

    select()
    send(4)
    turnaround()
    request_reset(qmp)
    initialize()
    select()
    turnaround()
    report['reset_releases_active_reply'] = read_word()
    assert report['reset_releases_active_reply'] == 0xFFFFFFFF
    deselect()

    if machine == 'm5stickcplus2':
        # Separate transfer through VSPI FIFO with the same GPIO chip select
        # and D/C. This register path existed before GPIO readback support.
        spi = 0x3FF65000
        select()
        write(spi + 0x80, 4)
        write(spi + 0x28, 7)
        write(spi + 0x1C, 1 << 27)
        write(spi, 1 << 18)
        pin_level(DC, True)
        write(spi + 0x2C, 31)
        write(spi + 0x1C, 1 << 28)
        write(spi, 1 << 18)
        report['hardware_spi_rddid'] = command(f'readl {spi + 0x80:#x}')
        assert report['hardware_spi_rddid'] == 0x85, hex(report['hardware_spi_rddid'])
        deselect()

    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', type=Path, required=True)
    parser.add_argument('--rom-dir', type=Path, required=True)
    parser.add_argument('--machine', choices=('m5stickcplus2', 'm5core2'), default='m5stickcplus2')
    parser.add_argument('--expected-id', type=lambda value: int(value, 0), required=True)
    args = parser.parse_args()
    with args.qemu.open('rb') as binary:
        runtime = hashlib.file_digest(binary, 'sha256').hexdigest()
    with tempfile.TemporaryDirectory(prefix='m5-plus2-gpio-panel-') as temporary:
        root = Path(temporary)
        test_path, qmp_path = root / 'test.sock', root / 'qmp.sock'
        argv = [str(args.qemu.resolve()), '-M', args.machine, '-accel', 'qtest',
                '-L', str(args.rom_dir.resolve()), '-display', 'none', '-serial', 'null', '-nic', 'none',
                '-qtest', f'unix:{test_path},server=on,wait=off',
                '-qmp', f'unix:{qmp_path},server=on,wait=off']
        with (root / 'stderr').open('wb') as stderr:
            proc = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=stderr)
            try:
                with (connect(test_path, proc) as sock, connect(qmp_path, proc) as qmp_sock,
                      sock.makefile('rwb', buffering=0) as test,
                      qmp_sock.makefile('rwb', buffering=0) as qmp):
                    print(json.dumps({'runtime_sha256': runtime,
                                      'machine': args.machine,
                                      'checks': verify(test, qmp, args.expected_id, args.machine)}, indent=2))
            finally:
                if proc.poll() is None:
                    proc.terminate()
                    try:
                        proc.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()


if __name__ == '__main__':
    main()

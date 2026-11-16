"""Exercise the ST7789V2 GPIO wiring through actual QEMU MMIO."""

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from check_mmio import connect, request_reset


MACHINES = ('m5stickcplus2', 'm5core2', 'm5cardputer', 'm5cardputeradv')


def verify(test, qmp, expected_id, machine):
    s3 = machine in ('m5cardputer', 'm5cardputeradv')
    if s3:
        gpio, iomux = 0x60004000, 0x60009000
        pins = {pin: (pin + 1) * 4 for pin in (37, 36, 34, 35)}
        bank, output_select, pin_config, mux_function = 4, 0x554, 0x74, 1
    else:
        gpio, iomux = 0x3FF44000, 0x3FF49000
        pins = {5: 0x6C, 13: 0x38, 14: 0x30, 15: 0x3C}
        bank, output_select, pin_config, mux_function = 0, 0x530, 0x88, 2
    cs, sck, dc, sda = pins

    def command(words):
        test.write((words + '\n').encode())
        reply = test.readline().decode().split()
        if not reply or reply[0] != 'OK':
            raise RuntimeError(f'qtest {words} failed: {reply}')
        return int(reply[1], 0) if len(reply) >= 2 else None

    def write(address, value):
        command(f'writel {address:#x} {value:#x}')

    bank_offset = 0x0C if s3 else 0

    def pin_level(pin, high):
        write(gpio + bank_offset + (0x08 if high else 0x0C), 1 << (pin % 32))

    def direction(pin, output, *, input_enabled=True):
        write(iomux + pins[pin], (mux_function << 12) | (int(input_enabled) << 9))
        write(gpio + output_select + pin * 4, 256)
        write(gpio + bank_offset + (0x24 if output else 0x28), 1 << (pin % 32))

    def read_bit():
        return (command(f'readl {gpio + bank + 0x3C:#x}') >> (sda % 32)) & 1

    def initialize():
        for pin in pins:
            pin_level(pin, pin == cs)
            direction(pin, True)

    def clock():
        pin_level(sck, True)
        pin_level(sck, False)

    def send(byte, size=8):
        for bit in range(7, 7 - size, -1):
            pin_level(sda, (byte >> bit) & 1)
            clock()

    def read_word():
        result = 0
        for byte in range(4):
            value = 0
            for _ in range(8):
                value = (value << 1) | read_bit()
                clock()
            result |= value << (byte * 8)
        return result

    def select():
        direction(sda, True)
        pin_level(dc, False)
        pin_level(cs, False)

    def turnaround():
        pin_level(dc, True)
        direction(sda, False)
        clock()

    def deselect():
        pin_level(cs, True)

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
    pin_level(dc, True)
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
    pin_level(dc, True)
    pin_level(sda, False)
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
    pin_level(dc, True)
    direction(sda, False, input_enabled=False)
    clock()
    report['disabled_host_receiver_no_reply'] = read_word()
    assert report['disabled_host_receiver_no_reply'] == (0 if s3 else 0xFFFFFFFF)
    deselect()

    select()
    send(4)
    pin_level(dc, True)
    # A peripheral route with software OE set is not known to be high-Z.
    # With an open-drain high latch the old GPIO receiver still exposes an
    # external low, so this independently detects unintended panel drive.
    pin_level(sda, True)
    write(gpio + pin_config + sda * 4, 1 << 2)
    write(gpio + output_select + sda * 4, (1 << 10) | 1)
    clock()
    report['active_unknown_route_no_reply'] = read_word()
    assert report['active_unknown_route_no_reply'] == 0xFFFFFFFF
    deselect()
    write(gpio + pin_config + sda * 4, 0)

    select()
    send(4)
    pin_level(dc, True)
    direction(sda, False)
    report['without_turnaround_no_bit_yet'] = read_bit()
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
    direction(sda, True)
    pin_level(sda, True)
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

    if s3:
        spi = 0x60025000
        select()
        write(spi + 0x98, 4)
        write(spi + 0x1C, 7)
        write(spi + 0x10, 1 << 27)
        write(spi, 1 << 24)
        pin_level(dc, True)
        write(spi + 0x1C, 31)
        write(spi + 0x10, 1 << 28)
        write(spi, 1 << 24)
        report['hardware_spi_rddid'] = command(f'readl {spi + 0x98:#x}')
        assert report['hardware_spi_rddid'] == 0x81, hex(report['hardware_spi_rddid'])
        deselect()
    elif machine == 'm5stickcplus2':
        # Separate transfer through VSPI FIFO with the same GPIO chip select
        # and D/C. This register path existed before GPIO readback support.
        spi = 0x3FF65000
        select()
        write(spi + 0x80, 4)
        write(spi + 0x28, 7)
        write(spi + 0x1C, 1 << 27)
        write(spi, 1 << 18)
        pin_level(dc, True)
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
    parser.add_argument('--machine', choices=MACHINES, default='m5stickcplus2')
    parser.add_argument('--expected-id', type=lambda value: int(value, 0), required=True)
    args = parser.parse_args()
    with args.qemu.open('rb') as binary:
        runtime = hashlib.file_digest(binary, 'sha256').hexdigest()
    with tempfile.TemporaryDirectory(prefix='m5-gpio-panel-') as temporary:
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

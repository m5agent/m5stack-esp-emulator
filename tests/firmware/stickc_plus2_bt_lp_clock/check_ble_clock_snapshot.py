#!/usr/bin/env python3
"""Exercise sampled classic ESP32 BLE clock on paused qtest machines."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile


from check_mmio import connect, request_reset


BASE = 0x3FF7121C
FINE = 0x3FF71220
BT_BASE = 0x3FF7101C
SAMP = 1 << 31
WRAP_US = (1 << 27) * 625


def clock_checks(test, qmp):
    def command(words):
        test.write((words + '\n').encode())
        reply = test.readline().decode().split()
        if not reply or reply[0] != 'OK':
            raise RuntimeError(f'qtest {words} failed: {reply}')
        return int(reply[1], 0) if len(reply) >= 2 else None

    def read_pair():
        return tuple(command(f'readl {address:#x}') for address in (BASE, FINE))

    def sample(value=SAMP):
        command(f'writel {BASE:#x} {value:#x}')
        return read_pair()

    assert command('clock_step 0') == 0
    result = {'power_on': read_pair(), 'first_sample': sample()}
    now = command('clock_set 156000')
    assert now == 156000, now
    result['held_across_time'] = read_pair()
    result['phase_above_467'] = sample()
    assert command('clock_step 1000') == 157000
    result['phase_at_467'] = sample()
    command(f'writel {FINE:#x} 0xffffffff')
    result['write_without_samp'] = sample(0x7FFFFFFF)
    command(f'writeb {BASE + 3:#x} 0xff')
    command(f'writew {FINE:#x} 0xffff')
    result['partial_writes'] = read_pair()
    result['fine_low_byte'] = command(f'readb {FINE:#x}')
    result['fine_high_byte'] = command(f'readb {FINE + 1:#x}')
    assert command('clock_set 624000') == 624000
    result['before_slot_boundary'] = sample(0xFFFFFFFF)
    assert command('clock_step 1000') == 625000
    result['held_across_slot_boundary'] = read_pair()
    result['after_slot_boundary'] = sample()
    result['classic_bank_at_slot_boundary'] = command(f'readl {BT_BASE:#x}')
    assert command(f'clock_set {(WRAP_US - 1) * 1000}') == (WRAP_US - 1) * 1000
    result['before_coarse_wrap'] = sample()
    assert command('clock_step 1000') == WRAP_US * 1000
    result['after_coarse_wrap'] = sample()
    assert command('clock_step 250000') == (WRAP_US + 250) * 1000
    result['before_reset'] = sample()
    request_reset(qmp)
    result['reset_latch'] = read_pair()
    result['reset_epoch_sample'] = sample()
    return result


def check(qemu, rom, expected):
    with tempfile.TemporaryDirectory(prefix='m5-ble-clock-') as temporary:
        root = Path(temporary)
        test_path, qmp_path = root / 'qtest.sock', root / 'qmp.sock'
        argv = [str(qemu), '-M', 'm5stickcplus2', '-accel', 'qtest', '-L', str(rom),
                '-display', 'none', '-serial', 'null', '-nic', 'none',
                '-qtest', f'unix:{test_path},server=on,wait=off',
                '-qmp', f'unix:{qmp_path},server=on,wait=off']
        # The qtest accelerator runs no CPUs. Leave its virtual clock enabled.
        with (root / 'stderr').open('wb') as stderr:
            process = subprocess.Popen(argv, stdout=subprocess.DEVNULL, stderr=stderr)
            try:
                with (connect(test_path, process) as qtest_socket,
                      connect(qmp_path, process) as qmp_socket,
                      qtest_socket.makefile('rwb', buffering=0) as test,
                      qmp_socket.makefile('rwb', buffering=0) as qmp):
                    result = clock_checks(test, qmp)
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=5)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
    if expected:
        oracle = {'power_on': (0, 0), 'first_sample': (0, 624), 'held_across_time': (0, 624),
                  'phase_above_467': (0, 468), 'phase_at_467': (0, 467),
                  'write_without_samp': (0, 467), 'partial_writes': (0, 467),
                  'fine_low_byte': 211, 'fine_high_byte': 1, 'before_slot_boundary': (0, 0),
                  'held_across_slot_boundary': (0, 0), 'after_slot_boundary': (1, 624),
                  'classic_bank_at_slot_boundary': 625,
                  'before_coarse_wrap': ((1 << 27) - 1, 0), 'after_coarse_wrap': (0, 624),
                  'before_reset': (0, 374), 'reset_latch': (0, 0), 'reset_epoch_sample': (0, 624)}
        if result != oracle:
            raise AssertionError(f'BLE snapshots differ: {result} != {oracle}')
    else:
        assert result['first_sample'] == (0, 0)
        assert result['held_across_time'] == (156, 0)
        assert result['phase_at_467'] == (157, 0)
        assert result['after_slot_boundary'] == (625, 0xFFFF)
    with qemu.open('rb') as binary:
        result['qemu_sha256'] = hashlib.file_digest(binary, 'sha256').hexdigest()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--rom-dir', type=Path, required=True)
    args = parser.parse_args()
    report = {'baseline': check(args.baseline.resolve(), args.rom_dir.resolve(), False),
              'candidate': check(args.candidate.resolve(), args.rom_dir.resolve(), True)}
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()

"""Verify classic ESP32 RWBT modem reset and preserved reset domains."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile

from check_mmio import connect, request_reset


RWBT = 0x3FF71000
DPORT = 0x3FF00000
RWBT_SOURCE = 1 << 6
SLEEP = 1 << 15
IRQ = 1 << 2


def verify(test, qmp, baseline=False):
    def command(words):
        test.write((words + '\n').encode())
        reply = test.readline().decode().split()
        if not reply or reply[0] != 'OK':
            raise RuntimeError(f'qtest {words} failed: {reply}')
        return int(reply[1], 0) if len(reply) >= 2 else None

    def read(addr):
        return command(f'readl {addr:#x}')

    def write(addr, value):
        return command(f'writel {addr:#x} {value:#x}')

    def step(ns):
        return command(f'clock_step {ns}')

    def status():
        return [read(RWBT + offset) for offset in (0x0c, 0x14, 0x10, 0x30, 0x38)] + [read(DPORT + 0xec) & RWBT_SOURCE]

    def sleep_and_correct():
        write(DPORT + 0xd4, 79)
        write(DPORT + 0xd8, 1 << 26)
        write(RWBT + 0x34, 1)
        write(RWBT + 0x30, 7)
        step(2000)
        write(RWBT + 0x18, IRQ)
        write(RWBT + 0x30, 0xb)

    report = {}
    reset_reg = DPORT + 0xd0
    rtc_options0 = 0x3ff48000
    rtc_reset_state = 0x3ff48034
    assert read(reset_reg) == 0
    sleep_and_correct()
    write(RWBT + 0xc, 1 | 0x200)
    write(RWBT + 0xb8, 10)
    step(625000)
    assert status() == [0x201, 1, 1, 3, 1, RWBT_SOURCE]
    write(reset_reg, 1 << 3)
    report['unrelated_btbb_reset'] = status()
    assert report['unrelated_btbb_reset'] == [0x201, 1, 1, 3, 1, RWBT_SOURCE]
    assert read(reset_reg) == (0 if baseline else 1 << 3)
    write(reset_reg, 0)
    write(rtc_options0, read(rtc_options0) | (1 << 4))
    for _ in range(8):
        if (read(rtc_reset_state) >> 6) & 63 == 12:
            break
    assert (read(rtc_reset_state) >> 6) & 63 == 12
    report['cpu_only_reset'] = status()
    assert report['cpu_only_reset'] == [0x201, 1, 1, 3, 1, RWBT_SOURCE]
    write(reset_reg, 0x7ff)
    if baseline:
        report['ignored_original_modem_reset'] = status()
        assert report['ignored_original_modem_reset'] == report['cpu_only_reset']
        assert read(reset_reg) == 0
        write(reset_reg, 0)
        step(6250000)
        report['stale_fine_and_slot_irq_after_reboot_pulse'] = status()
        assert report['stale_fine_and_slot_irq_after_reboot_pulse'] == [0x201, 0x201, 0x201, 3, 1, RWBT_SOURCE]
        return report

    assert read(reset_reg) == 0x7ff
    report['asserted_combined_reset'] = status()
    assert report['asserted_combined_reset'] == [0, 0, 0, 0, 0, 0]
    write(RWBT + 0xc, 0xffffffff)
    write(RWBT + 0xb8, 0)
    write(RWBT + 0x34, 1)
    write(RWBT + 0x30, 7)
    assert read(RWBT + 0x34) == read(RWBT + 0xb8) == 0
    write(reset_reg, 0)
    assert read(reset_reg) == 0
    write(rtc_options0, read(rtc_options0) | (1 << 5))
    assert read(rtc_reset_state) & 63 == 12
    step(6250000)
    report['post_reboot_no_stale_irq'] = status()
    assert report['post_reboot_no_stale_irq'] == [0, 0, 0, 0, 0, 0]
    assert read(DPORT + 0xd4) == 79
    assert read(DPORT + 0xd8) == 1 << 26
    sleep_and_correct()
    write(RWBT + 0xc, 1)
    step(625000)
    report['fresh_slot_after_reprogramming'] = status()
    assert report['fresh_slot_after_reprogramming'] == [1, 1, 1, 3, 1, RWBT_SOURCE]

    # MAC-only reset preserves active sleep, wake and the low-power clock.
    write(RWBT + 0x18, 0xffffffff)
    write(RWBT + 0xc, IRQ | 0x200)
    write(RWBT + 0xb8, 0x4000)
    write(RWBT + 0x34, 100)
    write(RWBT + 0x30, 7)
    step(100000)
    write(reset_reg, 1 << 9)
    report['mac_reset_preserves_active_lp_clock'] = status()
    assert report['mac_reset_preserves_active_lp_clock'] == [IRQ, 0, 0, SLEEP | 7, 50, 0]
    assert read(RWBT + 0xb8) == 0
    step(100000)
    report['lp_wake_during_mac_reset'] = status()
    assert report['lp_wake_during_mac_reset'] == [IRQ, IRQ, IRQ, 3, 100, RWBT_SOURCE]
    write(reset_reg, 0)
    write(RWBT + 0x18, IRQ)
    write(RWBT + 0x30, 0xb)
    write(RWBT + 0xc, 1 | IRQ)
    step(625000)
    # LP-only reset clears LP wake and preset and retains the active MAC IRQ.
    write(RWBT + 0x3c, 0xabcdef)
    assert status() == [5, 1, 1, 3, 100, RWBT_SOURCE]
    write(reset_reg, 1 << 10)
    report['lp_reset_preserves_active_mac_irq'] = status()
    assert report['lp_reset_preserves_active_mac_irq'] == [1, 1, 1, 0, 0, RWBT_SOURCE]
    assert read(RWBT + 0x3c) == 0
    write(reset_reg, 0)
    # Moving the reset assertion between domains in one DPORT write never
    # asserts both. It must not reset the shared half-slot clock epoch.
    step(10000000)
    write(RWBT + 0x1c, 1 << 31)
    before_swap = read(RWBT + 0x1c)
    assert before_swap > 16
    write(reset_reg, 1 << 10)
    write(reset_reg, 1 << 9)
    assert read(reset_reg) == 1 << 9
    write(reset_reg, 1 << 10)
    assert read(reset_reg) == 1 << 10
    write(reset_reg, 0)
    write(RWBT + 0x1c, 1 << 31)
    report['atomic_domain_swaps'] = [before_swap, read(RWBT + 0x1c)]
    assert report['atomic_domain_swaps'] == [before_swap, before_swap]
    request_reset(qmp)
    assert status() == [0, 0, 0, 0, 0, 0]
    assert read(reset_reg) == 0 and read(DPORT + 0xd4) == 255
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', type=Path, required=True)
    parser.add_argument('--rom-dir', type=Path, required=True)
    parser.add_argument('--baseline', action='store_true',
                        help='reproduce the ignored DPORT reset on the frozen 0200 runtime')
    args = parser.parse_args()
    with args.qemu.open('rb') as binary:
        runtime = hashlib.file_digest(binary, 'sha256').hexdigest()
    with tempfile.TemporaryDirectory(prefix='m5-rwbt-reset-') as temporary:
        root = Path(temporary)
        test_path, qmp_path = root / 'test.sock', root / 'qmp.sock'
        argv = [str(args.qemu.resolve()), '-M', 'm5stickcplus2', '-accel', 'qtest',
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
                                      'controls': verify(test, qmp, args.baseline)}, indent=2))
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

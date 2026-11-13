"""Exercise a BR/EDR low-power timer on the classic ESP32 QEMU address space."""
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
GROSS_IRQ = 1 << 10
GROSS_MASK = (1 << 23) - 1


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

    def regs():
        return [read(RWBT + offset) for offset in (0x30, 0x38, 0x14, 0x10)] + [read(DPORT + 0xec) & RWBT_SOURCE]

    def sample_clock():
        write(RWBT + 0x1c, 1 << 31)
        return [read(RWBT + 0x1c), read(RWBT + 0x20)]

    if baseline:
        write(DPORT + 0xd4, 79)
        write(DPORT + 0xd8, 1 << 26)
        write(DPORT + 0x11c, 25)
        write(RWBT + 0x0c, IRQ)
        write(RWBT + 0x34, 100)
        write(RWBT + 0x30, 7)
        before = regs()
        step(200000)
        expired = regs()
        assert before == expired == [7, 0, 0, 0, 0], (before, expired)
        assert read(RWBT + 0x0c) == IRQ | 0x200
        return {'missing_sleep_state_and_irq': expired,
                'interrupt_mask_with_forced_bit9': read(RWBT + 0x0c)}

    report = {}
    assert read(RWBT + 0x0c) == 0
    assert sample_clock() == [0, 624]
    step(312500)
    assert sample_clock() == [1, 312]
    step(123)
    assert [read(RWBT + 0x1c), read(RWBT + 0x20)] == [1, 312]
    step(312377)
    assert sample_clock() == [2, 624]
    assert regs() == [0, 0, 0, 0, 0]
    write(DPORT + 0xd4, 79)
    write(DPORT + 0xd8, 1 << 26)
    write(DPORT + 0x11c, 25)
    write(RWBT + 0x30, SLEEP)
    assert regs() == [0, 0, 0, 0, 0]
    write(RWBT + 0x34, 100)
    write(RWBT + 0x30, 7)
    report['sleep_entry'] = regs()
    assert report['sleep_entry'] == [SLEEP | 7, 0, 0, 0, 0]
    step(199000)
    report['before_deadline'] = regs()
    assert report['before_deadline'] == [SLEEP | 7, 99, 0, 0, 0]
    step(1000)
    report['expiry_masked'] = regs()
    assert report['expiry_masked'] == [3, 100, IRQ, 0, 0]
    write(RWBT + 0x0c, IRQ)
    report['unmasked'] = regs()
    assert report['unmasked'] == [3, 100, IRQ, IRQ, RWBT_SOURCE]
    write(RWBT + 0x18, 2)
    assert regs() == report['unmasked']
    write(RWBT + 0x18, IRQ)
    report['ack'] = regs()
    assert report['ack'] == [3, 100, 0, 0, 0]
    assert sample_clock() == [2, 624]
    write(RWBT + 0x40, 425)
    write(RWBT + 0x44, 1 << 31)
    write(RWBT + 0x30, 0xb)
    assert sample_clock() == [2, 424]
    step(424999)
    assert sample_clock() == [3, 0]
    assert regs() == [3, 100, 0, 0, 0]
    step(1)
    assert sample_clock() == [4, 624]
    report['masked_slot_irq'] = regs()
    assert report['masked_slot_irq'] == [3, 100, 1, 0, 0]
    write(RWBT + 0x0c, IRQ | 1)
    report['slot_irq_unmasked'] = regs()
    assert report['slot_irq_unmasked'] == [3, 100, 1, 1, RWBT_SOURCE]
    write(RWBT + 0x18, 1)
    assert regs() == [3, 100, 0, 0, 0]
    write(RWBT + 0x0c, IRQ)
    write(RWBT + 0x34, 2000)
    write(RWBT + 0x30, 0x80000007)
    step(2500)
    write(RWBT + 0x30, 0x80000017)
    assert regs() == [0x80008007, 1, 0, 0, 0]
    step(1500)
    report['soft_wake'] = regs()
    assert report['soft_wake'] == [0x80000003, 2, IRQ, IRQ, RWBT_SOURCE]
    write(RWBT + 0x18, IRQ)
    write(RWBT + 0x40, 621)
    write(RWBT + 0x30, 0xb)
    write(RWBT + 0x34, 100)
    write(RWBT + 0x30, 7)
    assert regs() == [SLEEP | 7, 0, 0, 0, 0]
    request_reset(qmp)
    report['reset'] = regs()
    assert report['reset'] == [0, 0, 0, 0, 0]
    step(200000)
    assert regs() == report['reset']

    # Program a 27-bit modulo-slot compare two slots after reset.
    write(RWBT + 0xb8, 0xf8000002)
    assert read(RWBT + 0xb8) == 2
    step(1049999)
    assert regs() == [0, 0, 0, 0, 0]
    step(1)
    report['fine_target_raw'] = regs()
    assert report['fine_target_raw'] == [0, 0, 0x200, 0, 0]
    write(RWBT + 0x0c, 0x200)
    report['fine_target_unmasked'] = regs()
    assert report['fine_target_unmasked'] == [0, 0, 0x200, 0x200, RWBT_SOURCE]
    write(RWBT + 0x18, 0x200)
    assert regs() == [0, 0, 0, 0, 0]
    # Place the running controller one slot below rollover using its clock
    # correction interface, without fast-forwarding other SoC timers by 23h.
    write(DPORT + 0xd4, 79)
    write(DPORT + 0xd8, 1 << 26)
    write(RWBT + 0x34, 1)
    write(RWBT + 0x30, 7)
    step(2000)
    write(RWBT + 0x18, 4)
    write(RWBT + 0x40, 0)
    write(RWBT + 0x44, (1 << 31) | (((1 << 27) - 3) * 2))
    write(RWBT + 0x30, 0xb)
    assert sample_clock() == [0x0ffffffe, 624]
    write(RWBT + 0xb8, 1)
    step(1249999)
    assert regs() == [3, 1, 1, 0, 0]
    step(1)
    assert sample_clock() == [2, 624]
    report['fine_target_after_wrap'] = regs()
    assert report['fine_target_after_wrap'] == [3, 1, 0x201, 0x200, RWBT_SOURCE]

    # Keep the gross compare in BR/EDR, with a full 16-slot period and the
    # same DPORT source as the slot and fine-target interrupts.
    write(RWBT + 0x18, 0x201)
    write(RWBT + 0x0c, GROSS_IRQ)
    write(RWBT + 0xb4, 0xff800002)
    assert read(RWBT + 0xb4) == 2
    write(RWBT + 0xb4, 1)
    step(9374999)
    assert regs() == [3, 1, 1, 0, 0]
    step(1)
    report['gross_target_reprogrammed'] = regs()
    assert report['gross_target_reprogrammed'] == [3, 1, 1 | GROSS_IRQ, GROSS_IRQ, RWBT_SOURCE]
    write(RWBT + 0x0c, 0)
    report['gross_target_masked'] = regs()
    assert report['gross_target_masked'] == [3, 1, 1 | GROSS_IRQ, 0, 0]
    write(RWBT + 0x18, 1)
    assert regs() == [3, 1, GROSS_IRQ, 0, 0]
    write(RWBT + 0x18, GROSS_IRQ)
    assert regs() == [3, 1, 0, 0, 0]

    # Move the clock just below gross wrap through the correction registers.
    # A zero target is real and should fire at wrap, without a 23-hour step.
    write(RWBT + 0x34, 1)
    write(RWBT + 0x30, 7)
    step(2000)
    write(RWBT + 0x18, 4)
    write(RWBT + 0x44, (1 << 31) | (((1 << 27) - 17) * 2))
    write(RWBT + 0x30, 0xb)
    assert sample_clock() == [0x0ffffffe, 624]
    write(RWBT + 0xb4, 0)
    write(RWBT + 0x0c, GROSS_IRQ)
    step(624999)
    assert regs() == [3, 1, 0, 0, 0]
    step(1)
    report['gross_target_after_wrap'] = regs()
    assert sample_clock() == [0, 624]
    assert report['gross_target_after_wrap'] == [3, 1, 1 | GROSS_IRQ, GROSS_IRQ, RWBT_SOURCE]
    write(RWBT + 0x18, 1 | GROSS_IRQ)
    write(RWBT + 0xb4, GROSS_MASK)
    assert read(RWBT + 0xb4) == GROSS_MASK
    write(RWBT + 0xb4, 1)
    step(2000000)
    assert regs() == [3, 1, 1, 0, 0]
    write(RWBT + 0x18, 1)
    write(RWBT + 0x34, 100)
    write(RWBT + 0x30, 7)
    step(200000)
    # The high-speed clock stays frozen until the guest applies correction.
    step(10000000)
    assert regs() == [3, 100, IRQ, 0, 0]
    write(RWBT + 0x18, IRQ)
    write(RWBT + 0x40, 425)
    write(RWBT + 0x44, 1 << 31)
    write(RWBT + 0x30, 0xb)
    step(7799999)
    assert regs() == [3, 100, 1, 0, 0]
    step(1)
    report['gross_target_after_sleep_correction'] = regs()
    assert report['gross_target_after_sleep_correction'] == [3, 100, 1 | GROSS_IRQ, GROSS_IRQ, RWBT_SOURCE]

    # Once a sleep interval starts, its period follows the sampled DPORT
    # clock and divider. A subsequent interval uses the new clock selection.
    write(RWBT + 0x18, 1 | GROSS_IRQ)
    write(RWBT + 0x0c, IRQ)
    write(DPORT + 0xd4, 79)
    write(DPORT + 0xd8, 1 << 26)
    write(RWBT + 0x34, 10)
    write(RWBT + 0x30, 7)
    step(5000)
    write(DPORT + 0xd4, 7)
    write(DPORT + 0xd8, 1 << 25)
    write(RWBT + 0x34, 1)
    assert read(RWBT + 0x34) == 10
    step(14999)
    assert regs() == [SLEEP | 7, 9, 0, 0, 0]
    step(1)
    report['running_sleep_uses_entry_clock'] = regs()
    assert report['running_sleep_uses_entry_clock'] == [3, 10, IRQ, IRQ, RWBT_SOURCE]
    write(RWBT + 0x18, IRQ)
    write(RWBT + 0x40, 0)
    write(RWBT + 0x44, 0)
    write(RWBT + 0x30, 0xb)
    write(RWBT + 0x34, 10)
    write(RWBT + 0x30, 7)
    step(9999)
    assert regs() == [SLEEP | 7, 9, 0, 0, 0]
    step(1)
    report['next_sleep_uses_updated_clock'] = regs()
    assert report['next_sleep_uses_updated_clock'] == [3, 10, IRQ, IRQ, RWBT_SOURCE]
    write(RWBT + 0x18, IRQ)
    write(RWBT + 0x30, 0xb)

    # An unsupported multiple-clock selection cannot synthesize a wake.
    write(DPORT + 0xd8, (1 << 25) | (1 << 26))
    write(RWBT + 0x30, 7)
    report['multiple_sleep_sources_rejected'] = regs()
    assert report['multiple_sleep_sources_rejected'] == [3, 10, 0, 0, 0]
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--qemu', type=Path, required=True)
    parser.add_argument('--rom-dir', type=Path, required=True)
    parser.add_argument('--baseline', action='store_true',
                        help='reproduce the missing timer on a build before patch 0200')
    args = parser.parse_args()
    with args.qemu.open('rb') as binary:
        runtime = hashlib.file_digest(binary, 'sha256').hexdigest()
    with tempfile.TemporaryDirectory(prefix='m5-rwbt-clock-') as temporary:
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

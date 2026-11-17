"""Exercise offline admission and report parsing without requiring retained assets."""

import base64
from pathlib import Path
import struct
import unittest
import zlib

from decode_esp32_coredump import task_summary, uart_dump, validate_dump
from device_service_crash import crash_console_observations, serial_crash_observations
from esp32_uart_coredump import decode_task_contexts


def make_note(name, kind, description):
    padded_name = name.ljust((len(name) + 3) & ~3, b"\0")
    padded_description = description.ljust((len(description) + 3) & ~3, b"\0")
    return struct.pack("<3I", len(name), len(description), kind) + padded_name + padded_description


def make_dump(notes):
    elf = bytearray(52)
    elf[:7] = b"\x7fELF\x01\x01\x01"
    struct.pack_into("<HH", elf, 16, 4, 94)  # ET_CORE, EM_XTENSA
    struct.pack_into("<I", elf, 28, 52)
    struct.pack_into("<HH", elf, 42, 32, 1)
    elf.extend(struct.pack("<8I", 4, 84, 0, 0, len(notes), 0, 0, 0))
    elf.extend(notes)
    data = struct.pack("<6I", 24 + len(elf) + 4, 0x0102, 0, 0, 0, 0) + elf
    checksum = zlib.crc32(data)
    return data + struct.pack("<I", checksum)


def make_app_note():
    note_desc = struct.pack("<I", 0x0102) + b"1916d0ba9".ljust(64, b"\0")
    return make_note(b"ESP_CORE_DUMP_INFO\0", 8266, note_desc)


def make_task_note(tcb, pc, sp):
    description = bytearray(588)
    struct.pack_into("<I", description, 24, tcb)
    struct.pack_into("<I", description, 72, pc)
    struct.pack_into("<I", description, 332, sp)
    return make_note(b"CORE\0", 1, description)


def make_extra_note(crashed_tcb):
    return make_note(b"ESP_EXTRA_INFO\0", 677, struct.pack("<I", crashed_tcb).ljust(152, b"\0"))


class OfflineCoreDumpTests(unittest.TestCase):
    def test_uart_uses_independently_padded_lines_and_stops_at_reboot(self):
        panic = "Guru Meditation Error: Core  1 panic'ed (Interrupt wdt timeout on CPU1).\n"
        elf = "ELF file SHA256: 1916d0ba\n"
        dump = "===== CORE DUMP START =====\nYQ==\nYg==\n===== CORE DUMP END =====\n"
        console = panic + elf + dump
        receipt = serial_crash_observations(console, "")
        self.assertEqual(uart_dump(console, receipt), (b"ab", "1916d0ba"))
        console = panic + elf + "Rebooting...\n" + dump
        with self.assertRaisesRegex(ValueError, "one completed dump"):
            uart_dump(console, serial_crash_observations(console, ""))
        console = panic + elf + dump + dump
        with self.assertRaisesRegex(ValueError, "one completed dump"):
            uart_dump(console, serial_crash_observations(console, ""))

    def test_crc_and_elf_note_are_independent_gates(self):
        dump = make_dump(make_app_note())
        checksum = zlib.crc32(dump[:-4])
        self.assertEqual(validate_dump(dump, "1916d0ba9" + "0" * 55), checksum)
        with self.assertRaisesRegex(ValueError, "CRC32 mismatch"):
            validate_dump(dump[:-1] + bytes([dump[-1] ^ 1]), "1916d0ba" + "0" * 56)
        with self.assertRaisesRegex(ValueError, "note digest differs"):
            validate_dump(dump, "0" * 64)

    def test_core_contexts_keep_crashed_task_and_label_sdk_placeholders(self):
        tcb = 0x3FFABC40
        pc = 0x400D7D19
        sp = 0x3FFB67D0
        notes = make_app_note() + make_task_note(tcb, pc, sp)
        notes += make_task_note(0x3FFABCC0, 0x20000000, 0x20000060)
        result = decode_task_contexts(make_dump(notes + make_extra_note(tcb)), "1916d0ba")
        self.assertEqual(result["crashed_tcb"], "0x3ffabc40")
        self.assertEqual(result["dump_elf_sha256_prefix"], "1916d0ba9")
        self.assertEqual(result["tasks"], [
            {"tcb": "0x3ffabc40", "pc": "0x400d7d19", "sp": "0x3ffb67d0",
             "context_status": "captured", "crashed": True},
            {"tcb": "0x3ffabcc0", "pc": None, "sp": None,
             "context_status": "sdk_placeholder", "crashed": False},
        ])
        skipped = decode_task_contexts(make_dump(notes + make_extra_note(0xDEADBEEF)), "1916d0ba")
        self.assertIsNone(skipped["crashed_tcb"])
        self.assertFalse(any(item["crashed"] for item in skipped["tasks"]))

    def test_contexts_reject_wrong_app_note_repeated_tcb_and_unlisted_crashed_tcb(self):
        tcb = 0x3FFABC40
        task = make_task_note(tcb, 0x400D7D19, 0x3FFB67D0)
        notes = make_app_note() + task
        with self.assertRaisesRegex(ValueError, "differs from the panic ELF prefix"):
            decode_task_contexts(make_dump(notes + make_extra_note(tcb)), "1916d0ba8")
        with self.assertRaisesRegex(ValueError, "invalid or repeated task handle"):
            decode_task_contexts(make_dump(notes + task + make_extra_note(tcb)), "1916d0ba")
        with self.assertRaisesRegex(ValueError, "missing saved task context"):
            decode_task_contexts(make_dump(notes + make_extra_note(0x3FFABCC0)), "1916d0ba")

    def test_service_receipt_preserves_reported_delimiter_when_dump_is_corrupt(self):
        tcb = 0x3FFABC40
        dump = make_dump(make_app_note() + make_task_note(tcb, 0x400D7D19, 0x3FFB67D0)
                         + make_extra_note(tcb))
        header = (b"Guru Meditation Error: Core  1 panic'ed (Interrupt wdt timeout on CPU1).\n"
                  b"ELF file SHA256: 1916d0ba\n===== CORE DUMP START =====\n")
        delimiter = b"===== CORE DUMP END =====\n"

        def receipt(data, enabled):
            transfer = b"".join(base64.b64encode(data[i:i + 48]) + b"\n" for i in range(0, len(data), 48))
            _, observed = crash_console_observations(
                Path("unused"), "", header + transfer + delimiter, decode_core_dump=enabled,
            )
            return observed["core_dump"]

        self.assertEqual(receipt(dump, False), {"status": "uart_reported_complete"})
        self.assertEqual(receipt(dump, True)["decoding"]["status"], "decoded")
        corrupt = dump[:-1] + bytes([dump[-1] ^ 1])
        self.assertEqual(receipt(corrupt, True), {
            "status": "uart_reported_complete",
            "decoding": {"status": "unavailable", "reason": "unsupported_or_invalid_dump"},
        })

    def test_report_keeps_metrics_and_rejects_incomplete_or_repeated_rows(self):
        heading = (
            "Crashed task handle: 0x0123, name: 'fixture_fault', GDB name: 'process 291'\n"
            "       TCB             NAME PRIO C/B  STACK USED/FREE\n"
            "---------- ---------------- -------- ----------------\n"
        )
        row = "    0x0123    fixture_fault      2/2        1696/2396\n"
        end = "\n==================== ESP32 CORE DUMP END ====================\n"
        result = task_summary(heading + row + end)
        self.assertEqual(result, {"crashed_task": "fixture_fault", "tasks": [{
            "name": "fixture_fault", "crashed": True, "priority": 2, "base_priority": 2,
            "stack_used_bytes": 1696, "stack_free_bytes": 2396,
        }]})
        with self.assertRaisesRegex(ValueError, "duplicate"):
            task_summary(heading + row + row + end)
        with self.assertRaisesRegex(ValueError, "did not complete"):
            task_summary(heading + row)

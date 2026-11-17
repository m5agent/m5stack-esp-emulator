"""Exercise offline admission and report parsing without requiring retained assets."""

import struct
import unittest
import zlib

from decode_esp32_coredump import task_summary, uart_dump, validate_dump
from device_service_crash import serial_crash_observations


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
        note_name = b"ESP_CORE_DUMP_INFO\0"
        note_desc = struct.pack("<I", 0x0102) + b"1916d0ba".ljust(64, b"\0")
        note = struct.pack("<3I", len(note_name), len(note_desc), 8266) + note_name.ljust(20, b"\0") + note_desc
        elf = bytearray(52)
        elf[:7] = b"\x7fELF\x01\x01\x01"
        struct.pack_into("<HH", elf, 16, 4, 94)  # ET_CORE, EM_XTENSA
        struct.pack_into("<I", elf, 28, 52)
        struct.pack_into("<HH", elf, 42, 32, 1)
        elf.extend(struct.pack("<8I", 4, 84, 0, 0, len(note), 0, 0, 0))
        elf.extend(note)
        data = struct.pack("<6I", 24 + len(elf) + 4, 0x0102, 0, 0, 0, 0) + elf
        checksum = zlib.crc32(data)
        dump = data + struct.pack("<I", checksum)
        self.assertEqual(validate_dump(dump, "1916d0ba" + "0" * 56), checksum)
        with self.assertRaisesRegex(ValueError, "CRC32 mismatch"):
            validate_dump(dump[:-1] + bytes([dump[-1] ^ 1]), "1916d0ba" + "0" * 56)
        with self.assertRaisesRegex(ValueError, "note digest differs"):
            validate_dump(dump, "0" * 64)

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

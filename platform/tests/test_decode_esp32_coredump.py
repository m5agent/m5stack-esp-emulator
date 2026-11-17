"""Exercise offline admission and report parsing without requiring retained assets."""

import base64
import hashlib
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zlib

from decode_esp32_coredump import task_summary, uart_dump, validate_dump
from device_service_crash import crash_console_observations, serial_crash_observations
from esp32_freertos_task_details import annotate_xtensa_tasks
from esp32_uart_coredump import (
    ESP32C6_CHIP_ID, ESP32C6_ELF_CRC32, ESP32C6_ELF_SHA256, ESP32_ELF_CRC32,
    ESP32S3_CHIP_ID, ESP32S3_ELF_CRC32, ESP32S3_ELF_SHA256,
    decode_task_contexts,
)


def make_note(name, kind, description):
    padded_name = name.ljust((len(name) + 3) & ~3, b"\0")
    padded_description = description.ljust((len(description) + 3) & ~3, b"\0")
    return struct.pack("<3I", len(name), len(description), kind) + padded_name + padded_description


def make_dump(notes, *, version=ESP32_ELF_CRC32, machine=94, loads=()):
    elf = bytearray(52)
    elf[:7] = b"\x7fELF\x01\x01\x01"
    struct.pack_into("<HH", elf, 16, 4, machine)  # ET_CORE
    struct.pack_into("<I", elf, 28, 52)
    headers = 1 + len(loads)
    struct.pack_into("<HH", elf, 42, 32, headers)
    offset = 52 + headers * 32
    elf.extend(struct.pack("<8I", 4, offset, 0, 0, len(notes), 0, 0, 0))
    offset += len(notes)
    for address, data in loads:
        elf.extend(struct.pack("<8I", 1, offset, address, address, len(data), len(data), 0, 0))
        offset += len(data)
    elf.extend(notes)
    for _, data in loads:
        elf.extend(data)
    trailer_size = 32 if version in {ESP32C6_ELF_SHA256, ESP32S3_ELF_SHA256} else 4
    data = struct.pack("<6I", 24 + len(elf) + trailer_size, version, 0, 0, 0, 0) + elf
    trailer = hashlib.sha256(data).digest() if trailer_size == 32 else struct.pack("<I", zlib.crc32(data))
    return data + trailer


def make_app_note(version=ESP32_ELF_CRC32):
    note_desc = struct.pack("<I", version) + b"1916d0ba9".ljust(64, b"\0")
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

    def test_s3_xtensa_layout_verifies_its_own_checksum_and_chip(self):
        tcb = 0x3fceaa58
        registers = make_task_note(tcb, 0x40379418, 0x3fcea820) + make_extra_note(tcb)
        for version, kind, key in (
            (ESP32S3_ELF_CRC32, "crc32", "dump_crc32"),
            (ESP32S3_ELF_SHA256, "sha256", "dump_embedded_sha256"),
        ):
            with self.subTest(kind=kind):
                dump = make_dump(make_app_note(version) + registers, version=version)
                result = decode_task_contexts(dump, "1916d0ba", chip_id=ESP32S3_CHIP_ID)
                self.assertEqual(result["format"], f"esp32s3_xtensa_elf32_{kind}")
                self.assertIn(key, result)
                self.assertEqual(result["tasks"][0]["pc"], "0x40379418")
                self.assertEqual(result["tasks"][0]["sp"], "0x3fcea820")
                for wrong_chip in (0, ESP32C6_CHIP_ID):
                    with self.assertRaisesRegex(ValueError, "version"):
                        decode_task_contexts(dump, "1916d0ba", chip_id=wrong_chip)
                corrupted = dump[:-1] + bytes([dump[-1] ^ 1])
                with self.assertRaisesRegex(ValueError, "mismatch"):
                    decode_task_contexts(corrupted, "1916d0ba", chip_id=ESP32S3_CHIP_ID)
                bad_note = make_dump(make_app_note() + registers, version=version)
                with self.assertRaisesRegex(ValueError, "application ELF note"):
                    decode_task_contexts(bad_note, "1916d0ba", chip_id=ESP32S3_CHIP_ID)

    def test_riscv_layout_and_checksum_follow_the_qualified_chip(self):
        tcb = 0x408117A8
        task = bytearray(204)
        struct.pack_into("<I", task, 24, tcb)
        struct.pack_into("<III", task, 72, 0x40804CD6, 0x40804A44, 0x408116B0)
        registers = make_note(b"CORE\0", 1, task)
        extra = make_note(b"ESP_EXTRA_INFO\0", 677, struct.pack("<II", tcb, 0))

        for version, kind, checksum_key in (
            (ESP32C6_ELF_CRC32, "crc32", "dump_crc32"),
            (ESP32C6_ELF_SHA256, "sha256", "dump_embedded_sha256"),
        ):
            with self.subTest(version=version):
                notes = make_app_note(version) + registers + extra
                dump = make_dump(notes, version=version, machine=243)
                result = decode_task_contexts(dump, "1916d0ba", chip_id=ESP32C6_CHIP_ID)
                self.assertEqual(result["format"], f"esp32c6_riscv_elf32_{kind}")
                self.assertIn(checksum_key, result)
                self.assertEqual(result["tasks"], [{
                    "tcb": "0x408117a8", "crashed": True, "context_status": "captured",
                    "pc": "0x40804cd6", "sp": "0x408116b0",
                }])
                with self.assertRaisesRegex(ValueError, "dump version"):
                    decode_task_contexts(dump, "1916d0ba")
                with self.assertRaisesRegex(ValueError, "matching ELF32"):
                    decode_task_contexts(make_dump(notes, version=version), "1916d0ba",
                                         chip_id=ESP32C6_CHIP_ID)
                with self.assertRaisesRegex(ValueError, "version.*application ELF note|application ELF note"):
                    wrong_note = make_dump(make_app_note() + registers + extra, version=version, machine=243)
                    decode_task_contexts(wrong_note, "1916d0ba", chip_id=ESP32C6_CHIP_ID)
                with self.assertRaisesRegex(ValueError, "mismatch"):
                    corrupt = dump[:-1] + bytes([dump[-1] ^ 1])
                    decode_task_contexts(corrupt, "1916d0ba", chip_id=ESP32C6_CHIP_ID)

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
                Path("unused"), "", header + transfer + delimiter, core_dump_chip_id=0 if enabled else None,
            )
            return observed["core_dump"]

        self.assertEqual(receipt(dump, False), {"status": "uart_reported_complete"})
        self.assertEqual(receipt(dump, True)["decoding"]["status"], "decoded")
        corrupt = dump[:-1] + bytes([dump[-1] ^ 1])
        self.assertEqual(receipt(corrupt, True), {
            "status": "uart_reported_complete",
            "decoding": {"status": "unavailable", "reason": "unsupported_or_invalid_dump"},
        })

    def test_metadata_uses_one_exact_tcb_load_and_retains_saved_registers(self):
        tcb = 0x3ffabc40
        notes = make_app_note() + make_task_note(tcb, 0x400d7d19, 0x3ffb67d0) + make_extra_note(tcb)
        fields = {
            b"pxTopOfStack": (0, 4), b"uxPriority": (4, 4), b"uxBasePriority": (8, 4),
            b"pxStack": (12, 4), b"pxEndOfStack": (16, 4), b"pcTaskName": (20, 16),
        }
        prefix = struct.pack("<5I", 0x3ffb6730, 4, 2, 0x3ffb6500, 0x3ffb6f00)
        tcb_bytes = prefix + b"benign_task\0".ljust(16, b"\0")
        for loads, available in (
            ([(tcb, tcb_bytes)], True),
            ([(tcb, tcb_bytes[:-1])], False),
            ([(tcb, tcb_bytes), (tcb + 4, b"X" * 16)], False),
            ([(tcb, prefix + b"A" * 16)], False),
        ):
            with self.subTest(available=available, load_sizes=[len(data) for _, data in loads]):
                core = []
                decoded = decode_task_contexts(
                    make_dump(notes, loads=loads), "1916d0ba", capture_core=core.append,
                )
                task, = decoded["tasks"]
                before = dict(task)
                mock_module = SimpleNamespace(ELFFile=object())
                with patch.dict(sys.modules, {"elftools.elf.elffile": mock_module}), patch(
                    "esp32_freertos_task_details._read_layout", return_value=(36, fields),
                ):
                    annotate_xtensa_tasks(decoded, core[0], Path("test.elf"))
                if available:
                    self.assertEqual(decoded["task_metadata"]["status"], "decoded")
                    self.assertEqual(task.pop("metadata"), {
                        "name": "benign_task", "priority": 4, "base_priority": 2,
                        "stack": {"source": "tcb_saved_stack_bounds", "used_bytes": 2000, "free_bytes": 560},
                    })
                else:
                    self.assertEqual(decoded["task_metadata"], {
                        "status": "unavailable", "reason": "task_memory_unavailable",
                    })
                self.assertEqual(task, before)

    def test_same_core_capture_is_available_for_http_and_zip_console_sources(self):
        tcb = 0x3ffabc40
        notes = make_app_note() + make_task_note(tcb, 0x400d7d19, 0x3ffb67d0) + make_extra_note(tcb)
        dump = make_dump(notes)
        serial = (b"abort() was called at PC 0x400d7d19 on core 1\n"
                  b"ELF file SHA256: 1916d0ba\n===== CORE DUMP START =====\n")
        serial += b"".join(base64.b64encode(dump[i:i + 48]) + b"\n" for i in range(0, len(dump), 48))
        serial += b"===== CORE DUMP END =====\n"
        with tempfile.TemporaryDirectory() as tmp:
            log = Path(tmp) / "serial.log"
            log.write_bytes(serial)
            from_log, from_zip = [], []
            self.assertEqual(
                crash_console_observations(log, "", core_dump_chip_id=0, capture_task_core=from_log.append),
                crash_console_observations(log, "", serial, core_dump_chip_id=0, capture_task_core=from_zip.append),
            )
        self.assertEqual(from_log, [dump[24:-4]])
        self.assertEqual(from_log, from_zip)

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

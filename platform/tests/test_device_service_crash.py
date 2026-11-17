"""Guard postmortem attribution independently of any cached runtime assets."""

import hashlib
from pathlib import Path
import tempfile
import unittest

from device_service_crash import CRASH_OUTPUT_LIMIT, output_tail, serial_crash_observations


class CrashDiagnosticsTests(unittest.TestCase):
    def test_cpu_attribution_comes_from_panic_and_register_labels(self):
        parsed = serial_crash_observations(
            "Guru Meditation Error: Core  1 panic'ed (Interrupt wdt timeout on CPU1).\n"
            "Core  1 register dump:\nPC      : 0x400d1000 PS : 0x00060e34\n"
            "Backtrace: 0x400d0ffd:0x3ffb67d0\n"
            "Core  0 register dump:\nPC      : 0x40001234\n"
            "Backtrace: 0x40001231:0x3ffb12c0\n"
            "ELF file SHA256: 1916d0ba9\n"
            "======== CORE DUMP START ========\nZGF0YQ==\n======== CORE DUMP END ========\n"
            "Rebooting...\nESP-ROM:esp32s3-20210327\n"
            "I (385) app_init: ELF file SHA256:  1efaa3064...\n",
            "",
        )
        self.assertEqual(parsed["panic"]["kind"], "watchdog")
        self.assertEqual(parsed["panic"]["core"], 1)
        self.assertEqual(parsed["panic"]["elf_sha256_prefix"], "1916d0ba9")
        self.assertEqual(parsed["panic_count"], 1)
        self.assertEqual([(row["core"], row["pc"]) for row in parsed["cpus"]],
                         [(0, "0x40001234"), (1, "0x400d1000")])
        self.assertEqual(parsed["cpus"][1]["backtrace"], [{"pc": "0x400d0ffd", "sp": "0x3ffb67d0"}])
        self.assertEqual(parsed["core_dump"]["status"], "uart_reported_complete")

    def test_boot_loop_dump_read_error_and_backend_warning_do_not_assert_panic(self):
        parsed = serial_crash_observations(
            "ESP-ROM:esp32p4-eco2-20240710\nrst:0xc (SW_CPU_RESET),boot:0x30\n"
            "E (145) esp_core_dump_flash: Core dump data check failed:\n"
            "ESP-ROM:esp32p4-eco2-20240710\nrst:0xc (SW_CPU_RESET),boot:0x30\n"
            "I (385) app_init: ELF file SHA256:  1efaa3064...\n",
            "[WARN cpu::execute] Illegal instruction 0x00000000 at PC=0x4FF10F12 hart=0 priv=Machine\n",
        )
        self.assertIsNone(parsed["panic"])
        self.assertEqual(parsed["cpus"], [])
        self.assertEqual(parsed["boot"]["rom_banners"], 2)
        self.assertEqual(len(parsed["boot"]["reset_reports"]), 2)
        self.assertEqual(parsed["core_dump"]["status"], "flash_check_failed")
        self.assertEqual(parsed["backend_observations"], [{
            "kind": "illegal_instruction_reported", "hart": 0, "pc": "0x4ff10f12",
            "instruction": "0x00000000", "source": "runtime_stderr",
        }])

    def test_task_watchdog_report_without_panic_and_abort_call_site_only(self):
        warning = "E (7) task_wdt: Task watchdog got triggered. The following tasks did not reset.\n"
        parsed = serial_crash_observations(warning, "")
        self.assertEqual(parsed["task_watchdog_reports"], 1)
        self.assertIsNone(parsed["panic"])
        parsed = serial_crash_observations(
            warning + "abort() was called at PC 0x400d7d17 on core 1\n"
            "Backtrace: 0x400d7d17:0x3ffb67d0\n======== CORE DUMP START ========\n",
            "",
        )
        self.assertEqual(parsed["panic"]["abort_call_site_pc"], "0x400d7d17")
        self.assertNotIn("pc", parsed["cpus"][0])
        self.assertEqual(parsed["core_dump"]["status"], "uart_incomplete")

    def test_truncated_capture_hashes_retained_bytes_and_ignores_partial_lines(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "serial.log"
            content = b"x" * CRASH_OUTPUT_LIMIT + b"\nvalid line\nunfinished"
            path.write_bytes(content)
            receipt, body = output_tail(path)
            retained = content[-CRASH_OUTPUT_LIMIT:]
            self.assertEqual(receipt["bytes"], CRASH_OUTPUT_LIMIT)
            self.assertEqual(receipt["offset"], len(content) - CRASH_OUTPUT_LIMIT)
            self.assertEqual(receipt["sha256"], hashlib.sha256(retained).hexdigest())
            self.assertTrue(receipt["truncated"])
            self.assertEqual(body, "valid line\n")
            self.assertEqual((receipt,body), output_tail(path, content))

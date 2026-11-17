"""Guard postmortem attribution independently of any cached runtime assets."""

import hashlib
import io
import json
from pathlib import Path
import tempfile
import unittest

from device_service_crash import (
    CRASH_OUTPUT_LIMIT, S3_IWDT_STAGE0_PREFIX, crash_console_observations,
    output_tail, qmp_cpu_pc_sample, serial_crash_observations,
)
from device_service_errors import ServiceError


class CpuPcSampleTests(unittest.TestCase):
    def sample(
        self, registers, *, states=("running", "running"), targets=("xtensa", "xtensa"),
        native_c6=False, machine="esp32c6-machine", cpu_model="espressif-riscv-cpu",
        cpu_path="/machine/soc/cpu",
    ):
        queued_states = iter(states)
        calls = []

        def qmp(command, **arguments):
            calls.append((command, arguments))
            if command == "query-status":
                status = next(queued_states)
                return {"return": {"status": status, "running": status == "running"}}
            if command == "query-cpus-fast":
                return {"return": [
                    {"cpu-index": i, "target": target, "thread-id": i + 100, "qom-path": cpu_path}
                    for i, target in enumerate(targets)
                ]}
            if command == "qom-get":
                return {"return": machine if arguments["path"] == "/machine" else cpu_model}
            return {"return": registers}

        self.calls = calls
        return qmp_cpu_pc_sample(qmp, native_c6=native_c6)

    def test_binds_two_pcs_to_qmp_indices_and_reads_paused_state_without_cont(self):
        result = self.sample(
            "\r\nCPU#1\r\nPC=400D1234\r\nPS=60001000\r\nCPU#0\r\nPC=4000ABCD\r\n",
            states=("paused", "paused"),
        )
        self.assertEqual(result["cpus"], [
            {"cpu_index": 0, "pc": "0x4000abcd"}, {"cpu_index": 1, "pc": "0x400d1234"},
        ])
        self.assertEqual((result["run_state_before"], result["run_state_after"]), ("paused", "paused"))
        self.assertEqual(self.calls, [
            ("query-status", {}), ("query-cpus-fast", {}),
            ("human-monitor-command", {"command-line": "info registers -a"}), ("query-status", {}),
        ])

    def test_rejects_non_xtensa_before_reading_registers(self):
        with self.assertRaises(ServiceError) as failure:
            self.sample("CPU#0\nPC=400abcd0", targets=("riscv32",))
        self.assertEqual(failure.exception.code, "cpu_pc_not_supported")
        self.assertEqual([name for name, _ in self.calls], ["query-status", "query-cpus-fast"])

    def test_native_c6_reads_current_pc_after_confirming_qmp_identity(self):
        result = self.sample(
            "CPU#0\n pc       4080273E\n mepc     40804cb8\n",
            native_c6=True, targets=("riscv32",), states=("paused", "paused"),
        )
        self.assertEqual(result["target"], "riscv32")
        self.assertEqual(result["machine_type"], "esp32c6-machine")
        self.assertEqual(result["cpu_model"], "espressif-riscv-cpu")
        self.assertEqual(result["cpus"], [{"cpu_index": 0, "pc": "0x4080273e"}])
        self.assertEqual((result["run_state_before"], result["run_state_after"]), ("paused", "paused"))
        self.assertEqual(self.calls, [
            ("query-status", {}), ("query-cpus-fast", {}),
            ("qom-get", {"path": "/machine", "property": "type"}),
            ("qom-get", {"path": "/machine/soc/cpu", "property": "type"}),
            ("human-monitor-command", {"command-line": "info registers -a"}), ("query-status", {}),
        ])

    def test_native_c6_rejects_other_targets_or_unverified_qom_before_registers(self):
        cases = (
            ({"targets": ("riscv64",)}, "cpu_pc_not_supported"),
            ({"targets": ("riscv32", "riscv32")}, "cpu_pc_unavailable"),
            ({"machine": "virt-machine"}, "cpu_pc_not_supported"),
            ({"cpu_model": "riscv-cpu"}, "cpu_pc_not_supported"),
            ({"cpu_path": "/objects/cpu"}, "cpu_pc_unavailable"),
        )
        for overrides, code in cases:
            with self.subTest(**overrides), self.assertRaises(ServiceError) as failure:
                self.sample("CPU#0\n pc 4080273e\n", **({"native_c6": True, "targets": ("riscv32",)} | overrides))
            self.assertEqual(failure.exception.code, code)
            self.assertNotIn("human-monitor-command", [name for name, _ in self.calls])

    def test_native_c6_requires_current_pc_instead_of_guest_exception_pc(self):
        for report in ("CPU#0\n mepc 40804cb8\n", "CPU#0\n pc 000000004080273e\n", "CPU#1\n pc 4080273e\n"):
            with self.subTest(report=report), self.assertRaises(ServiceError) as failure:
                self.sample(report, native_c6=True, targets=("riscv32",))
            self.assertEqual(failure.exception.code, "cpu_pc_unavailable")

    def test_rejects_state_transition_and_ambiguous_or_incomplete_register_output(self):
        valid = "CPU#0\nPC=400abcd0\nCPU#1\nPC=400abcd1\n"
        with self.assertRaises(ServiceError) as failure:
            self.sample(valid, states=("running", "paused"))
        self.assertEqual(failure.exception.code, "cpu_pc_state_changed")
        for report in (valid + "PC=400abcd1\n", valid.rsplit("PC=", 1)[0], "é" + valid, valid * 2000):
            with self.subTest(size=len(report)), self.assertRaises(ServiceError) as failure:
                self.sample(report)
            self.assertEqual(failure.exception.code, "cpu_pc_unavailable")


class CrashDiagnosticsTests(unittest.TestCase):
    FLASH_START = "I (39) esp_core_dump_flash: Save core dump to flash...\n"
    FLASH_FAILURE = "E (39) esp_core_dump_common: Core dump write failed with error=-1\n"
    FLASH_SAVED = "I (39) esp_core_dump_flash: Core dump has been saved to flash.\n"

    def test_failed_flash_attempt_preserves_saved_report_as_a_conflict(self):
        console = "ESP-ROM:esp32p4-test\n" + self.FLASH_START + self.FLASH_FAILURE + self.FLASH_SAVED
        dump = serial_crash_observations(console, "")["core_dump"]
        self.assertEqual(dump["status"], "write_failed")
        self.assertEqual(dump["write_attempt_count"], 1)
        self.assertEqual(dump["write_attempts"], [{
            "ordinal": 1, "boot_ordinal": 1, "start_line": 2,
            "failure_line": 3, "saved_line": 4, "transport": "flash",
            "status": "write_failed", "saved_reported": True, "conflicting_reports": True,
        }])
        self.assertEqual(dump["last_terminal_write_attempt"], dump["write_attempts"][0])

    def test_conflicting_flash_reports_do_not_attempt_flash_decoding(self):
        def unexpected_decode(_):
            self.fail("a contradictory saved report must not initiate Flash decoding")

        source, observed = crash_console_observations(
            Path("unused"), "", (self.FLASH_START + self.FLASH_FAILURE + self.FLASH_SAVED).encode(),
            decode_flash_dump=unexpected_decode,
        )
        self.assertEqual(source["status"], "available")
        self.assertEqual(observed["core_dump"]["status"], "write_failed")
        self.assertNotIn("decoding", observed["core_dump"])

    def test_new_attempt_and_boot_do_not_inherit_an_earlier_write_failure(self):
        for separator in (self.FLASH_START, "ESP-ROM:esp32p4-next\n", "Rebooting...\n",
                          "abort() was called at PC 0x400d0000 on core 0\n"):
            with self.subTest(separator=separator):
                dump = serial_crash_observations(
                    self.FLASH_START + self.FLASH_FAILURE + separator + self.FLASH_SAVED, "",
                )["core_dump"]
                self.assertEqual(dump["status"], "flash_reported_saved")
                self.assertEqual(dump["write_attempt_count"], 2)
                self.assertEqual(dump["write_attempts"][0]["status"], "write_failed")
                self.assertFalse(dump["write_attempts"][1]["conflicting_reports"])
                self.assertEqual(dump["last_terminal_write_attempt"]["ordinal"], 2)

    def test_latest_incomplete_boot_preserves_last_terminal_attempt(self):
        terminal = self.FLASH_START + self.FLASH_FAILURE + self.FLASH_SAVED
        next_boot = "ESP-ROM:esp32p4-next\nI (10) boot: Loaded app from partition at offset 0x10000\n"
        dump = serial_crash_observations(terminal + next_boot, "")["core_dump"]
        self.assertEqual(dump["status"], "write_failed")
        self.assertEqual(dump["last_terminal_write_attempt"]["status"], "write_failed")
        pending = serial_crash_observations(terminal + next_boot + self.FLASH_START, "")["core_dump"]
        self.assertEqual(pending["status"], "write_failed")
        self.assertEqual(pending["write_attempts"][-1]["status"], "incomplete")
        self.assertEqual(pending["last_terminal_write_attempt"]["ordinal"], 1)
        self.assertTrue(pending["last_terminal_write_attempt"]["conflicting_reports"])

    def test_new_incomplete_write_does_not_decode_an_earlier_saved_report(self):
        def unexpected_decode(_):
            self.fail("an earlier saved report must not decode an unfinished later write")

        _, observed = crash_console_observations(
            Path("unused"), "", (self.FLASH_SAVED + self.FLASH_START).encode(),
            decode_flash_dump=unexpected_decode,
        )
        dump = observed["core_dump"]
        self.assertEqual(dump["status"], "flash_reported_saved")
        self.assertEqual(dump["write_attempts"][-1]["status"], "incomplete")
        self.assertEqual(dump["last_terminal_write_attempt"]["ordinal"], 1)
        self.assertNotIn("decoding", dump)

    def test_unknown_start_and_bounded_pending_attempts_preserve_terminal_report(self):
        dump = serial_crash_observations(self.FLASH_FAILURE + self.FLASH_SAVED + self.FLASH_START * 32, "")["core_dump"]
        self.assertEqual(dump["write_attempt_count"], 33)
        self.assertEqual(len(dump["write_attempts"]), 16)
        self.assertEqual([item["ordinal"] for item in dump["write_attempts"]], list(range(18, 34)))
        terminal = dump["last_terminal_write_attempt"]
        self.assertIsNone(terminal["start_line"])
        self.assertIsNone(terminal["boot_ordinal"])
        self.assertEqual(terminal["ordinal"], 1)
        self.assertTrue(terminal["saved_reported"])
        self.assertTrue(terminal["conflicting_reports"])

    def test_uart_transfer_starts_a_separate_write_context(self):
        dump = serial_crash_observations(
            self.FLASH_START + self.FLASH_FAILURE + "===== CORE DUMP START =====\n"
            "===== CORE DUMP END =====\n", "",
        )["core_dump"]
        self.assertEqual(dump["status"], "uart_reported_complete")
        self.assertEqual(dump["last_terminal_write_attempt"]["status"], "write_failed")

    def test_application_loads_retain_order_and_capture_local_boot_context(self):
        parsed = serial_crash_observations(
            "ESP-ROM:esp32p4-test\nrst:0x1 (POWERON)\n"
            "I (6) boot: ESP-IDF test 2nd stage bootloader\n"
            "I (610) boot: Loaded app from partition at offset 0x10000\n"
            "ESP-ROM:esp32p4-test\nrst:0xc (SW_CPU_RESET)\n"
            "I (6) boot: ESP-IDF test 2nd stage bootloader\n"
            "I (493) boot: Loaded app from partition at offset 0x210000\n", "",
        )
        self.assertEqual(parsed["boot"]["application_load_count"], 2)
        self.assertEqual(parsed["boot"]["application_loads"], [
            {"console_line": 4, "boot_ordinal": 1, "idf_log_ms": 610, "offset": 65536},
            {"console_line": 8, "boot_ordinal": 2, "idf_log_ms": 493, "offset": 2162688},
        ])
        self.assertIsNone(parsed["panic"])
        self.assertEqual(parsed["cpus"], [])

    def test_application_load_context_is_unknown_without_a_proven_rom_boundary(self):
        load = "I (10) boot: Loaded app from partition at offset 0x10000\n"
        parsed = serial_crash_observations(
            load + "ESP-ROM:esp32p4-test\nrst:0x1 (POWERON)\n" + load
            + "Rebooting...\n" + load
            + "ESP-ROM:esp32p4-test\nrst:0x1 (POWERON)\n" + load
            + "rst:0xc (SW_CPU_RESET)\n" + load
            + "ESP-ROM:esp32p4-test\nI (0) boot: ESP-IDF test bootloader\n" + load
            + "I (0) boot: ESP-IDF test bootloader\n" + load, "",
        )
        self.assertEqual(
            [item["boot_ordinal"] for item in parsed["boot"]["application_loads"]],
            [None, 1, None, 2, None, 3, None],
        )

    def test_application_load_count_survives_bounded_record_retention(self):
        parsed = serial_crash_observations(
            ("ESP-ROM:esp32p4-test\n"
             "I (610) boot: Loaded app from partition at offset 0x10000\n") * 32, "",
        )
        boot = parsed["boot"]
        self.assertEqual(boot["application_load_count"], 32)
        self.assertEqual([item["boot_ordinal"] for item in boot["application_loads"]], list(range(17, 33)))
        self.assertEqual([item["console_line"] for item in boot["application_loads"]], list(range(34, 65, 2)))

    def test_application_load_marker_rejects_unbounded_or_unrelated_text(self):
        lines = [
            "application says I (10) boot: Loaded app from partition at offset 0x10000",
            "I (-1) boot: Loaded app from partition at offset 0x10000",
            "I (18446744073709551616) boot: Loaded app from partition at offset 0x10000",
            "I (10) boot: Loaded app from partition at offset 0x100000000",
            "I (10) boot: Loaded app from partition at offset 0x10000 trailing text",
        ]
        parsed = serial_crash_observations("\n".join(lines), "")
        self.assertEqual(parsed["boot"]["application_load_count"], 0)
        self.assertEqual(parsed["boot"]["application_loads"], [])

    def test_application_load_tail_uses_complete_capture_lines_and_provenance(self):
        marker = b"I (610) boot: Loaded app from partition at offset 0x10000\n"
        content = b"ESP-ROM:discarded\n" + b"x" * CRASH_OUTPUT_LIMIT + b"\n" + b"\x1b[32m" + marker[:-1] + b"\x1b[0m\n" + marker[:-1]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "serial.log"
            path.write_bytes(b"ESP-ROM:other-live-bytes\n")
            source, parsed = crash_console_observations(path, "", content)
        self.assertTrue(source["truncated"])
        self.assertEqual(source["sha256"], hashlib.sha256(content[-CRASH_OUTPUT_LIMIT:]).hexdigest())
        self.assertEqual(parsed["boot"]["application_load_count"], 1)
        self.assertEqual(parsed["boot"]["application_loads"], [
            {"console_line": 1, "boot_ordinal": None, "idf_log_ms": 610, "offset": 65536},
        ])

    HISTORICAL_PANIC = (
        b"Guru Meditation Error: Core  1 panic'ed (synthetic timeout).\n"
        b"Core  1 register dump:\nPC : 0x400d1000\nELF file SHA256: 1916d0ba9\n"
    )
    LATE_LOG = b"synthetic boot progress\n" * (5 * 1024 * 1024 // len(b"synthetic boot progress\n"))

    def test_native_s3_stage0_retains_timing_without_asserting_guest_panic(self):
        timing = {
            "schema_version": 1, "now_ns": 981700000,
            "feed_attempts": 38, "feeds": 36, "feed_cpu": 0,
            "last_feed_ns": 681140000, "last_feed_deadline_ns": 981140000,
            "stage0_ticks": 600, "stage1_ticks": 1200, "wdt_config0": 3089072128,
            "wdt_prescaler": 40000, "wdt_hz": 2000, "wdt_irq_enabled": 1,
            "alarms": [72, 73], "coalesced": [0, 30], "last_alarm_ns": [979331000, 979342000],
            "last_expire_ns": [977798000, 977798000], "acks": [[72, 0], [0, 42]],
            "last_ack_ns": [[981212000, 0], [0, 671680000]], "irq_sources": [55, 57, 58],
            "irq_rises": [1, 72, 43], "irq_falls": [0, 72, 42], "irq_level": [1, 0, 1],
            "routes": [[24, 24], [3, 6], [6, 1]], "cpu_irq_snapshot_available": True,
            "cpu_ps": [395808, 396835], "cpu_intenable": [318767150, 318767107], "cpu_intset": [0, 2],
        }
        line = S3_IWDT_STAGE0_PREFIX + json.dumps(timing) + "\n"
        parsed = serial_crash_observations("", line, native_s3=True)
        self.assertEqual(parsed["backend_observations"], [{
            "kind": "esp32s3_iwdt_stage0", "source": "runtime_stderr", "timing": timing,
        }])
        self.assertIsNone(parsed["panic"])
        self.assertEqual(parsed["cpus"], [])
        without_ack_clock = timing | {"last_ack_ns": [[-1, 0], [0, -1]]}
        no_clock_line = S3_IWDT_STAGE0_PREFIX + json.dumps(without_ack_clock)
        self.assertEqual(
            serial_crash_observations("", no_clock_line, native_s3=True)["backend_observations"][0]["timing"],
            without_ack_clock,
        )
        self.assertEqual(serial_crash_observations("", line)["backend_observations"], [])
        self.assertEqual(serial_crash_observations(line, "", native_s3=True)["backend_observations"], [])
        bad = (
            line + line, line.rstrip("\n") + " " * 2048, S3_IWDT_STAGE0_PREFIX + "{",
            *(S3_IWDT_STAGE0_PREFIX + json.dumps(timing | invalid)
              for invalid in ({"schema_version": True}, {"acks": [[72, 0], [42]]},
                              {"irq_sources": [55, 58, 57]}, {"feed_attempts": 35},
                              {"routes": [[24, 24], [3, 6], [6, 32]]}, {"payload": ["extra"]})),
        )
        for stderr in bad:
            with self.subTest(stderr=stderr[:160]):
                self.assertEqual(serial_crash_observations("", stderr, native_s3=True)["backend_observations"], [])

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

    def test_earlier_console_panic_survives_a_long_latest_window(self):
        content = self.HISTORICAL_PANIC + self.LATE_LOG + b"ESP-ROM:synthetic-test\n"
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "serial.log"
            path.write_bytes(content)
            source, observed = crash_console_observations(path, "")
            self.assertEqual(source, output_tail(path)[0])
            # A pre-captured evidence bundle must never use the live file.
            path.write_bytes(b"\nassert failed: current file differs\n")
            self.assertEqual((source, observed), crash_console_observations(path, "", content))

        self.assertIsNone(observed["panic"])
        self.assertEqual(observed["cpus"], [])
        self.assertEqual(observed["panic_count"], 0)
        self.assertEqual(observed["boot"]["rom_banners"], 1)
        earlier = observed["earlier_console"]
        self.assertEqual(earlier["scope"], "console_prefix")
        self.assertEqual(earlier["source"], {
            "status": "available", "offset": 0, "bytes": CRASH_OUTPUT_LIMIT, "truncated": True,
            "sha256": hashlib.sha256(content[:CRASH_OUTPUT_LIMIT]).hexdigest(),
        })
        self.assertEqual(earlier["panic"]["core"], 1)
        self.assertEqual(earlier["panic"]["elf_sha256_prefix"], "1916d0ba9")
        self.assertEqual(earlier["cpus"][0]["pc"], "0x400d1000")

    def test_scan_never_reads_more_than_two_bounded_console_ranges(self):
        reads = []

        class CapturedStream(io.BytesIO):
            def read(self, size=-1):
                if not 0 <= size <= CRASH_OUTPUT_LIMIT:
                    raise AssertionError("console crash read must use a bounded range")
                reads.append((self.tell(), size))
                return super().read(size)

        class CapturedPath:
            def open(self, mode):
                return CapturedStream(content)

        for latest in (b"", b"\nassert failed: later synthetic panic\n"):
            with self.subTest(latest=latest):
                content = self.HISTORICAL_PANIC + self.LATE_LOG + latest
                reads.clear()
                _, observed = crash_console_observations(CapturedPath(), "")
                expected = [(len(content) - CRASH_OUTPUT_LIMIT, CRASH_OUTPUT_LIMIT)]
                if latest:
                    self.assertEqual(observed["panic"]["reason"], "later synthetic panic")
                    self.assertNotIn("earlier_console", observed)
                else:
                    expected.append((0, CRASH_OUTPUT_LIMIT))
                    self.assertIn("earlier_console", observed)
                self.assertEqual(reads, expected)

    def test_prefix_cutoff_never_completes_partial_or_middle_panic_lines(self):
        header = self.HISTORICAL_PANIC.splitlines()[0]
        incomplete = b"x" * (CRASH_OUTPUT_LIMIT - len(header) - 1) + b"\n" + header
        content = incomplete + b"\n" + self.HISTORICAL_PANIC + self.LATE_LOG
        _, observed = crash_console_observations(Path("unused"), "", content)
        self.assertIsNone(observed["panic"])
        self.assertNotIn("earlier_console", observed)

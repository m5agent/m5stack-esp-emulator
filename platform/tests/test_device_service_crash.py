"""Guard postmortem attribution independently of any cached runtime assets."""

import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from device_service_crash import (
    CRASH_OUTPUT_LIMIT, S3_IWDT_STAGE0_PREFIX, output_tail, qmp_cpu_pc_sample, serial_crash_observations,
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

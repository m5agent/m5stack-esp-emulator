#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RUNNER = ROOT / "tests/uiflow2/core2_native_hci/run_service_5x.py"
SPEC = importlib.util.spec_from_file_location("core2_native_hci_runner", RUNNER)
assert SPEC and SPEC.loader
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def healthy(**overrides: int) -> dict[str, int]:
    values = {
        "hli-valid": 1,
        "hli-posts": 48,
        "hli-consumed": 48,
        "hli-errors": 0,
        "hli-c2h-events": 39,
        "hli-c2h-acls": 9,
        "hli-fast-path-events": 39,
        "hli-fast-path-acls": 9,
        "hli-prealloc-failures": 0,
        "hli-queue-depth": 0,
        "meta-queue-depth": 0,
        "dropped-packets": 0,
        "tx-queue-depth": 0,
        "last-error": 0,
        "peer-closed": 0,
    }
    values.update(overrides)
    return values


class Core2NativeHciHealthTests(unittest.TestCase):
    def test_parses_host_rss_samples(self) -> None:
        self.assertEqual(runner.parse_ps_rss_kib(" 245760\n"), 245760)
        self.assertIsNone(runner.parse_ps_rss_kib(""))
        self.assertIsNone(runner.parse_ps_rss_kib("unavailable"))

    def test_parses_phys_footprint_samples(self) -> None:
        output = "\n".join(
            (
                "python3 [123]: 64-bit    Footprint: 8656 KB",
                "Auxiliary data:",
                "    phys_footprint: 8.5 MB",
                "    phys_footprint_peak: 9 MB",
            )
        )
        self.assertEqual(
            runner.parse_footprint_kib(output),
            8704,
        )
        self.assertIsNone(runner.parse_footprint_kib("phys_footprint: unavailable"))

    def test_parses_bounded_qemu_accelerator(self) -> None:
        command = (
            "qemu-system-xtensa -M m5core2 -display none "
            "-accel tcg,thread=single,tb-size=128 "
            "-icount shift=5,align=off,sleep=off -m 0"
        )
        self.assertEqual(
            runner.parse_qemu_accelerator(command),
            "tcg,thread=single,tb-size=128",
        )
        self.assertEqual(
            runner.parse_qemu_icount(command),
            "shift=5,align=off,sleep=off",
        )
        self.assertIsNone(runner.parse_qemu_accelerator("qemu -M m5core2"))
        self.assertIsNone(runner.parse_qemu_icount("qemu -M m5core2"))
        self.assertEqual(
            runner.EXPECTED_QEMU_ACCELERATOR,
            "tcg,thread=single,tb-size=128",
        )
        self.assertEqual(
            runner.EXPECTED_QEMU_ICOUNT,
            "shift=5,align=off,sleep=off",
        )

    def test_sustained_stress_floor_matches_fixed_clock(self) -> None:
        self.assertEqual(
            runner.sustained_stress_requirements(10)["minimum_sweeps"],
            3,
        )
        self.assertEqual(
            runner.sustained_stress_requirements(40)["minimum_sweeps"],
            3,
        )
        self.assertEqual(
            runner.sustained_stress_requirements(120)["minimum_sweeps"],
            10,
        )

    def test_input_hashes_are_frozen_before_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "firmware.bin"
            elf = root / "firmware.elf"
            qemu = root / "qemu-system-xtensa"
            tool = root / "runner.py"
            image.write_bytes(b"image-v1")
            elf.write_bytes(b"elf-v1")
            qemu.write_bytes(b"qemu-v1")
            tool.write_bytes(b"runner-v1")

            frozen = runner.freeze_input_hashes(
                image,
                elf,
                qemu,
                {"runner": tool},
            )
            image.write_bytes(b"image-v2")
            elf.write_bytes(b"elf-v2")
            qemu.write_bytes(b"qemu-v2")
            tool.write_bytes(b"runner-v2")

            self.assertEqual(frozen["firmware_bytes"], len(b"image-v1"))
            self.assertEqual(
                frozen["firmware_sha256"],
                hashlib.sha256(b"image-v1").hexdigest(),
            )
            self.assertNotEqual(runner.sha256(image), frozen["firmware_sha256"])
            self.assertNotEqual(runner.sha256(elf), frozen["elf_sha256"])
            self.assertNotEqual(runner.sha256(qemu), frozen["qemu_sha256"])
            self.assertNotEqual(
                runner.sha256(tool),
                frozen["runner_sha256"],
            )

    def test_accepts_queue_full_only_after_peer_close(self) -> None:
        self.assertTrue(
            runner.native_hci_health_ok(
                healthy(
                    **{
                        "last-error": 2,
                        "peer-closed": 1,
                        "tx-queue-depth": 32,
                    }
                )
            )
        )
        self.assertFalse(
            runner.native_hci_health_ok(healthy(**{"last-error": 2}))
        )
        self.assertFalse(
            runner.native_hci_health_ok(
                healthy(
                    **{
                        "last-error": 2,
                        "peer-closed": 1,
                        "dropped-packets": 0,
                        "tx-queue-depth": 0,
                    }
                )
            )
        )

    def test_rejects_hli_errors_and_queue_depth(self) -> None:
        self.assertFalse(
            runner.native_hci_health_ok(healthy(**{"hli-errors": 1}))
        )
        self.assertFalse(
            runner.native_hci_health_ok(healthy(**{"meta-queue-depth": 1}))
        )

    def test_requires_guest_object_fast_path(self) -> None:
        self.assertFalse(
            runner.native_hci_health_ok(
                healthy(
                    **{
                        "hli-fast-path-events": 0,
                        "hli-fast-path-acls": 0,
                    }
                )
            )
        )
        self.assertTrue(
            runner.native_hci_health_ok(
                healthy(**{"hli-fast-path-events": 1})
            )
        )

    def test_reads_eight_mib_machine_capacity_from_qom(self) -> None:
        self.assertEqual(
            runner.qom_memory_bytes(
                {
                    "nodes": {
                        "memory": {
                            "value": {
                                "size": 8 << 20,
                            }
                        }
                    }
                }
            ),
            8 << 20,
        )
        self.assertIsNone(runner.qom_memory_bytes({}))
        self.assertIsNone(
            runner.qom_memory_bytes(
                {"nodes": {"memory": {"value": {"size": "8M"}}}}
            )
        )

    def test_parses_and_accepts_complete_psram_stress(self) -> None:
        serial = "\n".join(
            (
                "UNIFIED_CORE2_PSRAM_ALLOC 4194304 1048576 1048576",
                "UNIFIED_CORE2_PSRAM_INIT_PASS",
                "UNIFIED_CORE2_PSRAM_SWEEP 1",
                "UNIFIED_CORE2_PSRAM_SWEEP 2",
                "UNIFIED_CORE2_PSRAM_SWEEP 3",
                "UNIFIED_CORE2_PSRAM_SWEEP 4",
                "UNIFIED_CORE2_PSRAM_SWEEP 5",
                "UNIFIED_CORE2_PSRAM_SWEEP 6",
                "UNIFIED_CORE2_PSRAM_STRESS_PASS",
                "UNIFIED_CORE2_HTTP_RECHECK_PASS 1",
                "UNIFIED_CORE2_STRESS_HEARTBEAT 10 5 0 0",
                "UNIFIED_CORE2_STRESS_HEARTBEAT 20 6 1 0",
            )
        )
        parsed = runner.parse_psram_stress(serial)
        self.assertTrue(parsed["marker_present"])
        self.assertEqual(parsed["sweeps"], [1, 2, 3, 4, 5, 6])
        self.assertTrue(runner.psram_stress_ok(parsed))
        self.assertTrue(runner.sustained_stress_ok(parsed, 20))

    def test_sustained_psram_stress_is_hold_aware(self) -> None:
        serial = "\n".join(
            (
                "UNIFIED_CORE2_PSRAM_ALLOC 4194304 1048576 1048576",
                "UNIFIED_CORE2_PSRAM_INIT_PASS",
                "UNIFIED_CORE2_PSRAM_SWEEP 1",
                "UNIFIED_CORE2_PSRAM_SWEEP 2",
                "UNIFIED_CORE2_PSRAM_SWEEP 3",
                "UNIFIED_CORE2_PSRAM_STRESS_PASS",
            )
        )
        parsed = runner.parse_psram_stress(serial)
        self.assertTrue(runner.psram_stress_ok(parsed))
        self.assertFalse(runner.sustained_stress_ok(parsed, 120))
        self.assertEqual(
            runner.sustained_stress_requirements(120),
            {
                "minimum_sweeps": 10,
                "minimum_heartbeats": 6,
                "minimum_http_rechecks": 8,
                "minimum_public_rechecks": 2,
            },
        )

    def test_attempt_batches_preserve_attempt_order(self) -> None:
        self.assertEqual(
            runner.attempt_batches(5, 1),
            [[1], [2], [3], [4], [5]],
        )
        self.assertEqual(
            runner.attempt_batches(5, 2),
            [[1, 2], [3, 4], [5]],
        )
        self.assertEqual(
            runner.attempt_batches(3, 4),
            [[1, 2, 3]],
        )

    def test_maximum_interval_overlap_counts_live_sessions(self) -> None:
        self.assertEqual(runner.maximum_interval_overlap([]), 0)
        self.assertEqual(
            runner.maximum_interval_overlap(
                [(1.0, 3.0), (1.5, 2.5), (4.0, 5.0)]
            ),
            2,
        )
        self.assertEqual(
            runner.maximum_interval_overlap(
                [(1.0, 2.0), (2.0, 3.0)]
            ),
            1,
        )
        self.assertEqual(
            runner.maximum_interval_overlap(
                [(1.0, 2.0), (2.1, 3.0)]
            ),
            1,
        )

    def test_rejects_incomplete_or_failed_psram_stress(self) -> None:
        incomplete = runner.parse_psram_stress(
            "\n".join(
                (
                    "UNIFIED_CORE2_PSRAM_ALLOC 4194304 1048576 1048576",
                    "UNIFIED_CORE2_PSRAM_INIT_PASS",
                    "UNIFIED_CORE2_PSRAM_SWEEP 1",
                )
            )
        )
        self.assertFalse(runner.psram_stress_ok(incomplete))
        failed = runner.parse_psram_stress(
            "\n".join(
                (
                    "UNIFIED_CORE2_PSRAM_ALLOC 4194304 1048576 1048576",
                    "UNIFIED_CORE2_PSRAM_INIT_PASS",
                    "UNIFIED_CORE2_PSRAM_SWEEP 1",
                    "UNIFIED_CORE2_PSRAM_SWEEP 2",
                    "UNIFIED_CORE2_PSRAM_SWEEP 3",
                    "UNIFIED_CORE2_PSRAM_STRESS_PASS",
                    "UNIFIED_CORE2_PSRAM_STRESS_ERROR RuntimeError('bad')",
                )
            )
        )
        self.assertFalse(runner.psram_stress_ok(failed))

    def test_manifest_session_binding_requires_a_real_session(self) -> None:
        self.assertFalse(runner.manifest_session_binding_ok({}, None))
        self.assertFalse(
            runner.manifest_session_binding_ok(
                {"session": {"session_id": "other"}},
                "expected",
            )
        )
        self.assertTrue(
            runner.manifest_session_binding_ok(
                {"session": {"session_id": "expected"}},
                "expected",
            )
        )


if __name__ == "__main__":
    unittest.main(verbosity=2)

from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "platform/tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import device_service
import device_service_runtime


class DeviceServiceRuntimeBoundaryTests(unittest.TestCase):
    def test_qemu_runtime_memory_preserves_native_core2_qom_policy(self):
        self.assertEqual(
            device_service_runtime.qemu_runtime_memory(
                "0",
                "core2-native-hci",
                "core2",
            ),
            {
                "requested_psram_mib": 0,
                "cli_requested_psram_mib": 0,
                "effective_psram_mib": 8,
                "effective_source": "validated-m5core2-qom",
                "policy": "native-controller-machine-default-psram",
                "claim": "qemu-memory-configuration-only",
                "physical_cache_psram_timing": "NOT RUN",
            },
        )
        native_other = device_service_runtime.qemu_runtime_memory(
            "4",
            "core2-native-vhci",
            "cores3",
        )
        self.assertEqual(native_other["requested_psram_mib"], 4)
        self.assertEqual(native_other["cli_requested_psram_mib"], 0)
        self.assertEqual(native_other["effective_psram_mib"], 0)

    def test_qemu_runtime_memory_preserves_regular_and_missing_values(self):
        regular = device_service_runtime.qemu_runtime_memory(
            "8",
            "uiflow2-cores3-unified",
            "core2",
        )
        self.assertEqual(regular["requested_psram_mib"], 8)
        self.assertEqual(regular["effective_psram_mib"], 8)
        self.assertEqual(regular["policy"], "qemu-emulated-psram")
        missing = device_service_runtime.qemu_runtime_memory(
            None,
            None,
        )
        self.assertIsNone(missing["requested_psram_mib"])
        self.assertIsNone(missing["effective_psram_mib"])
        self.assertEqual(missing["policy"], "not-configured")
        invalid = device_service_runtime.qemu_runtime_memory(
            "invalid",
            None,
        )
        self.assertIsNone(invalid["requested_psram_mib"])

    def test_runtime_psram_mismatch_preserves_error_shape(self):
        issue = device_service_runtime.runtime_psram_mismatch(
            "4",
            "uiflow2-cores3-unified",
            6 << 20,
            "cores3",
        )
        self.assertEqual(issue["code"], "runtime_psram_mismatch")
        self.assertEqual(issue["requirement"], 6 << 20)
        self.assertEqual(issue["available"], 4 << 20)
        self.assertEqual(issue["path"], "target.psram_size")
        self.assertEqual(
            issue["runtime_profile"],
            "uiflow2-cores3-unified",
        )
        self.assertEqual(issue["memory_policy"], "qemu-emulated-psram")

    def test_runtime_psram_mismatch_accepts_valid_or_absent_requirement(self):
        self.assertIsNone(
            device_service_runtime.runtime_psram_mismatch(
                "8",
                "uiflow2-cores3-unified",
                8 << 20,
            )
        )
        for value in (None, 0, -1, "8388608"):
            with self.subTest(value=value):
                self.assertIsNone(
                    device_service_runtime.runtime_psram_mismatch(
                        "4",
                        "uiflow2-cores3-unified",
                        value,
                    )
                )

    def test_runtime_env_redacts_only_private_keys_without_mutating(self):
        source = {
            "M5SW_ESPNOW_PEER_LMK": "secret-lmk",
            "M5SW_ESPNOW_PEER_PMK": "secret-pmk",
            "M5SW_ESPNOW_PEER_PUBLIC_MAC": "02:00:00:00:00:01",
            "M5SW_I2C_TRACE": "1",
        }
        redacted = device_service_runtime.redacted_runtime_env(source)
        self.assertEqual(
            redacted,
            {
                "M5SW_ESPNOW_PEER_LMK": "<redacted>",
                "M5SW_ESPNOW_PEER_PMK": "<redacted>",
                "M5SW_ESPNOW_PEER_PUBLIC_MAC": "<redacted>",
                "M5SW_I2C_TRACE": "1",
            },
        )
        self.assertEqual(source["M5SW_ESPNOW_PEER_LMK"], "secret-lmk")
        self.assertEqual(
            device_service_runtime.redacted_runtime_env(None),
            {},
        )

    def test_device_service_reexports_same_runtime_objects(self):
        self.assertIs(
            device_service.PRIVATE_RUNTIME_ENV,
            device_service_runtime.PRIVATE_RUNTIME_ENV,
        )
        self.assertIs(
            device_service.qemu_runtime_memory,
            device_service_runtime.qemu_runtime_memory,
        )
        self.assertIs(
            device_service.runtime_psram_mismatch,
            device_service_runtime.runtime_psram_mismatch,
        )
        self.assertIs(
            device_service.redacted_runtime_env,
            device_service_runtime.redacted_runtime_env,
        )


if __name__ == "__main__":
    unittest.main()

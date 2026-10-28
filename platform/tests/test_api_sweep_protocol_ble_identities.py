from __future__ import annotations

import importlib.util
from pathlib import Path
import sys
import unittest

from device_service import UNIFIED_BLE_IDENTITIES


ROOT = Path(__file__).resolve().parents[2]
API_SWEEP = ROOT / "tests/uiflow2/api_sweep"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot import {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ApiSweepProtocolBleIdentityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        sys.path.insert(0, str(API_SWEEP))
        cls.runner = load_module(
            "api_sweep_protocol_runner_for_identity_test",
            API_SWEEP / "run_protocols.py",
        )
        cls.probes = load_module(
            "api_sweep_protocol_probes_for_identity_test",
            API_SWEEP / "probe_protocols.py",
        )

    def test_runner_matches_service_advertisement_and_payload(self):
        for device in self.runner.DEVICE_CHOICES:
            with self.subTest(device=device):
                self.assertEqual(
                    self.runner.BLE_IDENTITIES[device],
                    UNIFIED_BLE_IDENTITIES[device],
                )

    def test_all_ble_groups_compile_for_each_device(self):
        for device in self.runner.DEVICE_CHOICES:
            identity = self.runner.BLE_IDENTITIES[device]
            for group in (
                "ble-nus",
                "m5ble-server",
                "ble-client",
                "m5ble-client",
            ):
                with self.subTest(device=device, group=group):
                    source = self.probes.build_program(
                        group,
                        {
                            "device_id": device,
                            "ble_identity": list(identity),
                        },
                    )
                    compile(source, f"<{device}-{group}>", "exec")
                    self.assertIn('CONFIG["ble_identity"]', source)
                    self.assertNotIn(
                        '{"cores3":["M5-CORES3-UNIFIED"',
                        source,
                    )

    def test_model_blocker_names_the_selected_device_family(self):
        core2 = self.runner.stock_radio_model_blocker({}, "core2")
        self.assertIn("Core2", core2["reason"])
        self.assertNotIn("ESP32-S3", core2["reason"])

        sticks3 = self.runner.stock_radio_model_blocker({}, "sticks3")
        self.assertIn("stock sticks3 image", sticks3["reason"])

    def test_core2_ble_uses_the_native_hci_profile_and_requires_elf(self):
        self.assertEqual(
            self.runner.radio_profile("core2"),
            "core2-native-hci",
        )
        self.assertEqual(
            self.runner.radio_profile("sticks3"),
            "uiflow2-sticks3-unified",
        )
        with self.assertRaises(SystemExit):
            self.runner.require_core2_native_hci_elf(
                "core2",
                "ble-nus",
                None,
            )

    def test_exact_ack_notification_is_sufficient_without_host_cycle_tail(self):
        log = "\n".join(
            (
                "BLE_BUMBLE_CONNECTED",
                "BLE_BUMBLE_GATT_DISCOVERED 6e400001-b5a3-f393-e0a9-e50e24dcca9e",
                "BLE_BUMBLE_SUBSCRIBED 6e400003-b5a3-f393-e0a9-e50e24dcca9e",
                "BLE_BUMBLE_WRITE M5_CORE2_UNIFIED",
                "BLE_BUMBLE_NOTIFICATION_OK ACK:M5_CORE2_UNIFIED",
            )
        )
        self.assertTrue(
            self.runner.ble_nus_exchange_observed(
                log,
                "M5_CORE2_UNIFIED",
            )
        )
        self.assertFalse(
            self.runner.ble_nus_exchange_observed(
                log.replace("BLE_BUMBLE_SUBSCRIBED", "UNSUBSCRIBED"),
                "M5_CORE2_UNIFIED",
            )
        )


if __name__ == "__main__":
    unittest.main()

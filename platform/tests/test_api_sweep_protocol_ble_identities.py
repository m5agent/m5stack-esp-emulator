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

    def test_m5ble_source_is_injected_only_as_a_candidate_lane(self):
        candidate_source = "M5_CANDIDATE_SOURCE = 'reviewed'\n"
        source = self.probes.build_program(
            "m5ble-server",
            {
                "device_id": "core2",
                "ble_identity": list(self.runner.BLE_IDENTITIES["core2"]),
                "m5ble_source": candidate_source,
            },
        )
        compile(source, "<core2-m5ble-server-candidate>", "exec")
        self.assertIn("candidate_m5ble.py", source)
        self.assertIn("M5_CANDIDATE_SOURCE", source)
        self.assertIn("class _CandidateM5BLE", source)
        self.assertIn("_m5ble_namespace[_candidate_name]", source)
        self.assertEqual(
            self.runner.library_lane("m5ble-server", Path("candidate.py")),
            "candidate-source",
        )
        self.assertEqual(
            self.runner.library_lane("m5ble-server", None),
            "stock-frozen",
        )
        self.assertEqual(
            self.runner.candidate_source_sha256(
                "m5ble-server",
                {"m5ble_source": candidate_source},
            ),
            "3a89fc24a05f9f4859af7548ddd350cb766ced6e240a29740b8ca8afc0810bc1",
        )
        self.assertIsNone(
            self.runner.candidate_source_sha256("m5ble-server", {}),
        )
        self.runner.require_m5ble_source_group(
            "m5ble-server",
            Path("candidate.py"),
        )
        with self.assertRaises(SystemExit):
            self.runner.require_m5ble_source_group(
                "ble-nus",
                Path("candidate.py"),
            )

    def test_model_blocker_names_the_selected_device_family(self):
        core2 = self.runner.stock_radio_model_blocker({}, "core2")
        self.assertIn("Core2", core2["reason"])
        self.assertNotIn("ESP32-S3", core2["reason"])

        sticks3 = self.runner.stock_radio_model_blocker({}, "sticks3")
        self.assertIn("stock sticks3 image", sticks3["reason"])

    def test_client_groups_on_non_admitted_peer_device_are_not_run(self):
        self.assertTrue(
            self.runner.unsupported_ble_peripheral_peer("core2", "ble-client")
        )
        self.assertFalse(
            self.runner.unsupported_ble_peripheral_peer("cores3", "ble-client")
        )
        blocker = self.runner.stock_radio_model_blocker(
            {},
            "core2",
            "POST sessions: HTTP 400 peripheral BLE peer is admitted only for "
            "CoreS3 and Cardputer-ADV",
        )
        self.assertEqual(blocker["status"], "BLOCKED_FIXTURE")
        self.assertIn("NOT_RUN", blocker["reason"])

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

    def test_ble_server_probes_settle_disconnect_before_deinit(self):
        config = {
            "device_id": "core2",
            "ble_identity": list(self.runner.BLE_IDENTITIES["core2"]),
        }
        ble_nus = self.probes.build_program("ble-nus", config)
        self.assertIn(
            "server.close();time.sleep_ms(2000)",
            ble_nus,
        )
        m5ble = self.probes.build_program("m5ble-server", config)
        self.assertIn(
            "client.close();time.sleep_ms(2000)",
            m5ble,
        )


if __name__ == "__main__":
    unittest.main()

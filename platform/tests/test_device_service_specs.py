from __future__ import annotations

import os
from pathlib import Path
import stat
import sys
import tempfile
from unittest import mock
import unittest


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "platform/tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import device_service
import device_service_specs


class DeviceServiceSpecTests(unittest.TestCase):
    def test_public_symbols_are_same_object_reexports(self):
        for name in (
            "DeviceSpec",
            "load_device_specs",
            "backend_qemu_path",
            "backend_rom_dir",
            "core2_radio_qemu_path",
            "CORE2_WIFI_PROFILE",
            "UNIFIED_PROFILES",
        ):
            with self.subTest(name=name):
                self.assertIs(
                    getattr(device_service, name),
                    getattr(device_service_specs, name),
                )

    def test_catalog_loading_preserves_device_contracts(self):
        specs = device_service_specs.load_device_specs()
        self.assertEqual(len(specs), 14)
        self.assertEqual(specs["core2"].memory, "8")
        self.assertEqual(specs["core2"].flash_size, 16 << 20)
        self.assertEqual(specs["tab5"].service_kind, "tab5")
        self.assertEqual(specs["tab5"].flash_size, 16 << 20)
        self.assertFalse(specs["cardputer-zero"].supported)
        self.assertIn("separate Linux backend", specs["cardputer-zero"].reason)
        self.assertIn("cores3", specs)
        self.assertTrue(specs["cores3"].device_codes)

    def test_backend_overrides_accept_absolute_and_relative_paths(self):
        with mock.patch.dict(
            os.environ,
            {"M5_QEMU_XTENSA": "/tmp/custom-qemu"},
            clear=False,
        ):
            self.assertEqual(
                device_service_specs.backend_qemu_path(
                    "qemu-esp32lx6",
                    "ignored",
                ),
                Path("/tmp/custom-qemu"),
            )
        self.assertEqual(
            device_service_specs.backend_rom_dir(
                "qemu-esp32c6",
                ".work/custom-rom",
            ),
            (
                device_service_specs.ROOT / ".work/custom-rom"
                if not os.environ.get("M5_QEMU_RISCV32_ROM_DIR")
                else Path(os.environ["M5_QEMU_RISCV32_ROM_DIR"])
            ),
        )

    def test_core2_radio_override_enables_validated_profiles(self):
        with tempfile.TemporaryDirectory() as directory:
            qemu = Path(directory) / "qemu"
            qemu.write_bytes(b"test")
            qemu.chmod(qemu.stat().st_mode | stat.S_IXUSR)
            with mock.patch.dict(
                os.environ,
                {"M5_CORE2_RADIO_QEMU": str(qemu)},
                clear=False,
            ):
                spec = device_service_specs.load_device_specs()["core2"]
        self.assertEqual(spec.network_status, "validated")
        self.assertEqual(
            spec.network_profiles,
            [
                "core2-native-hci",
                "core2-native-vhci",
                "core2-unified",
                "core2-openmac",
                "core2-ble-advertise",
                "core2-hci-gatt",
            ],
        )

    def test_core2_radio_override_requires_executable(self):
        with tempfile.TemporaryDirectory() as directory:
            qemu = Path(directory) / "qemu"
            qemu.write_bytes(b"test")
            with mock.patch.dict(
                os.environ,
                {"M5_CORE2_RADIO_QEMU": str(qemu)},
                clear=False,
            ):
                with self.assertRaisesRegex(
                    device_service_specs.ServiceError,
                    "does not point to an executable",
                ):
                    device_service_specs.load_device_specs()


if __name__ == "__main__":
    unittest.main()

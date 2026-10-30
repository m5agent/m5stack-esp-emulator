from __future__ import annotations

import hashlib
import json
from pathlib import Path
import struct
import sys
import tempfile
from types import SimpleNamespace
import unittest


ROOT = Path(__file__).resolve().parents[2]
TOOLS = ROOT / "platform/tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import legacy_device_config
import device_service


FLASH_SIZE = 0x10000
CONFIG_OFFSET = 0xC000
CONFIG_SIZE = 0x1000


def config_bytes(value: dict, *, size: int = CONFIG_SIZE) -> bytes:
    payload = json.dumps(value, separators=(", ", ": ")).encode()
    encoded = len(payload).to_bytes(2, "big") + payload
    encoded += bytes([sum(encoded) & 0xFF])
    return encoded + b"\x00" * (size - len(encoded))


def legacy_image(value: dict) -> bytes:
    image = bytearray(FLASH_SIZE)
    image[0x8000:0x8020] = struct.pack(
        "<HBBII16sI",
        0x50AA,
        64,
        64,
        CONFIG_OFFSET,
        CONFIG_SIZE,
        b"config".ljust(16, b"\x00"),
        0,
    )
    image[0x8020:0x8040] = b"\xff" * 32
    image[CONFIG_OFFSET:CONFIG_OFFSET + CONFIG_SIZE] = config_bytes(value)
    return bytes(image)


class LegacyDeviceConfigTests(unittest.TestCase):
    def base_value(self) -> dict:
        return {
            "apikey": "7621FAE2",
            "wifi": [],
            "wifi-list": [],
            "board-name": "Core2",
            "screen_brightness": 80,
        }

    def test_decode_requires_checksum_and_legacy_schema(self):
        raw = config_bytes(self.base_value())
        self.assertEqual(
            legacy_device_config.decode_legacy_device_config(raw),
            self.base_value(),
        )
        length = int.from_bytes(raw[:2], "big")
        corrupt = bytearray(raw)
        corrupt[length + 2] ^= 1
        self.assertIsNone(
            legacy_device_config.decode_legacy_device_config(bytes(corrupt))
        )
        self.assertIsNone(
            legacy_device_config.decode_legacy_device_config(
                config_bytes({"other": True})
            )
        )

    def test_apply_selection_does_not_leak_password(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "core2.bin"
            image.write_bytes(legacy_image(self.base_value()))
            result = legacy_device_config.apply_legacy_wifi_config(
                image,
                flash_size=FLASH_SIZE,
                ssid="myssid",
                password="do-not-publish",
            )
            self.assertIsNotNone(result)
            assert result is not None
            self.assertTrue(result["changed"])
            self.assertNotIn("myssid", result)
            self.assertNotIn("do-not-publish", json.dumps(result))
            raw = image.read_bytes()[
                CONFIG_OFFSET : CONFIG_OFFSET + CONFIG_SIZE
            ]
            decoded = legacy_device_config.decode_legacy_device_config(raw)
            self.assertEqual(decoded["wifi"], ["myssid", "do-not-publish"])
            self.assertEqual(
                decoded["wifi-list"],
                [["myssid", "do-not-publish"]],
            )
            self.assertEqual(decoded["apikey"], "7621FAE2")
            self.assertEqual(decoded["screen_brightness"], 80)

    def test_apply_replaces_existing_credentials_and_is_idempotent(self):
        value = {
            **self.base_value(),
            "wifi": ["old", "old-password"],
            "wifi-list": [
                ["other", "other-password"],
                ["old", "old-password"],
            ],
        }
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "core2.bin"
            image.write_bytes(legacy_image(value))
            first = legacy_device_config.apply_legacy_wifi_config(
                image,
                flash_size=FLASH_SIZE,
                ssid="myssid",
                password="",
            )
            self.assertTrue(first["changed"])
            effective_sha = hashlib.sha256(image.read_bytes()).hexdigest()
            second = legacy_device_config.apply_legacy_wifi_config(
                image,
                flash_size=FLASH_SIZE,
                ssid="myssid",
                password="",
            )
            self.assertFalse(second["changed"])
            self.assertEqual(
                hashlib.sha256(image.read_bytes()).hexdigest(),
                effective_sha,
            )
            decoded = legacy_device_config.decode_legacy_device_config(
                image.read_bytes()[
                    CONFIG_OFFSET : CONFIG_OFFSET + CONFIG_SIZE
                ]
            )
            self.assertEqual(decoded["wifi"], ["myssid", ""])
            self.assertEqual(
                decoded["wifi-list"],
                [
                    ["other", "other-password"],
                    ["old", "old-password"],
                    ["myssid", ""],
                ],
            )

    def test_non_legacy_firmware_is_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "other.bin"
            image.write_bytes(b"\xff" * FLASH_SIZE)
            before = image.read_bytes()
            self.assertIsNone(
                legacy_device_config.apply_legacy_wifi_config(
                    image,
                    flash_size=FLASH_SIZE,
                    ssid="myssid",
                    password="",
                )
            )
            self.assertEqual(image.read_bytes(), before)

    def test_device_session_applies_legacy_wifi_overlay(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "core2.bin"
            image.write_bytes(legacy_image(self.base_value()))
            session = object.__new__(device_service.DeviceSession)
            session.runtime = device_service.QEMU_WIFI_RUNTIME
            session.spec = SimpleNamespace(id="core2", flash_size=FLASH_SIZE)
            session.virtual_flash = image
            session.network_config = {
                "wifi_ssid": "myssid",
                "wifi_password": "",
            }
            session.flash_info = {"transport": "test"}
            session.firmware_sha = "a" * 64
            events = []
            session._record_event = (
                lambda event, **payload: events.append((event, payload))
            )
            session._apply_legacy_wifi_config()
            self.assertEqual(
                session.flash_info["base_flash_sha256"],
                session.firmware_sha,
            )
            self.assertEqual(
                session.flash_info["legacy_wifi_config"]["partition_label"],
                "config",
            )
            self.assertEqual(
                events[0][0],
                "legacy_wifi_config_applied",
            )
            self.assertNotEqual(
                session.flash_info["base_flash_sha256"],
                session.flash_info["effective_flash_sha256"],
            )

    def test_device_session_overlay_is_scoped_to_core2_qemu_wifi(self):
        with tempfile.TemporaryDirectory() as directory:
            image = Path(directory) / "core2.bin"
            image.write_bytes(legacy_image(self.base_value()))
            before = image.read_bytes()
            for runtime, device_id in (
                ("qemu", "core2"),
                (device_service.QEMU_WIFI_RUNTIME, "sticks3"),
            ):
                with self.subTest(runtime=runtime, device_id=device_id):
                    session = object.__new__(device_service.DeviceSession)
                    session.runtime = runtime
                    session.spec = SimpleNamespace(
                        id=device_id,
                        flash_size=FLASH_SIZE,
                    )
                    session.virtual_flash = image
                    session.network_config = {
                        "wifi_ssid": "myssid",
                        "wifi_password": "",
                    }
                    session.flash_info = {"transport": "test"}
                    session.firmware_sha = "a" * 64
                    events = []
                    session._record_event = (
                        lambda event, **payload: events.append(
                            (event, payload)
                        )
                    )
                    session._apply_legacy_wifi_config()
                    self.assertEqual(events, [])
                    self.assertEqual(image.read_bytes(), before)

    def test_malformed_schema_is_not_treated_as_legacy_config(self):
        raw = config_bytes(self.base_value())
        self.assertIsNotNone(
            legacy_device_config.decode_legacy_device_config(raw)
        )
        malformed = config_bytes(
            {
                "apikey": "x",
                "wifi": [],
                "wifi-list": [1],
                "board-name": "Core2",
            }
        )
        self.assertIsNone(
            legacy_device_config.decode_legacy_device_config(malformed)
        )


if __name__ == "__main__":
    unittest.main()

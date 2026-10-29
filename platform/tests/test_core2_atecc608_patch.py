#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
PATCH = (
    ROOT
    / "patches/qemu-m5stack-peripherals/"
    "0085-core2-atecc608.patch"
)


class Core2Atecc608PatchTests(unittest.TestCase):
    def test_models_cryptoauth_i2c_command_data_plane(self) -> None:
        patch = PATCH.read_text()
        required = (
            '#define TYPE_M5_ATECC608 "m5.atecc608"',
            "ATCA_OPCODE_INFO  = 0x30",
            "ATCA_OPCODE_READ  = 0x02",
            "static uint16_t atecc_crc16(",
            "crc ^= 0x8005;",
            "atecc_set_wake(s);",
            "atecc_execute(s);",
            "qdev_prop_set_uint8(atecc, \"address\", 0x35);",
        )
        for marker in required:
            with self.subTest(marker=marker):
                self.assertIn(marker, patch)

    def test_uses_deterministic_locked_test_config(self) -> None:
        patch = PATCH.read_text()
        required = (
            "[4] = 0x00, [5] = 0x00, [6] = 0x60, [7] = 0x02",
            "[16] = 0x6a",
            "[86] = 0x00",
            "[87] = 0x00",
            "No production\n+ * private key or certificate material is present",
        )
        for marker in required:
            with self.subTest(marker=marker):
                self.assertIn(marker, patch)
        self.assertNotIn("PRIVATE KEY", patch)

    def test_dma_link_start_reuses_descriptor_and_observes_dc(self) -> None:
        patch = PATCH.read_text()
        required = (
            "uint32_t m5_panel_dma_link;",
            "s->m5_panel_dma_link = value & 0xfffff;",
            "esp32_spi_m5_dma_panel(s, s->m5_panel_dma_link)",
            "bool command_phase = s->m5_dc_pin >= 0",
            "data, length, command_phase",
            "s->m5_panel_dma_link = 0;",
        )
        for marker in required:
            with self.subTest(marker=marker):
                self.assertIn(marker, patch)

    def test_patch_does_not_fake_firmware_or_relax_runtime(self) -> None:
        patch = PATCH.read_text()
        forbidden = (
            "M5SW_DISABLE_WDT",
            "qemu_clock_warp",
            "PRIVATE KEY",
        )
        for marker in forbidden:
            with self.subTest(marker=marker):
                self.assertNotIn(marker, patch)


if __name__ == "__main__":
    unittest.main()

"""Contract checks for the legacy ESP32 RMT data-path model."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
PATCH = (
    ROOT
    / "patches/qemu-m5stack-peripherals/"
    "0066-esp32-classic-rmt-legacy.patch"
)


class Esp32ClassicRmtPatchTests(unittest.TestCase):
    def test_legacy_driver_register_and_memory_contract(self):
        text = PATCH.read_text()
        required = (
            '#define RMT_CLASSIC_MEM_OFFSET   0x800',
            '#define RMT_CLASSIC_MEM_SIZE     0x800',
            '#define RMT_CLASSIC_CHANNELS     8',
            '#define RMT_CLASSIC_SYMBOLS_CH   64',
            '#define RMT_CLASSIC_INT_RAW      0x0a0',
            '#define RMT_CLASSIC_INT_ENA      0x0a8',
            '#define RMT_CLASSIC_INT_CLR      0x0ac',
            'RMT_CLASSIC_MEM_SIZE_SHIFT 24',
            'RMT_CLASSIC_TX_THRESHOLD_BIT(channel) (24 + (channel))',
            'memory_region_init_ram_ptr(',
            'qdev_get_gpio_in(intmatrix, ETS_RMT_INTR_SOURCE)',
        )
        for marker in required:
            with self.subTest(marker=marker):
                self.assertIn(marker, text)

    def test_tx_refill_and_completion_are_separate(self):
        text = PATCH.read_text()
        self.assertIn(
            's->int_raw |= BIT(threshold_bit);', text
        )
        self.assertIn(
            's->int_raw |= BIT(channel * 3);', text
        )
        self.assertIn(
            'count == capacity && (s->int_ena & BIT(threshold_bit))',
            text,
        )
        self.assertIn(
            'classic_rmt_capture_tx(s, channel, count);', text
        )

    def test_replaces_the_unimplemented_region(self):
        text = PATCH.read_text()
        self.assertIn(
            '-    esp32_soc_add_unimp_device(\n'
            '-        sys_mem, "esp32.rmt", DR_REG_RMT_BASE, 0x1000, 0);\n'
            '+    esp32_classic_rmt_init(sys_mem, intmatrix_dev);',
            text,
        )


if __name__ == "__main__":
    unittest.main()

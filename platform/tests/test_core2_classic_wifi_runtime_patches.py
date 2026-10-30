#!/usr/bin/env python3
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
PATCH_ROOT = ROOT / "patches/qemu-m5stack-peripherals"
VIRTUAL_TIME_PATCH = PATCH_ROOT / "0093-esp32-classic-wifi-virtual-time.patch"
STATION_DATA_PATCH = PATCH_ROOT / "0094-esp32-classic-wifi-station-data.patch"


def added_lines(patch: str) -> list[str]:
    return [
        line[1:]
        for line in patch.splitlines()
        if line.startswith("+") and not line.startswith("+++")
    ]


class Core2ClassicWifiRuntimePatchTests(unittest.TestCase):
    def test_timers_and_frame_timestamps_use_virtual_time(self):
        patch = VIRTUAL_TIME_PATCH.read_text()
        additions = "\n".join(added_lines(patch))
        self.assertEqual(
            additions.count("timer_new_ns(QEMU_CLOCK_VIRTUAL"),
            2,
        )
        self.assertGreaterEqual(
            additions.count("qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)"),
            6,
        )
        self.assertNotIn("QEMU_CLOCK_REALTIME", additions)
        self.assertNotIn("qemu_clock_warp", patch)

    def test_classic_wifi_trace_is_default_off(self):
        patch = VIRTUAL_TIME_PATCH.read_text()
        self.assertIn(
            'getenv("M5SW_CLASSIC_WIFI_TRACE") != NULL',
            patch,
        )
        self.assertNotIn("M5SW_DISABLE_WDT", patch)

    def test_station_data_uses_the_normal_slirp_conversion(self):
        patch = STATION_DATA_PATCH.read_text()
        additions = "\n".join(added_lines(patch))
        self.assertIn(
            "s->ap_state == Esp32_WLAN__STATE_STA_DHCP",
            additions,
        )
        self.assertIn(
            "s->ap_state == Esp32_WLAN__STATE_ASSOCIATED",
            additions,
        )
        self.assertIn(
            "s->ap_state == Esp32_WLAN__STATE_STA_ASSOCIATED",
            additions,
        )
        self.assertIn(
            "qemu_send_packet(qemu_get_queue(s->nic), ethernet_frame",
            patch,
        )
        self.assertIn('"host-rx"', patch)
        self.assertIn('"host-tx"', patch)
        self.assertNotIn("STA DHCP not implemented yet", additions)
        self.assertNotIn("STA DATA, NOT IMPLEMENTED YET", additions)
        self.assertNotIn(
            "Esp32_WLAN_create_dhcp_discover",
            additions,
        )
        self.assertNotIn(
            "Esp32_WLAN_create_dhcp_request",
            additions,
        )

    def test_patch_order_follows_existing_runtime_series(self):
        bootstrap = (ROOT / "scripts/bootstrap-unit-runtime.py").read_text()
        cache_gate = bootstrap.index(
            "0092-esp32-wifi-irq-cache-gate.patch"
        )
        virtual_time = bootstrap.index(
            "0093-esp32-classic-wifi-virtual-time.patch"
        )
        station_data = bootstrap.index(
            "0094-esp32-classic-wifi-station-data.patch"
        )
        self.assertLess(cache_gate, virtual_time)
        self.assertLess(virtual_time, station_data)


if __name__ == "__main__":
    unittest.main()

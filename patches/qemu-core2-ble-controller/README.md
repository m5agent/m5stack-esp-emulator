# Core2 classic ESP32 BT controller bootstrap

Last reviewed: `2026-10-24`

This patch follows `qemu-core2-openmac-wifi` and adds the missing classic
ESP32 Bluetooth shared-memory and control-register block used by stock
UIFlow2 NimBLE.

The model currently provides:

- the `0x3ff70000` 64 KiB Bluetooth RAM window;
- the `0x3ff71000` control-register page;
- BT core identity values checked by the ROM;
- free-running clock and completion-bit behavior for the ROM clock helpers;
- RWIP/BLE reset completion and fine-timer-mask state needed by
  `ea_prog_timer()`.
- zero-valued BB idle readback at the classic ESP32 `0x3ff5d000` page, so
  Wi-Fi/BLE coexistence can observe `phy_force_wifi_chan()` complete instead
  of spinning on an unimplemented all-ones region.

With this patch, the stock Core2 UIFlow2 probe reaches:

```text
CORE2_BLE_ACTIVE True
CORE2_BLE_CONFIG
CORE2_BLE_ADVERTISE_BEGIN
CORE2_BLE_ADVERTISE_OK
CORE2_BLE_RESULT: PASSED
```

This patch alone proves the guest-side NimBLE to VHCI control and
advertising-enable path. It does not provide a bit-exact controller or
baseband.

The later `tests/uiflow2/core2_native_vhci/` runner keeps the stock
internal-controller firmware and bridges the real VHCI H2C/C2H boundary to
Bumble. An external peer completes scan/connect/NUS subscribe/write and the
guest notification ACK 5/5. `unified_core2 --ble-transport native-vhci` keeps
board, WiFi, public DNS/HTTP and that BLE path in one guest 3/3, and
`qemu-unified/profile=core2-native-vhci` exposes it through Device Service.
The bridge still depends on GDB; RF, pairing/security, coexistence and physical
behavior remain out of scope.

Apply after the OpenMAC WiFi patch:

```bash
git apply /path/to/patches/qemu-core2-openmac-wifi/0001-esp32-openmac-wifi-model.patch
git apply /path/to/patches/qemu-core2-ble-controller/0001-classic-esp32-bt-controller-bootstrap.patch
git apply /path/to/patches/qemu-core2-ble-controller/0002-classic-esp32-bb-idle-readback.patch
```

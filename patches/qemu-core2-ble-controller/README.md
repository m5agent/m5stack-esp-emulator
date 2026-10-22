# Core2 classic ESP32 BT controller bootstrap

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

With this patch, the stock Core2 UIFlow2 probe reaches:

```text
CORE2_BLE_ACTIVE True
CORE2_BLE_CONFIG
CORE2_BLE_ADVERTISE_BEGIN
CORE2_BLE_ADVERTISE_OK
CORE2_BLE_RESULT: PASSED
```

This proves the guest-side NimBLE to VHCI to controller control and
advertising-enable path. It does not yet prove over-the-air advertising,
external discovery, connection, GATT, ACL data, or real hardware behavior.

Apply after the OpenMAC WiFi patch:

```bash
git apply /path/to/patches/qemu-core2-openmac-wifi/0001-esp32-openmac-wifi-model.patch
git apply /path/to/patches/qemu-core2-ble-controller/0001-classic-esp32-bt-controller-bootstrap.patch
```

# 2026-10-28: Core2 legacy VFS and WiFi fixture correction

## Scope

This diagnostic separates two independent problems found while replaying the
public legacy `UIFlow_Core2 v1.15.4` image:

1. the injected LittleFS image must be produced by the matching UIFlow
   LittleFS2 packer;
2. legacy startup reaches WiFi initialization and therefore needs the ESP32
   WiFi model that is present in the `qemu-wifi` Device Service runtime.

The result is **virtual-device validation**. Physical hardware, RF, cache
timing and electrical behavior are `NOT RUN`.

## Firmware and filesystem

| Item | Value |
| --- | --- |
| Public source firmware SHA256 | `18d77e28adfacf7e719a167bd0c3450b78357d13cb1d2f2a8b7bccc2248a909a` |
| Test image SHA256 | `893d353527e15ddda041a3977c48065325141fe6c4cba7508aa280c80e064d8e` |
| VFS partition | offset `0x520000`, size `0x6de000` |
| Native LittleFS2 payload SHA256 | `805e1acd12039e235bf2da7f1507275b3e1a83f9f0df0e53098c201b1f09aa7c` |

The test image keeps the public firmware and partition layout unchanged and
replaces only the VFS payload. Its `boot.py` prints
`CORE2_LEGACY_VFS_BOOT` before importing the legacy system UI.

## Previous diagnostic gap

The generic LittleFS image was not accepted by the legacy guest. The guest
reformatted the correct `vfs` partition and never executed the injected
`boot.py`. Packing the same directory with the checkout-provided
`tools/littlefs/prebuilt/littlefs2` changed the result to:

```text
BOARD NAME: M5STACK-CORE2
APIKEY: <serial value omitted from this summary>
CORE2_LEGACY_VFS_BOOT
```

The serial log has `575` bytes and SHA256
`f837bbcc8402c299cce8abc1ce0820c3f20b801f4e3b4e3ceceeb6823f7c08b7`.

The earlier direct-QEMU control also omitted
`-nic user,model=misc.esp32_wifi,id=wifi0`. In that path, the guest can poll
`0x60033d24` (the APB alias of `WIFI_DMA_OUT_STATUS`) with no WiFi device and
never reach the injected boot file. This is a diagnostic-fixture gap, not a
physical Core2 property.

## Device Service replay

The corrected image was run through `/api/v1` with `runtime=qemu-wifi`,
`profile=core2-openmac`, and the exact-time state/frame capture enabled.

| Result | Value |
| --- | --- |
| QEMU binary SHA256 | `3b56b49a6b8e9444ca6a22e236bad92caf50f24460985fa907c8d32ac689fcd9` |
| Pause target | `120.000000000 s` |
| Actual pause | `120.000000030 s` |
| CPU0 PC | `0x40249c5d` |
| CPU1 PC | `0x400e1ffd` |
| Serial bytes | `575` |
| Frame | `320x240`, `0` nonblack pixels |
| Frame SHA256 | `57580743a08a3f4ebdf57240cbcc997002ef63b7234531f946127f1495973f43` |
| Session ID SHA256 | `9002382dcb325ff8aa2421594283c1373fc0276a5e09677ad8a91a747e75277c` |

The injected `boot.py` marker appears, but neither the application setup nor a
non-empty frame appears by 120 virtual seconds. The former CPU1
`0x40100049` LVGL wait is not reproduced in this corrected WiFi-enabled run;
CPU0 instead executes the WiFi register/delay path around `0x40249c5d`.

## Normal WDT control

The same corrected image without `M5SW_DISABLE_WDT`, with the WiFi NIC
present, still resets. The captured serial contains both `TG1WDT_SYS_RESET`
and `TG0WDT_SYS_RESET` messages, with neither the injected boot marker nor a
non-empty frame. This is a diagnostic control; it does not identify a physical
watchdog limit.

## Classification

- Matching LittleFS2 VFS recognition: `PASS`
- Device Service WiFi-backed legacy boot to injected boot marker: `PASS`
- System setup and REPL: `NOT REACHED`
- Non-empty application frame: `FAIL`
- Normal-WDT legacy boot: `FAIL`
- `RUNTIME-03`: `OPEN`

## Reproduction

The small probe sources are in
[`tests/firmware/core2_legacy_vfs_probe`](../../../tests/firmware/core2_legacy_vfs_probe/).
The exact image and large serial/state traces remain in ignored local storage.
Use the Device Service `runtime=qemu-wifi` lane; do not use a no-NIC direct
QEMU black frame as evidence that legacy UIFlow has reached its display path.

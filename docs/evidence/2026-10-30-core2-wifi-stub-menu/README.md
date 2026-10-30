# Core2 legacy UIFlow menu after deterministic WiFi configuration

Date: 2026-10-30

Status: `DIAGNOSTIC_PASS`; original `RUNTIME-03` remains `OPEN`.

## Result

The current Core2 QEMU source, including the classic-panel DMA and TIMG
watchdog fixes, reaches the complete `UIFlow_Core2 v1.15.4` startup menu when
the normalized firmware VFS is changed only to stub `wifiWebCfg.config_by_web`.

The diagnostic VFS injects a `_DiagWifi` object through
`sys.modules["wifiWebCfg"]`; `config_by_web()` returns `True`. It does not
write panel pixels, bypass SPI/DMA, disable display transactions, inject QOM
input or patch the guest interpreter.

The final virtual-device frame is `320x240`, with `76,760` nonblack pixels and
`417` colors. It visibly contains the UIFlow title, Core2 version, and
App/Flow/Setup menu.

## Evidence

| Item | Value |
| --- | --- |
| Original normalized firmware | `4d2d648bd8707a1789d540366015a1b90dc816b66a04163048626ea29e333ed4` |
| WiFi-stub normalized firmware | `f4966a4a2a3983cc15f5752a28e9a04ef990f63ef868c3ce7ce8de3349871c1b` |
| Diagnostic QEMU | `7d03bb183a34cbbf8960a75e95703f92c2fec7fe6e14dad98707e9431caf83a4` |
| Runtime | `qemu-wifi`, `core2-openmac`, `icount shift=2`, uncapped diagnostic QEMU |
| WDT | disabled diagnostic control |
| Final frame SHA256 | `a4f683468cfb9edc70468efaabd23c226abbed7a3cdeaf6a397cab09c52a6078` |

Serial reached:

```text
BOARD NAME: M5STACK-CORE2
APIKEY: 7621FAE2
CORE2_LEGACY_ORIGINAL_BOOT_START
CORE2_LEGACY_ORIGINAL_BOOT_DONE
CORE2_LEGACY_WIFI_STUB_INSTALLED
CORE2_LEGACY_WIFI_STUB_CONFIG_BY_WEB
```

## Boundary

The original normalized image leaves its dedicated `wifi` partition
(`0xbff000`, size `0x1000`) erased. The stub bypasses that configuration
lifecycle, so this is not an original-firmware `RUNTIME-03` PASS. It proves
that the current display, LVGL and Core2 menu paths can render the complete
startup UI once WiFi configuration returns. The remaining original-firmware
work is to exercise a nonempty WiFi configuration and verify the real
`wifiWebCfg` path under normal WDT.

Physical hardware, RF, electrical behavior and physical cache/PSRAM timing are
`NOT RUN`.

# Classic ESP32 Bluetooth low-power and modem clock registers

Use the native Xtensa QEMU binary with patches 0195 and 0196 and the matching
classic ESP32 ROM directory. The command also accepts a pre-0195 binary and a
binary with patch 0195 alone.

```sh
python3 tests/firmware/stickc_plus2_bt_lp_clock/check_mmio.py \
  --rom-dir "$XTENSA_ROM_DIR" \
  --qemu "$PATCHED_XTENSA_QEMU" \
  --bt-clock-only-qemu "$BT_CLOCK_ONLY_XTENSA_QEMU" \
  --unpatched-qemu "$UNPATCHED_XTENSA_QEMU"
```

The test pauses the StickC Plus2 CPUs and exercises 32-bit guest-address-space
access through the QEMU qtest interface. It checks the ESP32 reset values, the
XTAL selector and divider readback, reserved-bit masking, modem clock enable
readback, zero writes, and restoration of the reset values after a QMP system
reset. The optional controls reproduce the original zero reads and show that
0195 alone preserves only the low-power clock settings.

| Address | Register | Reset | Writable mask |
| --- | --- | --- | --- |
| `0x3ff000cc` | `DPORT_WIFI_CLK_EN` | `0xfffce030` | `0xffffffff` |
| `0x3ff000d4` | `DPORT_BT_LPCK_DIV_INT` | `0x000000ff` | `0x00001fff` |
| `0x3ff000d8` | `DPORT_BT_LPCK_DIV_FRAC` | `0x02001001` | `0x0fffffff` |

The register oracle is ESP-IDF v5.5.5 `dport_reg.h` at
`b774170ff46c393eeb5e495ea37936038d3f4f4f`. The raw file SHA-256 is
`b56337324208a6cbb0a014a8cf98e880cb3ba55e4fe9a66475c777cd4efc1acb`.
[Modem clock enable](https://github.com/espressif/esp-idf/blob/b774170ff46c393eeb5e495ea37936038d3f4f4f/components/soc/esp32/register/soc/dport_reg.h#L1031-L1037)
and [Bluetooth low-power clock](https://github.com/espressif/esp-idf/blob/b774170ff46c393eeb5e495ea37936038d3f4f4f/components/soc/esp32/register/soc/dport_reg.h#L1088-L1138).

The controller test has no guest execution. Application acceptance uses the
unchanged JIGGLER 1.0 merged BIN in dedicated native Device Service sessions
under both the default and auto icount policies with the watchdog enabled.
PHY clock timing, RF behavior, and BLE HID pairing require separate validation.
See [issue #225](https://github.com/m5agent/m5stack-esp-emulator/issues/225) for
the original image identity and failing UART markers.

## BLE clock sampling

Run the paired qtest with two otherwise equivalent binaries to exercise the
ESP32 BLE time registers before and after patch 0198.

```sh
python3 tests/firmware/stickc_plus2_bt_lp_clock/check_ble_clock_snapshot.py \
  --rom-dir "$XTENSA_ROM_DIR" \
  --baseline "$PRE_0198_XTENSA_QEMU" \
  --candidate "$XTENSA_QEMU_WITH_0198"
```

A qtest-controlled virtual clock drives guest-address-space reads and writes.
The check covers an atomic coarse/fine sample, both sides of the ESP32 ROM
wake-up predicate, stable reads without a new sample, slot and 27-bit coarse
rollover, read-only latch access, and reset. It also checks that `0x3ff7101c`
continues to use the existing BR/EDR register behavior. The qtest accelerator
executes no guest instructions.

The ESP32 register offsets and widths come from the [ESP32 BTDM register map](https://github.com/esp-rs/esp-pacs/blob/e6d898ec67556b8d08b2fc6f6265da930954404f/esp32/svd/patches/btdm.yml#L336-L357).
The [Renesas DA14535 manual, Tables 69 and 70](https://www.renesas.com/en/document/dst/da14535-datasheet#page=166)
describes the same-IP 625 µs coarse clock, microsecond fine count, and
read-only snapshots. The descending fine phase is inferred from the [Dialog SDK reference calculation for a hardware-captured BLE phase](https://github.com/yangchengxcy/da14580/blob/4e1c3006a1cfa4697ed76889b95d754ab0ab54ef/xcy_gump/src/modules/app/src/app_project/prod_test/custom_lld_evt.c#L1961-L1972).
That calculation covers a packet timing capture from the same controller
family. The [ESP32 ROM wake-up check symbol](https://github.com/espressif/esp-idf/blob/b774170ff46c393eeb5e495ea37936038d3f4f4f/components/esp_rom/esp32/ld/esp32.rom.ld#L1278)
identifies the separate ESP32 consumer observed polling sample completion and
comparing the fine count with 467. Sample completion is synchronous in the
model. Physical timing of the sample request and the fine counter phase on
ESP32 remain unmeasured.

The [virtual-device evidence summary](ble-clock-evidence-summary.json) records
both qtest binaries and the unchanged original BIN in Device Service. The
final native build ran the original for 65 seconds each with default and auto
icount. Both controls recorded black frames and no watchdog or clock
assertions. The original instructions describe automatic startup with the
display off.

A separate 40-second default-icount session held and released C through
the StickC Plus2 GPIO35 input. The welcome screen did not appear. All 80
sampled frames were black, so the A/B controls were unexercised. The evidence
includes the firmware, runtime, ROM, framebuffer and ZIP hashes and records
that each ZIP was saved before its session stopped. A separate native trace
shows the original ROM crossing the BLE time wait and reaching a BR/EDR sleep
and wake path. Application UI readiness, BLE HID pairing, and physical
hardware remain unverified.

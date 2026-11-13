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

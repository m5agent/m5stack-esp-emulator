# Classic ESP32 Bluetooth low-power clock

Use the native Xtensa QEMU binary with patch 0195 and the matching classic
ESP32 ROM directory. A pre-0195 Xtensa binary is an optional negative control.

```sh
python3 tests/firmware/stickc_plus2_bt_lp_clock/check_mmio.py \
  --rom-dir "$XTENSA_ROM_DIR" \
  --qemu "$PATCHED_XTENSA_QEMU" \
  --unpatched-qemu "$UNPATCHED_XTENSA_QEMU"
```

The test pauses the StickC Plus2 CPUs and exercises 32-bit guest-address-space
access through the QEMU qtest interface. It checks the ESP32 reset values, the
XTAL selector and divider readback, reserved-bit masking, zero writes, and
return to the reset values after a QMP system reset. The optional negative
control reproduces the original zero reads and discarded writes.

| Address | Register | Reset | Writable mask |
| --- | --- | --- | --- |
| `0x3ff000d4` | `DPORT_BT_LPCK_DIV_INT` | `0x000000ff` | `0x00001fff` |
| `0x3ff000d8` | `DPORT_BT_LPCK_DIV_FRAC` | `0x02001001` | `0x0fffffff` |

The register oracle is ESP-IDF v5.5.5 `dport_reg.h` at
`b774170ff46c393eeb5e495ea37936038d3f4f4f`. The raw file SHA-256 is
`b56337324208a6cbb0a014a8cf98e880cb3ba55e4fe9a66475c777cd4efc1acb`.
[Espressif register definitions](https://github.com/espressif/esp-idf/blob/b774170ff46c393eeb5e495ea37936038d3f4f4f/components/soc/esp32/register/soc/dport_reg.h#L1088-L1138)

The controller test has no guest execution. Application acceptance uses the
unchanged JIGGLER 1.0 merged BIN in dedicated native Device Service sessions
under both the default and auto icount policies with the watchdog enabled.
See [issue #225](https://github.com/m5agent/m5stack-esp-emulator/issues/225) for
the original image identity and failing UART markers.

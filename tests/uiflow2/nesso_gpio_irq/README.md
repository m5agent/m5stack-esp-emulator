# Original Nesso UIFlow GPIO IRQ regression

Reviewed: `2026-11-14`. This fixture exercises the original UIFlow executable's
`machine.Pin.irq` through the real Nesso GPIO3 source, C6 GPIO controller,
interrupt-matrix source 30 and CPU ISR. `irq_probe._handler` is the only code
that increments the callback count. Pin/I2C polling synchronizes external input;
it never creates a callback or substitutes for the ISR assertion.

## Prerequisites and repeatable case

Use Python 3.12+, the repository LittleFS dependency, the rebuilt C6 runtime
containing GPIO patch 0024, and the matching C6 ROM. Supply original Nesso UIFlow
v2.5.3 BIN SHA
`fcbd588fa92bcd24c8d4ba8fcd8837b8df64a6d5be72771e520c1ed84af88c7a` at
`platform/.cache/firmware/nesso-n1/uiflow2.bin`. The matrix composes only the VFS
probe at `0x820000` (size `0x7df000`) into a 16 MiB Flash image. The resulting
image is not byte-identical to the original BIN; retain original, composed and
executable-partition hashes.

```sh
M5_QEMU_RISCV32="$qemu_binary" M5_QEMU_RISCV32_ROM_DIR="$rom_directory" \
  PYTHONPATH=.work/py python3 tests/uiflow2/run_peripheral_matrix.py \
  --case nesso-gpio-irq --out-dir "$private_evidence_directory"
```

The case selects C6 USB Serial/JTAG console index 2 because that is where this
original firmware prints. UART0 and UART1 are retained separately. It waits for
the guest's stage marker before each real key down/up or 0.5-second touch input;
input acceptance alone cannot pass a check. `input-steps.jsonl` records actual
QMP events and relative times. Final acceptance requires all 16 serial checks
and the green pixel at display coordinate `(4,4)` on the 135×240 framebuffer.

The 16 checks cover disabled IRQ negative controls, falling/rising/both edge
callbacks, held-edge silence, primary PI4IOE status acknowledgement while touch
still holds GPIO3, last-source release and an already-acknowledged button release.
Do not run `M5.update()` concurrently: it could acknowledge this shared source.
Do not lengthen the touch pulse or lower assertions to obtain a passing result.

## Visible Device Service validation

For application-style validation, use the ordinary merged-firmware service path:
compose these three `.py` files locally with `uiflow_source.build_uiflow_source_image`,
upload the result to `/artifacts`, import through `/firmware/import`, then create
a normal Nesso `runtime=qemu` session. Nesso is not admitted to online program or
UIFlow source-upload APIs; do not expand those lists for this test. Mirror the
case's stage markers with real `/input` requests. Read its separate
`usb-serial-jtag` serial channel, request `/reset`, and repeat the complete
sequence in the same session using a fresh serial offset. Capture ZIP including
Flash before stop, stop with `purge=0`, and verify guest, lease, Flash and owned
service cleanup while retaining history.

The dated service comparison passed two 16-check rounds on the new runtime;
the same composed image on the old runtime kept every callback count at zero.
Both passed all source-level negative controls and retained original executable
bytes in the evidence Flash. See the
[bounded evidence](../../../docs/evidence/2026-11-14-c6-gpio-irq/README.md).

This case does not establish NMI/source 31, sleep/wake/filter timing, BMI270
interrupt generation, FT6336 trigger pulses, browser-WASM or physical electrical
behavior. Five trigger types and level-mask/rearm controls are separately tested
by the [ESP-IDF probe](../../firmware/esp32c6_gpio_irq/README.md).

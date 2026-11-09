# StickS3 USB OTG device-mode regression

This probe exercises the ESP32-S3 DWC2 FIFO and interrupt path with the original
StickS3 Bit Pirate v1.6 merged binary from
[the upstream release](https://github.com/geo-tp/ESP32-Bit-Pirate/releases/tag/v1.6).
Verify its SHA-256 before uploading it.

```text
a93557398b87a50ac1bbd99ff98e93fb842bff0f0f3634d463d4d53497f8747e
```

1. Build the native Xtensa runtime including
   [patch 0172](../../../patches/qemu-m5stack-peripherals/0172-sticks3-usb-otg-device.patch).
   Include [patch 0174](../../../patches/qemu-m5stack-peripherals/0174-sticks3-usb-otg-reset-fence.patch)
   for the reset recovery check.
   Start an owned loopback Device Service with a separate state directory and
   token file, and point it at that QEMU and its ROM directory. The validated
   transport is `M5_SERVICE_FLASH_MODE=host-image`.
2. [Upload the original merged image](../../../docs/device-service-api.md#upload-and-boot-an-arbitrary-merged-image)
   and start an owned `device_id=sticks3` session using `runtime=qemu`.
   Wait for the service to report `running`.
3. Run the probe with the owned API URL, session and token file.

```sh
python3 tests/firmware/sticks3_usb_otg/run_test.py \
  --api "$OWNED_SERVICE_API" --session "$OWNED_SESSION" \
  --token-file "$OWNED_TOKEN_FILE"
```

The virtual host reads guest descriptors, sets the device address and
configuration, and verifies CDC line coding at 115200, 57600 and 115200 baud.
It selects the guest's USB Serial menu entry through the StickS3 B and A keys,
sends an empty input line on CDC bulk OUT and reads the terminal prompt on CDC
bulk IN. It also reads the guest HID report descriptor. The caller collects
same-session evidence before stopping with `purge=0&retain_flash=0`.

The model's trusted local QOM controls at `/machine/soc/usb-otg` accept
`reset`, `setup HEX`, `in EP` and `out EP [HEX]` in `host-packet`.
Read `host-response` for `ACK`, `NAK`, `STALL`, `DETACHED`, `ERROR`
or a `DATA:` response followed by its hex bytes. `host-state` reports
attachment, the guest-programmed address and FIFO or Buffer DMA mode.

The [dated evidence](evidence-summary.json) retains the previous runtime's
TinyUSB installation failure and distinguishes CDC class I/O from the later
bulk exchange. The result covers the full-speed FIFO device path. Buffer DMA
guest execution, HID report I/O, MSC I/O, controller host mode, USB Serial/JTAG,
browser-WASM and physical USB are outside this result.

The separate paused-CPU check replays the controller's receive FIFO flush
and interrupt acknowledgments through MMIO. The early SETUP must receive NAK
until both interrupt flags have been acknowledged. The optional older
runtime proves that the unfenced controller acknowledged and then discarded
the early packet. This check is separate from the original-firmware probe.

```sh
python3 tests/firmware/sticks3_usb_otg/check_reset_fence.py \
  --qemu "$OWNED_QEMU" --rom-dir "$OWNED_ROM_DIR" \
  --unfenced-qemu "$OWNED_UNFENCED_QEMU"
```

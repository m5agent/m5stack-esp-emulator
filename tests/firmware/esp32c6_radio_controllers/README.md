# ESP32-C6 isolated radio controller regression

This ESP-IDF 5.5.4 fixture tests hardware registers used by the original
Meshtastic `2.7.20.79f469c` Nesso image. It does not replace guest functions or
interrupt handlers. Run the same BIN through dedicated Device Service sessions.

The checks are independent:

- the PHY microsecond counter at `0x600ad000` must advance without a host NIC;
- an armed WiFi RX descriptor must remain owned by hardware, with its buffer
  unchanged, when no virtual AP/backend exists;
- the Bluetooth AES engine at `0x600a9400` must read the programmed key and
  source buffer, encrypt one block, write the destination buffer and complete;
- an unsupported AES mode must not report success or modify the destination;
- the documented LPPERI RNG register at `0x600b2808` and public
  `esp_fill_random` API must both produce varying data.

The BLE register transaction comes from the original binary's
`r_ble_hw_encrypt_block` path (function identity retained in its own diagnostic
string): key at offsets `0x10..0x1c`, mode `0x08`, size `0x0c`, source/destination
`0x20/0x24`, DMA enables `0xb8`, start `0x04`, completion `0xc4`. This is bounded
coverage of its AES-128 ECB block operation, not documentation of all private
BLE registers. The independent cryptographic oracle is
[NIST SP 800-38A F.1.1](https://nvlpubs.nist.gov/nistpubs/Legacy/SP/nistspecialpublication800-38a.pdf),
plus the all-zero AES-128 vector. Apache NimBLE's
[LE Encrypt path](https://github.com/apache/mynewt-nimble/blob/master/nimble/controller/src/ble_ll_hci.c)
converts HCI byte order around the standard encryption block interface.

With ESP-IDF 5.5.4 activated:

```sh
idf.py -C tests/firmware/esp32c6_radio_controllers -B .work/c6-radio-controllers build
python -m esptool --chip esp32c6 merge_bin -o .work/c6-radio-controllers/merged.bin \
  0x0 .work/c6-radio-controllers/bootloader/bootloader.bin \
  0x8000 .work/c6-radio-controllers/partition_table/partition-table.bin \
  0x10000 .work/c6-radio-controllers/c6_radio_controllers_probe.bin
```

Upload to Device Service `nesso-n1` or `nanoc6`, `runtime=qemu`, without a NIC.
Require `C6_RADIO_TIMER_PASS`, `C6_RADIO_PEERLESS_PASS`, `C6_RADIO_AES_PASS`,
`C6_RADIO_AES_UNSUPPORTED_PASS`, `C6_RADIO_RNG_REGISTER_PASS`,
`C6_RADIO_RNG_API_PASS` and `C6_RADIO_READY`. Request the evidence ZIP
before stop with `purge=0`. The original Meshtastic BIN must be tested separately;
these markers alone do not prove its readiness.

Controls: the recipe through `0010` fails the timer and AES checks. Adding only
`0011-c6-isolated-wifi-presence.patch` fixes the timer while retaining the AES
failure. Explicitly attaching the existing virtual-AP NIC makes the peerless
check fail because it writes a real receive packet through the descriptor;
this is the positive control for the absence-of-traffic oracle. The final
candidate also includes `0012-c6-ble-aes-dma.patch`. Re-run the existing
`c6_qemu_wifi_probe` or unified Nesso fixture with an explicit backend to check
that configured networking still works.

Scope is virtual-device counter, MAC/DMA isolation and AES block behavior.
Native BLE link-layer interoperability, over-the-air WiFi/BLE, RF timing,
physical power and hardware security are NOT RUN.

Dated evidence separates [controller presence](presence-evidence-2026-11-13.json)
from [BLE AES and WiFi regressions](aes-evidence-2026-11-13.json). The original
image reaches NimBLE host sync and GATT registration after AES completion is
implemented, then encounters a further watchdog. A GDB sample in random-number
code is a diagnostic location, not sufficient cause attribution.

[RNG evidence](rng-evidence-2026-11-13.json) binds the raw-register negative
control and Nesso/NanoC6 positive runs to the same rebuilt fixture. The public
API already varies on the old runtime because IDF also mixes LP-timer data.
Patch `0013-c6-lpperi-rng.patch` connects the documented LPPERI data register
to QEMU guest-random; it does not claim physical entropy or security properties.
The original Meshtastic image has no panic or reboot in the bounded post-patch
observation, but its black frame still prevents an application-ready claim.

# StickS3 native AirMouseS3 HID

This regression uses the [original AirMouseS3 v1.0 merged release](https://github.com/Teapot174/AirMouseS3/releases/tag/v1.0).
The unchanged guest registers its own ESP32-S3 VHCI callbacks. A local Bumble
peer acts as the Bluetooth central and controller at that interface; the
stock NimBLE host still implements pairing, GATT and HID. The guest UARTs
remain on the normal board wiring.

Start a dedicated Device Service with the QEMU build containing the native
VHCI patch, a separate state directory and a private control token. Then run:

```sh
python3 tests/firmware/sticks3_native_hid/run_test.py \
  --base-url "$DEVICE_SERVICE_URL/api/v1" --token-file "$DEVICE_SERVICE_TOKEN_FILE" \
  --firmware "$AIRMOUSE_RELEASE_BIN" --evidence-out "$EVIDENCE_ZIP"
```

[Bounded evidence](evidence-summary.json) records the runtime SHA, four independent sessions, controller counters and NUS regression.

The test checks both the input image and composed Flash hashes, waits for
encrypted pairing and the HID notification subscription, verifies the peer
has seen zero reports before input, sends board BtnA down/up, and requires the
exact two four-byte reports `01000000` and `00000000`. It requests an evidence
ZIP before stopping the owned lease with history retained. The original BIN,
keys and full logs are excluded from the repository.

This covers native virtual HCI and mouse button reports on the pinned build.
Other firmware builds, IMU motion, real BLE RF and pairing security require
separate verification.

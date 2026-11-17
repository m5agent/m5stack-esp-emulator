# Native ESP-IDF LittleFS partition fixture

The probe mounts the LittleFS data partition (subtype `0x83`) through ESP-IDF
VFS with formatting disabled. It lists and reads `FIXTURE.TXT`, checks for its
previous `PROOF.TXT` write, and writes and rereads that proof after remount.

Build with [ESP-IDF v5.5.4](https://github.com/espressif/esp-idf/tree/735507283d5b2f9fb363a1901172dbd9e847945d)
and the pinned [LittleFS component 1.21.1](https://components.espressif.com/components/joltwallet/littlefs/versions/1.21.1).
The generated partition uses 4,096-byte blocks and a 64-byte name limit.
The run used `littlefs-python` 0.15.0. Run from this directory after activating
the SDK environment.

```sh
idf.py -B build build
python3 prepare_images.py --build build --out "$TEST_OUTPUT"
```

Start a dedicated native Device Service with its own state, port and token.
Upload the baseline and seed with `POST /api/v1/artifacts`. Register the
padded baseline as a merged image for Cardputer or Cardputer-ADV via
`POST /api/v1/firmware`. Create a native session with the returned firmware
ID and the following storage configuration.

```json
{
  "storage": {
    "filesystem": {
      "image_artifact_id": "<seed SHA-256>",
      "partition_label": "storage",
      "format": "littlefs"
    }
  }
}
```

Require `LITTLEFS_PROBE_READ seeded=1 listed=1 prior=0`,
`LITTLEFS_PROBE_REMOUNT wrote=1 restored=1 listed=1`, and
`LITTLEFS_PROBE_DONE` in the guest console. Reset the same session and require
`prior=1` in newly appended console data. A fresh baseline-only session must
mount and report `seeded=0 listed=0 prior=0`. Its guest should still write and
remount the proof. Compare the receipt's preboot Flash SHA with the baseline
replaced only in `0x110000–0x210000`. Request a same-session ZIP with
`include=manifest,serial,storage,flash` before stopping. Verify both uploaded
artifacts and live Flash outside the partition, then stop with `purge=0` and
`retain_flash=0`.

[Exact virtual-device summary](summary.json) includes both boards, the empty
volume control, and a separate ESP-IDF v6.1.1 Cardputer attempt. The latter
reached ESP-IDF sleep GPIO initialization but did not reach the application
marker in 50 seconds. Browser WASM and physical storage were not tested.

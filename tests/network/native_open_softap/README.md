# Cardputer open SoftAP fixture

The ESP-IDF application starts an open `fixture-ap-test` access point and
serves the fixed body `AP_FIXTURE_OK` at `/proof` on port 80. The
Device Service client joins the guest, runs DHCP and ARP, and verifies the
HTTP response through the native S3 Wi-Fi MAC and guest stack. The same
merged ESP32-S3 image runs on Cardputer and Cardputer ADV.

Build with ESP-IDF v5.5.4 at `735507283d5b2f9fb363a1901172dbd9e847945d`.
The exact tested input digest is recorded in [summary.json](summary.json).
A rebuild may produce different build metadata.

```sh
idf.py -C tests/network/native_open_softap -B "$BUILD_DIR" build
python -m esptool --chip esp32s3 merge_bin --fill-flash-size 8MB \
  --flash_mode dio --flash_size 8MB --flash_freq 80m -o "$MERGED_BIN" \
  0 "$BUILD_DIR/bootloader/bootloader.bin" \
  0x8000 "$BUILD_DIR/partition_table/partition-table.bin" \
  0x10000 "$BUILD_DIR/native_sta_fixture.bin"
```

Use a dedicated native Device Service with the QEMU build containing 0210,
separate state and a control token, and optional runtime ACL permission
`network.softap.probe`. Upload and register the merged BIN through
`/api/v1/artifacts` and `/api/v1/firmware`, then create a session with the
registered ID.

```json
{
  "device_id": "cardputer",
  "firmware_id": "<registered firmware id>",
  "runtime": "qemu-wifi",
  "ready_marker": "AP_FIXTURE_HTTP_READY",
  "network": {"profile": "cardputer-open-softap-fixture"}
}
```

Require `AP_FIXTURE_JOINED`, `AP_FIXTURE_LEASED`, and `AP_FIXTURE_HTTP_SENT`
on the same guest serial stream. Read `/sessions/{id}/network` for the
peer's body-hash receipt. Request the evidence before stop, stop with
`purge=0`, and check that the finalized pcap reports one DORA and one
bidirectional TCP payload flow for a single generation. After a QMP reset,
the peer must complete a second generation on the same session.
The finalized capture should contain both exchanges. Check zero active
leases after stop and verify the retained ZIP includes the pcap and peer
receipt.

Use the prior binary without 0210, an ACL without the profile permission,
or a custom guest-route request as negative admission controls. Lifecycle
verification covers two concurrent leases, graceful service shutdown, and
cleanup after a control process interruption. These are local native
virtual-device results. Browser-WASM, RF, encrypted guest APs, user firmware
portals, and Linux-worker execution remain outside this fixture.

## StickS3 button-gated provisioning

Build with `-D M5_FIXTURE_STICKS3_BUTTON=ON` and the same merge layout.
Use `device_id=sticks3`, `runtime=qemu-wifi`,
`network.profile=sticks3-open-softap-fixture`, and readiness marker
`PROVISION_WAIT_BUTTON gpio=11 level=1`. The firmware polls the board GPIOs
through ESP-IDF. It reads BtnB low on GPIO12 while remaining idle and
starts the AP after reading BtnA low on GPIO11.

Submit `{"kind":"button","control":"b","action":"hold","seconds":0.35}`
to `POST /api/v1/sessions/{id}/input`. Require
`PROVISION_IGNORED_BUTTON gpio=12 level=0` and an inactive guest AP.
Repeat with `"control":"a"` inside the fixture's DHCP discovery window.
Require the GPIO11 press marker before AP startup, guest association, DHCP
lease, and exact HTTP receipt. Reset the same session and repeat BtnA after
the idle marker. Expect two completed DORA transactions and two payload
flows in the finalized capture. A separate run without input must show
zero auth and association responses, DORA exchanges, and TCP flows.
See the [StickS3 evidence](sticks3-button-summary.json) for exact artifact
hashes and the no-input and wrong-button observations.

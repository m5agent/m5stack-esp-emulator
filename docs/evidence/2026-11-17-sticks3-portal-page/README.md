# StickS3 original first-boot setup page

**Virtual-device validation, 2026-11-17.** The original StickS3-Claude-Codex-Assistant v0.2.4 app emitted open `StickS3-Setup` beacons on first boot. In a standard Device Service StickS3 session, the peer completed 802.11 authentication and association, DHCP DORA and ARP through the guest Wi-Fi controller and network stack. It fetched the root page with one `GET /`, then independently reconstructed the guest's HTTP 200 from the retained Ethernet capture. The complete HTML body was 5,448 bytes and contained the `StickS3-Setup` heading and Wi-Fi configuration form. It hashed to `155b87edfafcd2bdf6142868c48b1bdc94c8b4b6a8ac7f4576baa68bbdae7854`. The capture and pre-stop ZIP were bound to the same session, and the native peer receipt matched the ZIP endpoint's network report. No physical button input was needed. [Dated receipt](summary.json)

The initial candidate got DHCP and ARP, then received a TCP reset on its first connection to port 80. WiFiManager starts the guest AP before its HTTP server. The second run also captured the first connection being refused, then completed with a fresh connection. The peer retries only an explicitly refused connection before the GET. This run held one per-session UNIX socketpair and had zero host IP backends. After stop the capture was finalized, mutable Flash was released, and the worker had zero active leases. [Original app](https://github.com/bulb888/StickS3-Claude-Codex-Assistant/blob/5faf4efaec9b9aa0d36fcb9514030cb9de649862/src/wifi_mgr.cpp#L156-L177) · [WiFiManager 2.0.17 AP and HTTP startup](https://github.com/tzapu/WiFiManager/blob/v2.0.17/WiFiManager.cpp#L685-L715)

With the same original Flash and the legacy peer profile on the same new QEMU, 200 beacons were observed and no authentication, association or DORA occurred. The separate ESP-IDF regression guest on the legacy profile still read BtnB and stayed idle, then completed DHCP and fixed HTTP after BtnA. After reset it completed a second exchange only after a new BtnA hold. Each control released its peer and all leases.

## Reproduce

Download `firmware.bin` from the [author's v0.2.4 release](https://github.com/bulb888/StickS3-Claude-Codex-Assistant/releases/tag/v0.2.4) and keep its bytes at Flash offset `0x10000`. Configure the ESP32-S3 bootloader for DIO, 80 MHz and 8 MiB using the QIO 80 MHz bootloader ELF and `boot_app0.bin` from the pinned Arduino core. Generate the partition table using the same core's `gen_esp32part.py` and the tagged author's `partitions_8MB_huge.csv`. Register the four segments using `/api/v1/firmware` with `kind=segmented`, offset/hash pairs from the receipt, and `device_id=sticks3`. Compare the composed Flash hash `9627c7bc4a313841b5e30477030af7c68d0b76c1172b7a46072938322ba3ec70`. [Author partition CSV](https://github.com/bulb888/StickS3-Claude-Codex-Assistant/blob/5faf4efaec9b9aa0d36fcb9514030cb9de649862/partitions_8MB_huge.csv) · [Pinned Arduino ESP32 core](https://github.com/espressif/arduino-esp32/tree/5e19e086c43d0fa5e5a596497ff8f11a0a43f6c2/tools)

Build native Xtensa with [`bootstrap-unit-runtime.py`](../../../scripts/bootstrap-unit-runtime.py), including 0214. Start a dedicated Device Service and enable the `network.softap.probe` runtime ACL operation for StickS3. Use this body with `POST /api/v1/sessions` and the registered firmware ID.

```json
{
  "device_id": "sticks3",
  "firmware_id": "registered-firmware-id",
  "runtime": "qemu-wifi",
  "network": {"profile": "sticks3-open-softap-portal"}
}
```

Wait for `softap_fixture.status=PASS` in `/sessions/{id}/network`, capture the setup frame and request the evidence ZIP before stop. Stop with `purge=0&retain_flash=0` and read the finalized network report. Require one DORA and one bidirectional TCP payload flow. Verify that reassembled server response length and body hash match the peer's receipt and that the request only reads the root page. Use `sticks3-open-softap-fixture` with the same firmware as the SSID negative control. The [SDK fixture procedure](../../../tests/network/native_open_softap/README.md#sticks3-button-gated-provisioning) exercises the legacy profile separately.

Credential submission, transitioning the original to STA, physical RF, and browser-WASM remain **NOT RUN**.

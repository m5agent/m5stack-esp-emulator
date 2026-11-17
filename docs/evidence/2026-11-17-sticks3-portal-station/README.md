# StickS3 original portal and station connection

**Virtual-device validation, 2026-11-17.** StickS3-Claude-Codex-Assistant v0.2.4 entered the open setup portal on its first boot. A Device Service peer read the original WiFiManager page and submitted the fixed open lab SSID. The same guest associated to the fixture AP using the native 802.11 model. It requested and received a station lease and replied to ARP from the assigned address. The terminal capture independently showed two distinct DHCP DORA exchanges, the portal GET and POST, two complete HTTP 200 bodies, and the station ARP reply after its ACK. The release-mode run used one session-owned Unix socketpair and zero host IP backends. Its ZIP, capture, frame, firmware, and runtime hashes are in the [receipt](summary.json).

The current-runtime diagnostic peer submitted the same normal form through the previous read-only backend. The original confirmed receipt and emitted 55 scan requests without a station association. During development, the new runtime first reached station DHCP discovery and sent the offer into RX DMA, but the guest did not send a DHCP request. Assigning infrastructure RX matches to the programmed station interface allowed DHCP to complete while the guest AP was still present. The legacy read-only profile on the candidate still showed one DORA and one HTTP flow.

## Reproduce

Assemble the original four segments using the pins from the [portal-page procedure](../2026-11-17-sticks3-portal-page/README.md). Start a dedicated Device Service with a native Xtensa build including patch 0217 and a configured ACL granting StickS3 `network.softap.provision`. Create a cold-boot session with the composed firmware ID and:

```json
{
  "device_id": "sticks3",
  "firmware_id": "registered-firmware-id",
  "runtime": "qemu-wifi",
  "network": {"profile": "sticks3-open-softap-provisioning"}
}
```

Read `/api/v1/sessions/{id}/network` until `softap_fixture.status` is terminal. Request the evidence ZIP while the session is running, then stop with `purge=0&retain_flash=0`. Compare the finalized pcap hashes and count separate client DORA handshakes. Reassemble the two bounded port 80 responses and compare them to the receipt. Match the second client's ARP reply to the address from its DHCP ACK. Verify the peer is released and the service has no active lease. The read-only control repeats the same setup with `sticks3-open-softap-portal` and its separate `network.softap.probe` permission.

The result covers first-boot setup and the local lab station path. Config persistence across reset, password-protected provisioning for this original, DNS/SNTP, live cloud, physical RF, and browser-WASM remain **NOT RUN**.

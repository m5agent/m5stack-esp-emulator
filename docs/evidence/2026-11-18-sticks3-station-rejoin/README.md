# StickS3 original station rejoin after reset

**Virtual-device validation, 2026-11-18.** The original StickS3-Claude-Codex-Assistant
v0.2.4 completed first-boot provisioning, then rejoined the same open local test AP
after each of two real guest resets. The app bytes remained identical in the
session's Flash. The guest's configured NVS differed from the cold image and
remained configured after both resets. Three boot ROM banners confirmed that
the guest rebooted. The native run was untraced.

An independent read of the session Ethernet pcap found one portal GET and one
form POST in the cold generation. It found two DHCP DORA exchanges in that
generation and one after each reset. Each station ACK was followed by a guest
ARP reply from the assigned address. A DHCP transaction ID recurred across
generations. The byte offset recorded before reset delimited each exchange,
and the pcap reader matched those boundaries to actual packet-record starts.
The evidence ZIP for each generation has the corresponding peer receipt.
[Hashes and cleanup](summary.json)

The previous frozen runtime with the same app and Flash composition completed
the cold exchange and saved settings. After reset its portal peer waited
for an AP lease while the guest scanned as a station. A separate development
candidate also failed when it required unique DHCP IDs between resets.
The release logic verifies DORA in the new capture interval and permits reuse.
A lost SYN during a cold form connection was reproduced independently. The
peer now retransmits the SYN before sending the fixed form at most once.

## Reproduce

Use the exact image and profile from the [cold provisioning procedure](../2026-11-17-sticks3-portal-station/README.md)
with a native Xtensa runtime including 0219. Grant `guest.reset`,
`network.softap.provision` and `flash.read` to the StickS3 session. Wait for
`softap_fixture.status=PASS`. Read the session Flash and obtain the evidence ZIP.
Call `POST /api/v1/sessions/{id}/reset` on that same lease. Require a new
generation with `station_reconnect=true`, station DHCP and ARP. Repeat once
and obtain a ZIP for each generation. Stop, finalize pcap, and read the finalized
network result. Verify the matching DORA comes after each generation's
`capture_start_offset`. The session must finish with the peer and Flash released.

The fixture stays on one local Unix socketpair. The result covers resets on
the established lease and an open test AP. Importing pre-provisioned Flash into
a new session, RF, protected access points, DNS/SNTP and cloud application
operations are outside this run.

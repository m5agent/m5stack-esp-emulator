# Exact-original S3-watch native WPA2 peer

This implementation targets the original S3-watch 0.1 (worked) merged image,
SHA256 `eb7f9425c07cffd972d0de479fc6c82d86af2aa51dc807d9829d5ee55add163b`.
Its unchanged firmware requests a WPA2-PSK SoftAP and serves read-only JSON at
`GET /api/state`. A visible WEB address proves an application state transition,
not authentication, a DHCP lease or delivered HTTP.

## Selected path

Add an opt-in WPA2 supplicant peer in the native S3 Wi-Fi model. Reuse the
existing MAC DMA path, management-frame construction, PBKDF2/PRF/MIC/CCM code
and Unix Ethernet stream. Add independent peer state for beacon/RSN selection,
open authentication, association, M1/M2/M3/M4, authenticated key-data unwrap and
packet/replay counters. A separate Device Service profile binds the exact
image, board, fixed original SSID and the privately supplied passphrase.
It carries no arbitrary destination, route or egress permission.

The existing Python SoftAP peer can provide DHCP, ARP and a bounded TCP HTTP
client after the radio handshake. A new application-specific peer validates
HTTP 200, JSON content type, the exact original response schema and `web=1`.
It never loads the HTML UI or calls `/time`, and cannot create IP sockets.
The native controller must withhold Ethernet delivery until the authenticated
peer is ready. Incorrect passwords, invalid MIC/key data, replay and reset
must not create a ready state or deliver application data.

A raw Python 802.11 peer would require a new bidirectional protected-frame
transport absent from the existing raw fixture. A host wpa_supplicant bridge
would require additional drivers, tools and a build/deployment path not present
in the sealed Linux image. Neither is a smaller source-faithful change than
extending the native peer.

## Controller and validation boundary

The existing S3 MAC TX interface presents hardware CCMP envelopes in guest DMA;
RX validates and decrypts in the model before descriptor delivery. The new peer
must explicitly exercise that boundary and must not label plaintext forwarding
as verified on-wire CCMP. Cryptographic known-answer and negative checks use
independent values, including RFC 3394 section 4.1 for AES key unwrap:
https://www.rfc-editor.org/rfc/rfc3394

Use a fresh complete Unit runtime prefix from QEMU
`40edccac415693c5130f91c01d84176ae6008566`. StopWatch's independent opt-in AP/STA
work is patch 0233; this peer follows as 0234. Preserve existing open fixtures
and authenticator behavior. No firmware source/BIN patch, direct guest ISR,
Python guest output, fake peripheral value or borrowed resident session is
part of this design.

Milestones: (1) source replay and protocol/crypto host controls; (2) candidate
native build; (3) exact original correct-password
and wrong-password Device Service runs, same-session frame/input/radio/DHCP/HTTP
receipts and ZIP-before-stop; (4) affected open-peer/STA regressions and bounded
handoff. Credentials and raw frames/logs remain private. A runtime build or
host test alone never grants guest PASS. Native Mac and Linux runs retain
separate source/runtime identities; neither establishes physical RF/security.

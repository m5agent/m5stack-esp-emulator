# Original S3-watch native WPA2 and read-only HTTP

This fixture targets **S3-watch 0.1 (worked)**, original merged BIN SHA256
`eb7f9425c07cffd972d0de479fc6c82d86af2aa51dc807d9829d5ee55add163b`.
It is distinct from All day watch. The BIN is neither modified nor checked in.
Patch 0234 follows the complete native prefix including StopWatch's 0233.

Use an agent-owned Device Service with that native runtime and its matching
ROM. The caller supplies the original SSID/passphrase privately; the service
admits the SSID hash and exact original firmware, while the passphrase must
actually complete the guest's authenticator handshake. No external network,
SLiRP/host forwarding, browser JavaScript, `/time` call or A sleep input is
used. Raw outputs contain private identifiers and must remain ignored.

```sh
python3 tests/network/native_s3_watch_wpa2/run_test.py \
  --url http://127.0.0.1:<owned-port> --token-file <private-token-file> \
  --firmware <original-bin> --network-file <private-network-json> \
  --out <ignored-private-output>
# Repeat with a fresh output directory and --wrong-password.
```

The network JSON contains `profile: "sticks3-s3-watch-wpa2"`,
`capture_pcap: true`, `wifi_ssid` and `wifi_password`; no other network
configuration is accepted. The runner waits 30 seconds after creation, captures
mature startup, sends B hold 2 seconds at sample 5, then B hold 2 seconds at
sample 15, with 2-second sampling intervals and 1-second input settling. It
captures the same guest's frames, serial, QOM and network result; requests a ZIP
before stopping with `purge=0`; verifies lease/Flash release; and reads the
stopped network result and ZIP. Its only HTTP request inside the guest is
`GET /api/state`.

The first B is **not** presumed to activate networking. Actual observations
show a mature initial address with a different open AP broadcast; first B
produces WEB OFF, second B produces the target SSID's WPA2 beacon and address.
The unchanged application skips AP configuration if `WLAN.active()` already
returns true, while its web-stop path disables the AP but retains the WLAN
object. The observed transition establishes the working input sequence; it
does not by itself prove which startup branch ran or attribute a firmware/SDK
root cause. The target WPA2 claim excludes the initial different open AP.

The original returns `t="--:--:--"` before its clock is set. That is a valid
response and does not require a clock fixture. An earlier oracle rejected this
HTTP 200 response; that failure is retained. The final parser accepts the
original unset-clock form, requires HTTP 200 and the exact JSON field/types,
and requires `web="1"`. No online clock synchronization is claimed.

Run the actual-C host controls against the same fully replayed source:

```sh
python3 tests/network/native_s3_watch_wpa2/host_test.py \
  --source <replayed-qemu-source> --deps <isolated-gcrypt-dependency-prefix> \
  --out <ignored-host-test-output>
```

This extracts the actual implementation and compiles ASan/UBSan checks using
libgcrypt. Independent known answers are [RFC 3394 section 4.1](https://www.rfc-editor.org/rfc/rfc3394)
and [RFC 3610 vector 1](https://www.rfc-editor.org/rfc/rfc3610). Controls cover
unwrap integrity/bounds, CCMP key/ciphertext/MIC rejection, RSN bounds, actual
hardware key selection, missing/duplicate/wrong key entries, pairwise/group
forwarding, replay and frame length limits. LeakSanitizer is not run on this
macOS path. These host checks do not replace the same-original guest runs.

The supported lane is non-QoS subtype 0 AP-originated IPv4/ARP, CCMP-128/PSK,
zero PMKID count and a nonzero GTK index. PMF negotiation, other ciphers,
general bridging and broad rekey interoperability are not qualified. Native
macOS results do not transfer to Linux or browser-WASM binaries. No physical
RF, power, memory-timing or hardware-security claim is made.

[Bounded execution summary](../../../docs/evidence/2026-11-23-s3-watch-native-wpa2/summary.json)
records exact runtime/source/ROM and positive, negative and earlier failed
observations. A pre-stop ZIP can still contain a CAPTURING summary; final DORA
and TCP counts are taken from the stopped same-session result and checked
against that ZIP's PCAP bytes. The separately retained stopped ZIP records the
final classification directly.

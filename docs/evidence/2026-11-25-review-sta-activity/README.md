# review-sta driver initialisation and conditional setup (2026-11-25)

Follow-up to [#238](https://github.com/m5agent/m5stack-esp-emulator/issues/238).
This is virtual-device validation on Cardputer ADV; it does not establish RF
behaviour or hardware results. Bounded results are in [summary.json](summary.json).

- `/network` now reports `wifi_initialized` and `reason`. On the ESP32-S3 NIC,
  an idle window in which the guest never programmed the Wi-Fi MAC is
  `NOT_USED` with `reason=wifi_not_initialized` instead of `PARTIAL`. The
  classic ESP32 NIC has no such trace and keeps `PARTIAL`.
- A UDP packet to `0.0.0.0` (a name that failed to resolve) is no longer egress.
  Bruce CN previously showed a false `FAIL host_egress_denied` after SNTP got NXDOMAIN.
- `setup_inputs` steps accept `until=joined`, so a reviewer can send bounded
  navigation input that stops once the station holds a lease.
- Replays: Bruce CN and CardOS-zh join and lease with the Enter navigation
  probe. Monster for Cyberspace associates and sends DHCPDISCOVER but never
  sends DHCPREQUEST after the peer OFFER, while CardOS accepts the same OFFER.
  That firmware stays open.

A probe is exploratory input. It does not prove that any specific application
feature works.

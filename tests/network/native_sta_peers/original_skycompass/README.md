# Original SkyCompass Satellite v3.6 STA replay

The saved original runs on Cardputer ADV. The Device Service receives the
immutable merged source artifact and performs its normal 8 MiB Flash
normalization. Semantic keyboard input advances the original start screen,
language selection, Wi-Fi scan and AP selection. Scan and connect use the
native ESP32-S3 Wi-Fi controller.

The dedicated Device Service starts the `cardputer-adv-local-time-fixture`
profile using one per-session Unix socketpair. The fixture responds to
DHCP, ARP, two time-service DNS names and fixed SNTP. It returns NXDOMAIN
for other DNS names. The profile has no host IP backend and accepts
neither forwarding nor caller-selected endpoints. The harness configures
a private runtime ACL. The `--withhold-ntp` control keeps DHCP and DNS active.

Use a native Xtensa runtime, matching ROMs, an installed Device Service
dependency directory and the saved original with SHA-256
`7c8ddd56e87a3b3ef5a69721b0847eb8461cb1833eb68eade918290e21894bf3`.

```sh
PYTHONPATH=<device-service-python-deps> \
  python3.13 tests/network/native_sta_peers/original_skycompass/run.py \
  --original-bin <saved-original-bin> --qemu <native-xtensa> \
  --qemu-sha256 <runtime-sha256> --rom-dir <matching-rom-dir> \
  --esp-emu <native-esp-emu> --out-dir .work/skycompass-sntp
```

Re-run with `--withhold-ntp` and a new output directory. Require one DORA
transaction in each capture, the exact fixture time in the original's
serial output for the positive replay, and a request with the reply
withheld plus no successful time sync in the negative replay. Collect
the ZIP before stopping and read the finalized capture after releasing
the lease and mutable Flash. Use `--deny-fixture` to verify ACL rejection
before a lease is created, or `--check-reset` to verify the next peer
generation has cleared the previous response. Raw frames and captures stay in ignored
storage. See [summary.json](summary.json) for bounded evidence.

This virtual-device replay covers the original Wi-Fi setup, DHCP, DNS
and SNTP. Public satellite updates, HTTP, RF, browser-WASM and Linux
namespace execution are outside this test.

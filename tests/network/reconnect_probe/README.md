# StickS3 reconnect probe

Last reviewed: `2026-10-25`

This UIFlow2 VFS replaces only `boot.py`/`main.py` in the validated StickS3
test image. It performs:

1. scan and association;
2. DHCP and controlled HTTP `/before`;
3. guest WLAN disconnect;
4. radio removal through the WiFi model's `radio-enabled` QOM property;
5. a scan that must return zero APs while the radio is down;
6. radio restoration followed by a non-empty scan;
7. re-association and a second DHCP lease;
8. controlled HTTP `/after`.

Build the image from the validated unified app:

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/run_profile_ui_test.py \
  --base /tmp/m5-sticks3-unified-public.bin \
  --machine m5sticks3 \
  --files-dir tests/network/reconnect_probe \
  --vfs-offset 0x641000 \
  --vfs-size 0x1BE000 \
  --flash-size 0x800000 \
  --expected-size 135x240 \
  --efuse-pkg-version 1 \
  --out-dir /tmp/m5-reconnect-probe \
  --build-only
```

Run the complete build/service/fault/evidence flow with one command:

```bash
python3 tests/network/reconnect_probe/run_test.py \
  --out-dir /tmp/m5-reconnect-probe
```

The runner rebuilds the image from the cached public StickS3 base and unified
build, starts a disposable Device Service unless `--service-url` is supplied,
drives the radio QOM state at the guest markers, stops with `purge=0`, and
requires radio state, two scans, two DHCP exchanges, two HTTP requests and pcap
all in the same session.

Create a Device Service `runtime=qemu-wifi` lease with
`profile=uiflow2-sticks3-wifi`, then poll the serial endpoint until
`RECONNECT DISCONNECTED`. Issue:

```bash
curl -sS -H 'Content-Type: application/json' \
  -d '{"action":"down","target":"radio"}' \
  "$BASE/api/v1/sessions/$SID/network-fault"

# after `RADIO_DOWN_SCAN 0` appears
curl -sS -H 'Content-Type: application/json' \
  -d '{"action":"up","target":"radio"}' \
  "$BASE/api/v1/sessions/$SID/network-fault"
```

The expected terminal marker is `RECONNECT RESULT: PASSED`. The host HTTP
fixture must log both `/before` and `/after`; the retained pcap summary should
show two DHCP exchanges and two TCP flows to the controlled endpoint. Evidence
must also record `RADIO_DOWN_SCAN 0`, a non-zero restored scan, the radio QOM
path and its false/true state changes.

The Device Service run is archived in
[`evidence-2026-10-24-radio-loss-pass.json`](evidence-2026-10-24-radio-loss-pass.json):
scan `1→0→1`, two DHCP DORA exchanges, HTTP 200 before/after, pcap PASS and a
same guest process throughout.

The current automated runner evidence is
[`evidence-2026-10-24-radio-loss-recovery-pass.json`](evidence-2026-10-24-radio-loss-recovery-pass.json):
16/16 checks PASS with pcap SHA256
`5b57d36ccf55dc6ef840f7fe28e41d56e7c9ece5f7bb2235e063f39eef979b9e`.

This is simulation-only evidence. It proves application disconnect and
radio/AP removal and recovery over the QEMU WiFi model data plane, not physical
RF, timing, WPA2/WPA3 security or DHCP server failure behavior.

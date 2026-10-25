# Firmware guest CNAME lifecycle

Last reviewed: `2026-10-25`.

Status: `PASS` in three independent Device Service leases for the closed
`NET-07` gate.

This fixture builds one stock StickS3 UIFlow2 VFS probe and runs it through a
single `runtime=qemu-wifi/profile=uiflow2-sticks3-wifi` Device Service lease.
The guest:

1. associates with the QEMU virtual AP and obtains DHCP;
2. resolves `alias.cname.test`, whose controlled resolver answer is a CNAME
   to `origin.cname.test` plus the terminal A record `10.0.2.2`;
3. sends an HTTP request to the allowed `10.0.2.2:18080` endpoint using the
   alias as the Host header;
4. confirms an unlisted name returns no address;
5. confirms `origin.cname.test` cannot connect on unlisted port `18081`;
6. emits one terminal marker while Device Service retains serial, resolver,
   HTTP, pcap and namespace cleanup evidence in the same lease.

Build the probe on a macOS host with the UIFlow2 VFS dependency:

```bash
PYTHONPATH=.work/py python3 \
  tests/network/cname_guest_lifecycle/run_test.py \
  --build-only \
  --out-dir .work/cname-guest
```

Run the build and Device Service lifecycle inside a privileged Linux arm64
container with QEMU and nftables:

```bash
docker run --rm --privileged \
  -v "$PWD":/workspace \
  -w /workspace \
  m5-qemu-p0-net:latest \
  bash -lc '
    apt-get update -qq &&
    apt-get install -y -qq libcapstone5 >/dev/null &&
    PYTHONPATH=platform/tools python3 \
      tests/network/cname_guest_lifecycle/run_test.py \
      --prebuilt-image .work/cname-guest/probe.bin \
      --qemu .work/M5StopWatch-QEMU/build/qemu-linux-arm64/qemu-system-xtensa \
      --rom-dir .work/M5StopWatch-QEMU/build/qemu-linux-arm64/pc-bios \
      --out-dir /tmp/m5-cname-guest
  '
```

Run the lifecycle in three independent containers/leases, then produce the
committed aggregate:

```bash
python3 tests/network/cname_guest_lifecycle/summarize_runs.py \
  --run .work/cname-guest-run \
  --run .work/cname-guest-run-2 \
  --run .work/cname-guest-run-3 \
  --diagnostic-failure .work/cname-guest-run-fail1 \
  --diagnostic-failure .work/cname-guest-run-fail2 \
  --out tests/network/cname_guest_lifecycle/evidence-2026-10-25-cname-guest-lifecycle-3x.json
```

The evidence must show the resolver chain, the guest resolution marker, the
controlled HTTP fixture request, the allowed and denied pcap flows, the same
session/lease identity and completed namespace/QEMU cleanup. A resolver-only
unit test, host HTTP request or different session cannot substitute for this
gate.

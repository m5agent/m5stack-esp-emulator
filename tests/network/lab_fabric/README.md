# Two-guest lab fabric

This fixture validates two real QEMU StickS3 guests on one private Linux lab
network. The passing evidence uses a QEMU socket L2 switch inside a private
network namespace; the host TAP/bridge helper is a separately tested Linux
primitive.

The namespace-local DHCP service assigns:

| Endpoint | MAC | Address |
| --- | --- | --- |
| Guest A | `02:4d:35:00:00:01` | `10.230.0.2` |
| Guest B | `02:4d:35:00:00:02` | `10.230.0.3` |

Guest B listens on TCP `19123`; guest A connects and exchanges a protocol
payload. Both guests use the real QEMU WiFi NIC and their own TCP/IP stacks.
The namespace has no default route or external interface. nftables keeps
input/output fail-closed and permits only loopback traffic for the switch
fixture.

## Current evidence

[`evidence-2026-10-24-two-guest-pass.json`](evidence-2026-10-24-two-guest-pass.json)
records all 17 gates:

- both guests complete `DISCOVER/OFFER/REQUEST/ACK`;
- reservations match guest A `10.230.0.2` and guest B `10.230.0.3`;
- guest A reaches guest B on TCP `19123` and receives the expected reply;
- the A and B pcaps each contain both TCP directions and payload hashes;
- the host control plane, public IPv4 and metadata endpoint are unreachable;
- the switch binds connection slots to configured MACs even when guest B's
  DHCP arrives before guest A's;
- no default route exists, neither endpoint has pending frames, and the
  namespace and helper sockets are removed.

The firmware and QEMU SHA256 values are stored in the evidence. This is
`virtual-device validation`, not physical hardware, RF, WPA2/WPA3, a production
worker or a malicious-firmware sandbox.

## Reproduce the QEMU test

Build the role images from the existing UIFlow2 StickS3 application:

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/unified_sticks3/make_image.py \
  --base platform/.cache/firmware/sticks3/uiflow2.bin \
  --build-dir .work/uiflow-core2-2.5.3/m5stack/build-M5STACK_StickS3-unified \
  --files-dir tests/network/lab_fabric/role_a \
  --out /tmp/m5-lab-fabric-a.bin

PYTHONPATH=.work/py python3 tests/uiflow2/unified_sticks3/make_image.py \
  --base platform/.cache/firmware/sticks3/uiflow2.bin \
  --build-dir .work/uiflow-core2-2.5.3/m5stack/build-M5STACK_StickS3-unified \
  --files-dir tests/network/lab_fabric/role_b \
  --out /tmp/m5-lab-fabric-b.bin
```

Run on Linux with the QEMU build containing
`0028-esp32-wifi-dual-guest-fabric.patch`:

```bash
python3 tests/network/lab_fabric/run_test.py \
  --qemu /path/to/qemu-system-xtensa \
  --rom-dir /path/to/pc-bios \
  --image-a /tmp/m5-lab-fabric-a.bin \
  --image-b /tmp/m5-lab-fabric-b.bin \
  --out-dir /tmp/m5-lab-fabric
```

The QEMU test requires `CAP_NET_ADMIN`, `CAP_SYS_ADMIN`, `iproute2` and
`nftables`. Set `M5_LAB_FABRIC_TRACE=1` to include per-frame switch tracing in
`switch.log`; tracing is off by default.

## TAP/bridge primitive

`check_fabric.py` independently checks namespace creation, a private bridge,
two TAP endpoints, namespace DHCP readiness, default-drop nftables rules and
cleanup without launching QEMU. This primitive additionally requires
`/dev/net/tun`:

```bash
python3 tests/network/lab_fabric/check_fabric.py \
  --out-dir /tmp/m5-lab-fabric-primitive
```

This primitive runs in CI, but it is not the source of the two-guest QEMU PASS.

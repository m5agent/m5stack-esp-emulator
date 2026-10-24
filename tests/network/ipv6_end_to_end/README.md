# UIFlow2 firmware guest IPv6 DNS and HTTP

Last reviewed: `2026-10-24`

This probe replaces the StickS3 UIFlow2 VFS with one application that:

1. associates with the QEMU virtual AP;
2. waits for the IPv6 link-local address and router advertisement;
3. checks that MicroPython exposes `AF_INET6`;
4. in namespace mode resolves an allowlisted AAAA record through the
   controlled resolver;
5. completes one IPv6 HTTP request to the exact `fec0::2` SLiRP host alias;
6. confirms a second, non-allowlisted port is blocked;
7. emits pass markers from the firmware guest and retains pcap evidence.

QEMU's user network maps the virtual IPv6 host `fec0::2` to the host loopback
socket. The sandbox canonicalizes that one address to `::1` for policy
evaluation, so it does not require the bridge/NAT gateway.

## Build requirement

The stock StickS3 UIFlow2 image contains `AF_INET6`, but its board
configuration disables `CONFIG_LWIP_IPV6_AUTOCONFIG` and the application does
not create a link-local address. With that image the probe stops with
`OSError: EHOSTUNREACH`; this is a firmware configuration boundary, not a
QEMU egress result.

For a dedicated guest data-plane test, apply the included test-only patch from
the `uiflow_micropython` root:

```bash
git apply /path/to/uiflow2-sticks3-ipv6-test-build.patch
source "$IDF_PATH/export.sh"
export MICROPY_MPYCROSS="$UIFLOW_DIR/micropython/mpy-cross/build-M5STACK_StickS3-ipv6/mpy-cross"
make -C "$UIFLOW_DIR/m5stack" \
  BOARD=M5STACK_StickS3 \
  BUILD=build-M5STACK_StickS3-ipv6 \
  build
```

Merge the generated application into a copy of the stock 8 MiB image at
`0x10000`, then reverse the source patch:

```bash
cp platform/.cache/firmware/sticks3/uiflow2.bin /tmp/sticks3-ipv6.bin
truncate -s 8388608 /tmp/sticks3-ipv6.bin
dd if="$UIFLOW_DIR/m5stack/build-M5STACK_StickS3-ipv6/micropython.bin" \
  of=/tmp/sticks3-ipv6.bin bs=1 seek=$((0x10000)) conv=notrunc
git apply --reverse /path/to/uiflow2-sticks3-ipv6-test-build.patch
```

The patch changes test configuration and calls
`esp_netif_create_ip6_linklocal()` after `IP_EVENT_STA_GOT_IP`. It does not
claim that a production or stock UIFlow2 build enables IPv6.

## Direct endpoint probe

Run without isolation to validate the same guest's IPv6 TCP/HTTP path:

```bash
python3 tests/network/ipv6_end_to_end/run_test.py \
  --qemu .work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa \
  --rom-dir .work/M5StopWatch-QEMU/build/qemu/pc-bios \
  --base-image /tmp/sticks3-ipv6.bin \
  --out-dir /tmp/m5-ipv6-e2e
```

The committed direct result is
`evidence-2026-10-24-guest-ipv6-direct-test-build-pass.json`: WiFi reaches
DHCP, `AF_INET6` exists, the guest completes HTTP/1.0 200 over
`fec0::2:18095`, and pcap records the same IPv6 TCP flow with `site-local`
scope. The evidence binds the base/probe/QEMU, test-build app and ELF hashes.

## Linux namespace probe

Run on Linux for controlled AAAA and denied-port checks:

```bash
python3 tests/network/ipv6_end_to_end/run_test.py \
  --isolation namespace \
  --base-image /tmp/sticks3-ipv6.bin \
  --qemu /path/to/linux/qemu-system-xtensa \
  --rom-dir /path/to/qemu/pc-bios \
  --out-dir /tmp/m5-ipv6-e2e
```

For a host without a Linux Python `littlefs` module, build the same probe image
on the host and pass it into the isolated Linux run:

```bash
python3 tests/network/ipv6_end_to_end/run_test.py \
  --isolation namespace \
  --base-image /tmp/sticks3-ipv6.bin \
  --prebuilt-image /tmp/sticks3-ipv6-namespace-probe.bin \
  --qemu /path/to/linux/qemu-system-xtensa \
  --rom-dir /path/to/qemu/pc-bios \
  --out-dir /tmp/m5-ipv6-e2e
```

The isolated run reads `isolation.json` and only marks namespace cleanup PASS
when the sandbox records `cleanup_completed`, QEMU process reaping, DNS close
and HTTP close. It no longer supplies a hard-coded cleanup result.

The Linux namespace AAAA and denied-port portion is now committed in
`evidence-2026-10-25-ipv6-namespace-aaaa-http-pass.json`: one UIFlow2
test-build guest resolves the controlled AAAA, completes IPv6 HTTP, receives a
block on the non-allowlisted port, produces pcap evidence, and leaves the
namespace/fixtures cleaned with QEMU reaped. It does not claim public IPv6
reachability, RF behavior, throughput or physical hardware. SLiRP maps all
addresses in its virtual IPv6 prefix to host loopback, so a denied
virtual-address assertion is not meaningful on that path; exact denied-address
behavior stays covered by the separate dual-stack egress gateway fixture.

# Core2 for AWS ATECC608 virtual-device validation

Date: 2026-10-29

Status: `PASS` for the bounded `RUNTIME-04` virtual-device path.

## Result

The public `Core2_For_AWS` factory firmware previously stopped during
ATECC608 initialization and rebooted before creating an application frame. The
new `0085-core2-atecc608.patch` adds a QEMU I2C slave at 7-bit address `0x35`
and implements the initialization data plane actually used by the public
firmware:

- CryptoAuthentication wake, idle and sleep words;
- count/opcode/parameter/CRC command packets;
- 32-byte config reads, 4-byte lock-word reads and Info revision;
- response framing and the CryptoAuthLib CRC16 polynomial `0x8005`.

The fixture uses a deterministic, locked test configuration with revision
`00 00 60 02` and serial bytes `01 23 45 67 89 AB CD EF 12`. The data zone is
zero-filled. No production private key, certificate or trust-root material is
present.

The same guest exposed a separate classic-ESP32 DMA issue: firmware writes the
descriptor address and the start bit in separate writes, and DMA command bytes
must be classified from the GPIO15 DC level. The patch retains the descriptor
address until start, observes DC for every DMA descriptor, and avoids replaying
a completed DMA transfer through the CPU data-register path.

## Reproduction

Run a Device Service built with the patch:

```bash
M5_QEMU_XTENSA=/path/to/qemu-system-xtensa \
M5_QEMU_XTENSA_ROM_DIR=/path/to/pc-bios \
python3 platform/tools/serve.py 8787 \
  --state-dir /tmp/m5-core2-atecc

python3 tests/firmware/core2_atecc608/run_service.py \
  --api http://127.0.0.1:8787/api/v1 \
  --image /path/to/Core2_For_AWS.bin \
  --qemu /path/to/qemu-system-xtensa \
  --attempts 3 \
  --out-dir /tmp/m5-core2-atecc-run
```

The firmware source must have SHA256
`22ee8c0f5d3c9640be370cb1a89496ed265b685d573b0e41d62320cf6288ff3a`.
The exact service-normalized image is
`104062aa0e6f52470f0c7f409d202af5d2dad5c3e5ee8f7e65815508a512ef3c`.

## Evidence

Three independent `/api/v1` sessions passed:

- serial moved from `atcab_init returned f0` plus `abort()` to
  `atecc608: ok: 60 02`;
- each session produced a live `320x240` frame with `76,800` nonblack pixels
  and `160` colors;
- all three frame PNGs have the same SHA256
  `f373994099403fea3b0e42d0dbf9b0486d2d9306cbb9c6cb27455794b602eb10`;
- evidence ZIPs were valid;
- every service session stopped with `purge=0`, retained history, released its
  lease and left no QEMU PID.

Exact hashes, observed ATECC commands and cleanup checks are in
[summary.json](summary.json).

## Boundaries

This is `virtual-device validation`, not `hardware validation`. It proves the
initialization and identity-read path needed by this firmware and a nonempty
application frame. It does not prove ECDSA key generation, signing,
certificate provisioning, production slot contents, private-key security,
electrical behavior, side-channel resistance or a physical trust root.

BMI270 initialization errors remain visible in this sample and are a separate
board-model question; they do not block the bounded ATECC result. The Core2
legacy UIFlow `RUNTIME-03` startup gap is also separate and remains open.

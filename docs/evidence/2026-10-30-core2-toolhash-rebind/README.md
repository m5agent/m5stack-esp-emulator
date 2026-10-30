# Core2 current tool-hash rebind

Date: `2026-10-30`

Validation category: **virtual-device validation**

Status: `4/4 PASS`

## Trigger

The SVC-03 boundary moves in PRs #58, #59 and #61 changed the tracked
`platform/tools/device_service.py` hash even though they were semantic
no-ops. The Core2 capacity evidence from PR #57 therefore remained bound to
the earlier service hash and could not be presented as a current-main result.

This rebind reran the same Core2 workload on `origin/main` commit
`3fc436e4aa99176ef3a4f7a2d35d25c973659219` after those three changes:

| Input/tool | SHA256 |
| --- | --- |
| Firmware | `ae094f4824d15499a5770018393660d1051866743dec52265552b6fc23eb2a23` |
| ELF | `5bec056bb775bcc94bc020e4fa411def097ea17b108dcd597d9cdab3c347db49` |
| QEMU | `54e7a7f7cd0ff6f5a1d6343c06563388f49c2b0abbca4cafb850876e57ed1254` |
| Runner before/after | `a9d1f678f2509e794bb4d98e4e4bd5540531df512adec8479543ca73be1da013` |
| `device_service.py` before | `5b4ed0f576dae7a23151049f753acdfd6bf1ddce2d44e3c3389413b2b6349acb` |
| `device_service.py` current | `a96b15061d104aa79e7af74b513e5881481acf62a847d5ba1e27c5997aa1bbbb` |

The runner froze inputs before the first lease and observed no asset drift.

## Result

Two independent zero-stagger `2x60s` batches each completed `2/2 PASS`:

| Batch | Result | Evidence SHA256 |
| --- | --- | --- |
| A | `2/2 PASS` | `c0e4ad6d7fe3c4d07c922c0cb7df2072baaf058fa774f00dd72f4e213bed935a` |
| B | `2/2 PASS` | `4409b748203c6ab4ddcc1c2b70c639fce7c8f7c85047f6ad58a8bbf0b8813dce` |

Across the four leases:

- real concurrency reached `2`, with independent QEMU processes and leases;
- every lease completed three contiguous 1 MiB PSRAM sweeps and readback;
- every lease completed two controlled HTTP and two public network rechecks;
- WiFi DHCP/HTTP, public DNS/HTTP and external NUS GATT passed;
- the frame was nonempty and the QOM snapshot contained 32 nodes;
- QOM-effective PSRAM remained `8 MiB`;
- pcap, evidence ZIP, bounded TCG, fixed `icount shift=5` and cleanup passed;
- native HCI health was `45/45` posts/consumed, 36 fast-path events and
  9 ACLs per lease;
- HLI errors, preallocation failures, dropped packets, panic, GATT timeout,
  session read errors and cleanup errors were all zero.

The runner reports `frame_sha256=MISMATCH` because independent live frames
contain different transient UI content. `frame_png=PASS` is the frame gate;
no pixel-hash equality was required for these independent leases.

## Boundary

This result only rebinds the current service/tool hash for the two-instance
regression. It does not establish:

- a fresh eight-instance cold-start rebind under the current host condition;
- nine-instance capacity;
- sustained throughput;
- bit-exact Bluetooth controller/baseband or physical RF behavior;
- physical PSRAM capacity, cache timing or hardware validation.

The nine-instance boundary remains rejected at the existing reproducible
`ble_hs_hci_process_ack` panic. The default per-device capacity remains `8`.

## Reproduction

Start the Device Service with the deterministic Core2 QEMU and run:

```bash
.work/py312/bin/python tests/uiflow2/core2_native_hci/run_service_5x.py \
  --base-url http://127.0.0.1:8899 \
  --image /path/to/unified-core2.bin \
  --elf /path/to/matching/micropython.elf \
  --qemu /path/to/qemu-system-xtensa \
  --attempts 2 \
  --concurrency 2 \
  --stagger-seconds 0 \
  --hold-seconds 60 \
  --require-psram \
  --out-dir /tmp/m5-core2-toolhash-rebind-a
```

Repeat once with a new output directory and a fresh independent batch.

# Core2 legacy handoff issuer and phase attribution

Date: `2026-10-29`

Validation category: **virtual-device validation**

Hardware validation: `NOT RUN`

## Result

This diagnostic correlates each normal flash/cache handoff episode with the
two dominant guest flash issuer PCs:

- `0x40093b57`: the BIN-bound application fast-read site previously associated
  with `0xBB/64`;
- `0x4006222c`: the ESP-ROM status-read issuer previously associated with
  `0x05/1`.

One 30-second wall-time normal-WDT run reached about `10.97 s` virtual time
with `8,234` complete handoff episodes:

| Issuer pair per episode | Episodes | Total wait | Mean | p50 | Max |
| --- | ---: | ---: | ---: | ---: | ---: |
| one fast read + one status read | `6,806` | `5.857184128 s` | `860.591 us` | `891.776 us` | `1.1048 ms` |
| no fast/status issuer | `1,342` | `1.192171392 s` | `888.354 us` | `887.904 us` | `4.750784 ms` |
| status only | `48` | `0.042949728 s` | `894.786 us` | `888.832 us` | `1.020256 ms` |

Episodes with no guest flash issuer cost approximately the same as a 64-byte
fast-read episode. The dominant cost is therefore not the data length or one
specific Flash command.

## Initiator phase split

A separate short run selected internal PCs in the initiator’s
`spi_flash_disable_interrupts_caches_and_other_cpu()` source-shape path. For
`1,974` complete episodes, the mean phases were:

| Phase | Mean |
| --- | ---: |
| initiator prepare through `esp_ipc_call` source shape (`0x40087a25 -> 0x40087a31`) | `615.595 us` |
| after IPC return to `can_start` poll exit | `2.181 us` |
| `vTaskSuspendAll` source-shape call | `1.322 us` |
| priority change source-shape call | `34.083 us` |
| first cache-disable source-shape call | `101.104 us` |
| second cache-disable source-shape call | `52.053 us` |
| block wait to `complete` setter | `63.733 us` |

The first row is the dominant fixed cost. The `can_start` poll,
suspend/resume, cache-disable and observed Flash work together are much
smaller. The next model/debug target is therefore the cross-core IPC
handoff/wakeup latency, not the 64-byte Flash transfer.

## Negative controls

Two scheduling-only candidates were tried and discarded:

- shortening the contended-CAS RR quantum from `1 ms` to `100 us`;
- an experimental immediate-yield hook after the `can_start` store.

Neither reduced the normal-WDT handoff budget; both remained near the existing
`~0.78-0.80 ms` mean block wait and reset around `17.25 s`. The hooks are not
retained in the repository and are not product fixes.

## Evidence identity

- normalized firmware SHA256:
  `18d77e28adfacf7e719a167bd0c3450b78357d13cb1d2f2a8b7bccc2248a909a`;
- issuer-correlation QEMU SHA256:
  `7d9b1f43ecc5a9b842c370dd52981ae7eab1c71e996f5dbf26a61bb3b2c0f353`;
- phase-split QEMU SHA256:
  `d14e31e1270e2f42be44a46af2b3bc3c84ffa342ce83edcb424e123769922b27`;
- runtime: `qemu-wifi`;
- deterministic `-icount shift=5`;
- normal WDT enabled.

Both QEMU identities use the same 0089 source fixed point; the second binary
is a clean rebuild after discarding the negative-control hooks.

## Boundary

All PCs and source-shape names are BIN-bound. No matching private legacy ELF or
MAP is available. Startup UI, setup/REPL, non-empty frame, physical cache/Flash
timing and hardware validation remain `OPEN`/`NOT RUN`.

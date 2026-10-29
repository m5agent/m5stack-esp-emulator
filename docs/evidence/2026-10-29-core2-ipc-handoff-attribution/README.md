# Core2 legacy IPC/flash handoff stack attribution

Date: `2026-10-29`

Validation category: **virtual-device validation**

Hardware validation: `NOT RUN`

## Result

Three independent normal-WDT freezes at `17.200000 s` place CPU0 in the
same BIN-bound flash-cache block function loop:

```text
0x40087984..8e: nop / l8ui a8,a9,0 / beqz a8,0x40087980
```

The loop target is `0x3ffc7ec8`, and the exact register snapshot is stable
across all three runs:

- PC: `0x40087988`, `0x40087984`, `0x4008798e`;
- `A0=0x80088a31`;
- `A9=0x3ffc7ec8`;
- `A12=0x3ffbf2cc`;
- serial: 507 bytes, SHA256
  `e996276519b4f8882739ff1c494dcecba313c99278857a53a984c1c9986a1b62`.

The stack contains stable entries `0x400889c4`, `0x40087950` and
`0x800840a0`. BIN instruction shape matches public ESP-IDF
`components/spi_flash/cache_utils.c`:

- `0x40087950` is the `spi_flash_op_block_func` busy-wait candidate;
- `0x400889c4` is the `ipc_task` dispatcher that calls the selected callback;
- `0x4026306e` is the idle `waiti` path at later WDT-off windows, not this
  freeze point.

These are **BIN-bound source-shape matches**. There is still no matching
private legacy ELF/MAP, so they are not presented as exact linker symbols.

## CPU1 is doing work, not permanently stopped

CPU1 reached different PCs in the three runs:

- `0x40084312`;
- `0x4008448a`;
- `0x40095c5c`.

That variation rejects the interpretation that both vCPUs sit permanently at
one compiler-generated wait site. A separate same-binary freeze captured CPU1
inside FreeRTOS `xQueueGenericSend`, with `A0=0x801ec834`. On this BIN,
`0x801ec834` is the return site in `esp_ipc_call_and_wait`; its caller sends
the target-core semaphore, waits for acknowledgement and releases the global
IPC mutex.

Another run's CPU1 stack contains:

- return `0x801ec8d4` in the nonblocking `esp_ipc_call` wrapper;
- return `0x80087a31` after the flash-cache block callback is dispatched.

The supported conclusion is therefore narrower and more useful: CPU0 is
parked in the per-flash-operation block callback while CPU1 continues through
cross-core IPC and boot work. The old permanent-handshake-deadlock hypothesis
remains rejected.

## Sampled trace pairing correction

The default handoff trace records every 1024th routine event. A retained
`transaction-begin` line therefore cannot be paired with a later retained
`transaction-end` line as one transaction.

The pause runner now accepts `--trace-sample` and records the effective value
in every snapshot. A two-second `--trace-sample 1` control recorded:

- 13 transaction-begin and 13 transaction-end events;
- 11 receive-data events;
- all 13 paired begin/end virtual-time deltas were `0 ns`.

The ESP32 SPI transaction path is synchronous in the model. This control
rejects the apparent "one 1-byte RDSR takes 0.4 s" reading caused by pairing
sampled events from different transactions.

## Evidence identity

- normalized firmware SHA256:
  `18d77e28adfacf7e719a167bd0c3450b78357d13cb1d2f2a8b7bccc2248a909a`;
- QEMU SHA256:
  `75e7fa97424c859c6e1fe918dda203aa2c6509e9c81937893a15d2a4a46b6714`;
- runtime: `qemu-wifi`;
- icount shift: `5`;
- contended-CAS fair-yield candidate enabled for attribution only;
- normal WDT enabled; no watchdog timeout or WDT-disabled evidence is used
  as a fix.

## Next boundary

The next question is no longer "which anonymous vtable is stuck". It is how
often and for how long CPU0 is parked in
`spi_flash_op_block_func` while CPU1 advances startup, and which CPU1 boot
phase generates that flash/IPC workload.

`RUNTIME-03` remains `OPEN`: normal WDT still resets at TG0 stage 1 before
`BOARD NAME`, setup/REPL or a non-empty application frame.

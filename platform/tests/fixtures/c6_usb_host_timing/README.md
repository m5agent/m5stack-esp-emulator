# C6 USB Serial/JTAG host timing controls

This fixture exercises the actual C6 endpoint model before/after patch `0022`
and the upstream CDC interrupt consumer and connection monitor. It is a host C
regression, **not original-firmware execution or physical USB validation**.
The original Honeypot application remains `PARTIAL` pending the same-BIN
candidate runtime check. Earlier incomplete application logs remain evidence.

Run from the repository root (C compiler, Git, Python 3.12+):

```sh
PYTHONPATH=platform/tools python3 -m unittest discover \
  -s platform/tests -p 'test_c6_usb_host_timing_patch.py' -v
```

The test applies `0020` to the checked-in original C6 endpoint preimage in an
independent temporary Git root, checks both file hashes, then applies `0022`
and verifies reverse application. The actual controller functions are compiled
with ASan/UBSan. The chardev, virtual clock, interrupt line and ring buffer are
host stubs; no guest application runs on the host. The ISR and tick-hook control
flow are extracted from the files below. Only the C++ `HWCDC::isPlugged()` call
is bound to the same C connection-state reader; original source bytes stay intact.

## Source provenance

- [Arduino-ESP32 HWCDC.cpp, commit 3bfa3e0](https://github.com/espressif/arduino-esp32/blob/3bfa3e0a56c80305eec90f10e8318af8d8091bab/cores/esp32/HWCDC.cpp)
  (release tag `3.0.7`), SHA-256
  `29b6f2da994afc86b9c8b88c286f5ae039a756bc7316f20da0a8af1ee4df6cd9`.
- [ESP-IDF connection monitor, commit d7b0a45](https://github.com/espressif/esp-idf/blob/d7b0a45ddbddbac53afb4fc28168f9f9259dbb79/components/driver/usb_serial_jtag/usb_serial_jtag_connection_monitor.c)
  (release tag `v5.1.4`), SHA-256
  `6d5ee3b3d7824155ba956a973b7767e4b0e473fc4d0776c738a63c782f27a49f`.

Both fixture files are byte-identical to these Git objects and carry their
original Apache-2.0 notices; the license text is included. Their relevant code
paths match the original BIN disassembly, but this does not establish the
firmware's complete source/ELF identity or exact Arduino release.

For original BIN SHA-256
`4184ffc6b56f1742a926845d782f3b65c37246490cc6d3e1bfa067bff7b0c381`,
static inspection locates the CDC ISR at `0x42015dde`, connection-state reader at
`0x4201e688`, monitor tick hook at `0x40800c0c`, monitor initialization at
`0x4201e658`, and CDC write at `0x42015fcc`. The reader returns the byte at
`0x408182d8`; the monitor starts with three no-SOF credits. The ISR checks that
reader on IN_EMPTY and, if false, clears IN_EMPTY and returns without draining
the software TX ring. The setup prints after the softAP call without a button
condition. These are source/byte-path observations, not a new guest run.

## Model contract and controlled results

`0022` ports the already-used Xtensa `0177` independent-IN design to the C6
controller, while preserving C6 RX and host-presence gates. SOF uses an absolute
1 ms cadence. MMIO first observes host events whose virtual deadlines have
passed; it does not invent a new SOF within the same frame after W1C. Bulk IN
has an independent deadline; repeated WR_DONE does not postpone an existing
transaction. The 8 us empty-IN and 64 us data-IN values are **virtual host
scheduling parameters**, not physical USB timing measurements or a complete bus
scheduler. This remains an explicitly attached character-device host, with no
USB enumeration, host-controller or RF claim.

There are 30 before/after scenarios: 18 expose the old behavior and 12 preserve
existing behavior; all 30 pass after the patch. The controlled late-callback
sequences let guest monitor MMIO execute after the virtual SOF deadline but
before its timer callback. With the unchanged upstream ISR/monitor, the old
controller stops after 0, 64 or 128 bytes; the new controller drains the same
153-byte test queue in order. This establishes a reproducible model-level
failure mechanism, **not yet that these exact interleavings caused each recorded
Honeypot run**.

Other controls cover empty IN, full FIFO, repeated WR_DONE, absolute frame phase
and wrap, W1C, partial/zero/error chardev writes, disabled pads/external PHY,
closed or absent backend, RX retention, independent controller instances,
reset cancellation and unrealize. A final latched SOF is consumed only once
after host closure; four later no-SOF ticks disconnect the actual monitor.
Reconnection needs a new SOF. No constant connected state or constant SOF bit is
used. Native build and original-BIN smoke belong to the subsequent integration
step; this fixture does not grant those results.

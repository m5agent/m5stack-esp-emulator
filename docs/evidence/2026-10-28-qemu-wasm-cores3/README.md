# CoreS3 C/QEMU browser execution — 2026-10-28

The fixed CoreS3 UIFlow2 fixture executes the existing C/QEMU CPU, controllers,
board wiring, LVGL and PIR driver in Chromium WASM. A dedicated Device Service
owns visible sessions and transports the original UART, QMP and framebuffer
bytes. Node does not execute the guest or draw its frames. Service-side native
tools still prepare the virtual Flash; the public browser frontend is not yet
wired to this research backend.

**Overall port status remains PARTIAL.** The bounded offline fixture passes
with the explicit `vm-div8` clock profile and 64 KiB C stacks. This slows VM
virtual time and WDT expiration relative to wall time; it does not preserve real
CPU frequency or physical timing. Default wallclock still has a recorded LVGL
queue overflow. The result admits only this firmware, fixture and clock profile. The final
non-diagnostic build passes 58 checks across two full sessions; three further
cold sessions pass the narrower boot/frame/Unit-initial-state/evidence/cleanup
smoke. These five sessions are a bounded regression, not a long-duration claim.

## Fixes and negative controls

- `0006` fixes a real SHA callback return-signature mismatch with typed void
  wrappers around the original int-returning compressors.
- `0009` restores the main CPU C stack after an Emscripten 3.1.50 Asyncify
  Fiber/SjLj jump. The standalone C/libffi negative control drifts; corrected
  2 MiB and 64 KiB variants have zero drift and natural exits. Real CoreS3
  Flash-MMU observations have 64 flat entry/exit/read groups per guest.
  The separate `cpu_exec_step_atomic` setjmp is unmodified and unverified.
- Historical `0007` only enlarged the stack to 2 MiB; it delayed overflow and
  is **excluded** from the final 64 KiB configuration.
- Default wallclock r11 finished interactions but its second guest raised
  `schedule queue full`; its audited result is PARTIAL. Single/icount auto
  missed the bounded READY deadline, and fixed shift8 still raised queue full.
  Neither is submitted as a fix. Slow TCI timer-callback pressure is a plausible
  explanation; MTTCG alone has not been established as the cause.
- `0010` is an explicit VM elapsed-clock profile, default 1 and immutable after
  startup. The signed parser rejects negative-wrap/overflow inputs and accepts
  only 1..1024; 24 actual C parser/clock-arithmetic controls pass. Host monotonic
  and `cpu_get_ticks` remain unchanged. Divisor greater than 1 and icount conflict.

`0012` configures only Emscripten stdio QMP to use the existing default
main-loop context, preserving both guest CPU threads and the original in-band
command implementation. It no longer offers OOB. The r16 negative control
retains a real socket and progressing guest heartbeats throughout 40 seconds,
but fd0 polling in the independent QMP context stops; the original screendump
is still unread in the JavaScript queue. The underlying GLib/watch cause is
not established. The selected host I/O configuration and its actual startup
marker are bound to the final runtime; it adds no keepalive or fabricated reply.

## Functional and lifecycle evidence

Two fresh guests each render complete LVGL frames, reject a background touch,
count two button clicks, and observe PIR false→true→false through actual
QOM→GPIO→guest reads and changed/restored pixels. Frames converge to the full
RGB values of an independent native reference; this is not an atomic-frame
promise for every screendump. The old native runtime is an independent fixture
reference, not a latest-main or browser regression result.

Evidence ZIPs are collected before stop, then `purge=0` retains serial and last
frame while releasing the lease and virtual Flash. Both runtime instances exit
0 and all observed Workers per instance close before browser cleanup. Exact check
counts, final runtime, ZIP/source fingerprints, per-session stack observations,
clock/application probes and independent audit are in [summary.json](summary.json).

Active process-tree RSS samples are sums that can count shared pages more than
once, not PSS or peak memory. First create-to-READY includes Flash preparation;
reopen timing uses a different starting point. HTTP frame-capture latency is not
guest FPS. A fresh-heartbeat interval can observe approximate guest/wall time,
including serial forwarding and polling error; cached HMP CCOUNT is not evidence
of VM-clock freeze. The final run retains per-read sequence/host timestamps
for its short-pause no-new-serial assertion and a fresh post-resume heartbeat.

## Source and reproduction

1. Use Espressif QEMU base `40edccac415693c5130f91c01d84176ae6008566`,
   bootstrap's fixed 30 layers plus `0064`. The project merges main `805925d8`;
   `0011` ports its `0065/0066` added code into the frozen research context.
   This is 31 baseline layers plus two explicit context ports, **not** 33
   unchanged patch applications. See the exact [patch order](../../../patches/qemu-wasm-probe/README.md).
2. Apply `0001`, `0004`, `0005`, `0006`, `0009`, `0010`, then optional
   `0008`, `0011` and `0012`; library patches `0002/0003` apply to their own sources.
   The measured candidate includes the bounded `0008` diagnostics. Add actual link options `-sSTACK_SIZE=64KB`,
   `-sDEFAULT_PTHREAD_STACK_SIZE=64KB`, `-sSTACK_OVERFLOW_CHECK=2`; omit `0007`.
3. Use the [research transport](../../../scripts/qemu-wasm-browser/README.md)
   as `M5_QEMU_XTENSA` for a dedicated Device Service with its own port, state
   and token. Select reviewed WASM/ROM/Chromium explicitly and set
   `M5_WASM_CLOCK_PROFILE=vm-div8`. Leave user services untouched.
4. Import the hash-pinned official base and compose the two
   [fixture sources](../../../tests/browser-qemu/cores3_lvgl_pir/README.md)
   using the explicit normalized-base pin. Verify the Flash SHA, then create a
   visible `cores3`/`qemu` session with Port A PIR. Follow the serial/frame/input
   oracle, request evidence before stop, inspect retained history and repeat in
   a fresh session. QMP pause probes are backend diagnostics, not a new public
   Device Service pause API.
5. The [standalone Fiber/SjLj reproduction](../../../tests/browser-qemu/fiber_sjlj/README.md)
   and no-firmware transport self-tests have separate receipts; neither grants
   firmware PASS by itself.

Transport self-tests cover QMP, UART/HMP, cancellation and immediate reconnects.
Client socket errors are local to that connection; late QMP responses retain
request identity and are discarded for a closed client. Startup/fatal cleanup,
normal guest exit, and a reconnect capability ACK adapted only after real QEMU
`query-status` success remain distinct evidence paths. No peripheral value or
frame is substituted.

Raw source/build receipts, failed controls, serial, PNG/PPM, ZIPs and histories
remain in ignored local research storage and the local work-log archive. No
binary, SDK, ROM, token, private receipt or raw session dump is in source Git.
MEMFS guest writes are not synchronized to host Flash/eFuse/SD, so native
`retain_flash` and snapshot behavior do not transfer. Actual public interaction,
Pages COI/SW deployment, Safari/Firefox, radio/network/audio, other devices and
firmware, long-duration stability and physical hardware remain outside this
result. Full native peripheral matrix and hardware validation are NOT RUN.

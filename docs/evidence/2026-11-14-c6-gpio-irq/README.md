# C6 ordinary GPIO interrupt delivery

Reviewed: `2026-11-14`. **Virtual-device validation.** The old GPIO model carried
the board input level but did not deliver ordinary GPIO source 30 to the CPU.
Patch 0024 adds raw pending, per-pin CPU routing, five edge/level modes,
W1TS/W1TC, reset handling and the existing matrix connection. It preserves the
PI4IOE/touch shared GPIO3 source arbitration. No Python fake values or direct
ISR calls are used.

The [bounded summary](summary.json) retains old failures and new passes:

| Same firmware / input path | Old runtime | New runtime |
| --- | --- | --- |
| NanoC6 public ESP-IDF GPIO ISR | FAIL, 12/21; ISR count always zero | PASS, 21/21 |
| Nesso public ESP-IDF GPIO ISR | FAIL, 14/26; ISR count always zero | PASS, 26/26 |
| Original Nesso UIFlow `Pin.irq`, two rounds with reset | FAIL, 20/32; ISR count always zero | PASS, 32/32 |

Every old negative control preserved correct source/pad levels and disabled/held
behavior. All four IDF runs had exactly two ready boots and one requested reset,
no panic/watchdog markers, and complete owned-process/UART-thread cleanup. The
actual source-30 matrix routes were CPU interrupt 10 (NanoC6) and 11 (Nesso).
The same merged BIN and ordered UART/QMP inputs were used per board. IDF evidence
uses the checked-in direct-regression route; the IDF Device Service lane is
**NOT RUN**.

The two UIFlow runs used ordinary visible Device Service sessions, the same VFS
fixture and same 22 actual inputs, with two full 16-check rounds per session.
The old frame has a red result bar and the new frame a green bar on a 135×240
display. ZIP was captured before stop; each manifest entry's bytes/hash matched.
The application partition at `0x10000`, size `7405568`, stayed identical to the
original BIN both before and after execution: SHA256
`4743d8b5e3cf234b064dc01566fa1cce9e44b545ea72992081a2628b937a6ba4`.
Guest processes, leases, mutable Flash and owned services were released;
history was retained with `purge=0`.

The first service attempt failed before artifact/session creation because the
isolated checkout lacked the required flash-emulator path. It created no guest,
cleaned its owned service, and remains recorded as an infrastructure failure.
The later attempts supplied the existing tool's explicit path. This failure is
not counted as the GPIO negative control. Source binding was recorded after
execution: relevant service files match the original GPIO candidate commit;
a test-only input-step cherry-pick occurred during the baseline run and changed
none of those files. The candidate run started after that cherry-pick.

## Fixed identities and reproduction

- Upstream QEMU base: `febae182e132e4055529be423a818225ebddaa3a`.
- New C6 runtime: `69493c4edccaab5bc24961982ddb9097dda11c9b3418f9cdc0aaa2b27ae865a4`.
- Old C6 runtime: `80d92a6c6c68137a7813b8b7c519725aac350258078d9b244098eaabf82f63bf`.
- C6 ROM: `91db14c2419391308b108bac0b15fe3442a9c411cdd7f3fb088767c9fbc4b713`.
- Original Nesso UIFlow v2.5.3 BIN: `fcbd588fa92bcd24c8d4ba8fcd8837b8df64a6d5be72771e520c1ed84af88c7a`.
- Service VFS-composed BIN: `16255a35d2142a7f68363c79d3a083bab207e6c104b6a91d3563f8646889a3aa`.
- ESP-IDF v5.5.4: `735507283d5b2f9fb363a1901172dbd9e847945d`, clean complete checkout
  with 27 pinned recursive submodules. Earlier incomplete-SDK configure failures
  remain separate; the final build did not use that incomplete tree.

The service image is **not a byte-identical original BIN**: only VFS content was
composed; executable bytes and all bytes outside VFS were preserved. The fresh
runtime build replayed source patches in a new owned tree. Existing runtime
assets were not overwritten. Source/build receipts and private raw ZIP, serial,
input timeline and frame bytes remain retained outside Git; this folder contains
only bounded hashes and observations.

See the [GPIO patch and portable IDF probe](../../../tests/firmware/esp32c6_gpio_irq/README.md)
and [repeatable original UIFlow case](../../../tests/uiflow2/nesso_gpio_irq/README.md)
for build prerequisites, explicit artifact pins, UART commands, marker-gated
inputs, case invocation and cleanup. The portable IDF runner is extracted from
the executed private runner; its guest sequence and assertions are unchanged.
It was also executed independently on the same NanoC6 candidate image: 21/21
checks and owned-process/UART-thread cleanup passed.
The checked-in `nesso-gpio-irq` matrix case also passed: 16 serial checks,
11 marker-gated inputs, the green frame assertion and guest cleanup. Its final
run explicitly sets `M5SW_C6_BOARD=nesso-n1`; the earlier default-board PASS is
retained separately. Matrix composition additionally includes the unimported
common `rtc_probe.py`, so its composed BIN has a separate SHA
`623a45423230352e354eb2f6c2f5c2bc1f7bec8472c9f9149ade3e4f4981ad42`.
The complete native matrix and deployment remain separate pending gates.

NMI/source 31, sleep/wake/filter timing, BMI270 IRQ generation and FT6336 trigger
pulse timing remain **NOT IMPLEMENTED / not validated by this change**.
Existing held-level touch is exercised. Native-service, browser-WASM and
physical hardware results do not transfer to each other; no WASM rebuild,
physical electrical measurement, resident rollout or Burner submission is
claimed here.

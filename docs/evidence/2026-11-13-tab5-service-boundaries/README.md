# Tab5 service integrity and original-firmware comparison

Date: 2026-11-13. **#188 remains PARTIAL / OPEN.** These are native
**virtual-device validation** results through Device Service, not hardware or
browser results. [Exact bounded identities and outcomes](summary.json) retain
the original failures separately from the emulator-reference control.

## Service repairs

Normal Tab5 sessions already use complete `host-image` Flash preparation. The
obsolete fixed ranges in the alternate flasher were not the active service
path. This change instead rejects a changed input, repairs a corrupt same-sized
cache, verifies the complete session image, and records its application identity.
The reusable eFuse input and matching ELF become session-owned copies before
either P4 or C6 starts. Reset keeps the private eFuse state. The reference ELF
must match the actual application descriptor; an uploaded image with no matching
ELF executes without stale symbols, with frame/touch explicitly unavailable.
OTA uploads are preserved without assuming that a factory app is selected.

The older matching reference exposed a separate first-touch race: request
`(640,520)` first produced guest `(0,719,0)`, then the same request produced
`(640,520,1)`. The helper published the pressed flag before coordinates. It now
releases the mailbox, fills coordinates/size/sequence, and publishes the pressed
flag last. A fresh service session produces `TAB5_TOUCH 640 520 1` on its first
touch and `TAB5_TOUCH 640 520 2` after release/repress. The actual frame shows
the corresponding count. This is the existing diagnostic GDB mailbox path; it
does not establish a modeled touch controller or stock-firmware touch support.

## Same original V2.5.4, two runtime results

Both runs upload the same original BIN through `/api/v1/artifacts`, create a
`kind=merged` Tab5 firmware, then create an observable Device Service session.
Only trailing `0xff` padding completes the Flash. Both retain the entire original
application and omit the unrelated older reference ELF. Both collect the evidence
ZIP before stopping with `purge=0&retain_flash=1`.

| Runtime | Result on the original image |
| --- | --- |
| 0.51.0 | No Python/UI readiness. Direct GDB observations show PHY_RSTZ `0x0000000f` at `0x500a00a0`, but PHY_STATUS `0x00000000` at `0x500a00b0`, with no PLL lock. PC sample `0x4ff09a1a` is in the idle path. |
| 1.0.0-rc2 | Repeated illegal-instruction panic: MEPC `0x4ff0255c`, MTVAL `0x34602773`, MCAUSE `2`. This exact original BIN instruction reads CSR `0x346`. |

ESP-IDF v5.5.5 explicitly defines [old P4 `mintstatus` as CSR 0x346](https://github.com/espressif/esp-idf/blob/v5.5.5/components/riscv/include/esp_private/interrupt_clic.h)
when `CONFIG_ESP32P4_SELECTS_REV_LESS_V3` is set; newer silicon uses `0xfb1`.
The rc2 [CLI documentation](https://github.com/espressif/esp-emulator/blob/v1.0.0-rc2/docs/guides/CLI.md#esp32-p4-images-built-for-rev-0x--1x-silicon)
requires a rev0 ROM and matching revision eFuse for these older images. These
runs use that configuration. Its CLI/help expose no separate CLIC compatibility
switch. The [rc2 release](https://github.com/espressif/esp-emulator/releases/tag/v1.0.0-rc2)
changed unsupported-CSR behavior and incorporates rc1, which was tagged but not
published. No newer stable DSI fix was available in the inspected releases.

The minimum upstream work is revision-aware old-P4 CLIC CSR behavior, including
`mintstatus` reads, followed by the DSI PHY state machine: valid reset/clock/PLL
configuration must produce the corresponding lock/status transitions that
`dsi_phy_ll_is_pll_locked` reads. A forced ready bit is not an implementation.
The public upstream repository distributes binaries, docs and helper sources;
its emulator core is unavailable for a local source repair. No original
instruction or runtime binary was patched, and no PLL-ready value was injected.

## Reproduction and remaining gates

Configure the Tab5 backend with the runtime/ROM/C6/ELF hashes in `summary.json`,
an isolated service state directory and an unused local port. Upload the same
raw BIN, create merged firmware and a session, then read serial and the actual
session `flash.tab5` identity. For the original image, GDB inspection can read
the three addresses above without an ELF. For the matched older reference,
wait for `TAB5_UI_DRAWN`, send two separate `kind=touch` requests at `(640,520)`
with `hold_seconds=0.2`, `settle_seconds=0.25`, and check count 1 then 2 plus the
frame. Collect ZIP before stop. All owned guests/services were stopped; shared
seed bytes and resident services were preserved.

Narrow host contracts cover complete high-Flash cache repair, changed input,
stale/missing/session-replaced ELF, OTA without symbols, reset identity, seed
ownership and mailbox publication order. The final integration suite and
authority-page update belong to the integrating change. Latest original
Python/UI/touch still requires a corrected upstream runtime and a new same-path
run; this evidence does not close #188.

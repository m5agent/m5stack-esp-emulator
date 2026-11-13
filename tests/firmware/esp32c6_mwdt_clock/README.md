# C6 PCR to MWDT clock regression

C6 selects each main watchdog's source and gate in PCR, independently of the
older TIMG `USE_XTAL` bit. Patch 0017 connects both PCR outputs to their C6 TIMG
clock inputs. It retains counted source cycles and fractional progress when
changing the mux/gate, reschedules the remaining comparator distance, and
handles `DIVCNT_RST` as a one-shot write trigger. Legacy C3/S3 paths retain
their existing clock selection.

Primary definitions: ESP-IDF v5.5.4
[MWDT LL source selection](https://github.com/espressif/esp-idf/blob/v5.5.4/components/hal/esp32c6/include/hal/mwdt_ll.h),
[PCR registers](https://github.com/espressif/esp-idf/blob/v5.5.4/components/soc/esp32c6/register/soc/pcr_reg.h),
[TIMG write-trigger register](https://github.com/espressif/esp-idf/blob/v5.5.4/components/soc/esp32c6/register/soc/timer_group_reg.h),
and [nominal RC source](https://github.com/espressif/esp-idf/blob/v5.5.4/components/soc/esp32c6/include/soc/clk_tree_defs.h).
The RC source is modeled at its nominal 17.5 MHz; this is not an electrical
oscillator/calibration measurement.

## Reproduce

Run the actual-C host replay (23 cases, original and changed model, ASan/UBSan):

```sh
python3 platform/tests/test_c6_mwdt_clock_patch.py
```

Build the native runtime through `scripts/bootstrap-c6-runtime.py` in a new
owned source directory. Its complete sequence now includes C6 patch 0017.
Keep the old and new runtime hashes distinct.

For the guest probe, use the fixed Launcher board definition, three archives
and isolated PlatformIO 6.1.19 environment described in
[`../nesso_touch_bus_shared/source-pins.json`](../nesso_touch_bus_shared/source-pins.json).
The probe contains no Launcher build hooks or M5GFX dependency.

```sh
python3 tests/firmware/esp32c6_mwdt_clock/prepare.py \
  --out "$OWN/probe" --launcher-source "$LAUNCHER_SOURCE" \
  --archives "$ARCHIVES" --core-dir "$PIO_CORE"
```

Set all three PlatformIO variables from `owned-build-env.json`, then run
`pio run -e arduino-nesso-n1 -j 2` in the generated directory. The accepted
portable preparation was checked byte-for-byte against the compiled input.
Use the same `firmware.factory.bin` on both runtimes in dedicated native
Nesso Device Service sessions:

```sh
python3 tests/firmware/esp32c6_mwdt_clock/run.py \
  --base-url "$OWN_SERVICE" --mode before --firmware "$PROBE_BIN" \
  --firmware-sha256 "$PROBE_SHA" --runtime-sha256 "$OLD_RUNTIME_SHA" \
  --out "$OWN/before"
```

Repeat with `--mode after` and the new runtime hash. The loopback service must
run on the same host because the runner verifies the native executable SHA.
The probe programs PCR/TIMG through guest MMIO, receives the real MWDT IRQ,
and measures it using the independent SYSTIMER-backed `esp_timer_get_time()`.
It explicitly feeds between cases to reset stage/count. Oracles cover 40 MHz,
80 MHz, RC_FAST, both mux directions and a 200 ms gate pause. The 20 ms bound
covers guest interrupt delivery; it does not alter watchdog configuration.

The runner saves the create request for same-key recovery, exports the ZIP
before `purge=0` stop, revalidates complete serial, compares application bytes,
and waits for native PID, Flash and lease release. Its output is private.

## Accepted results and original firmware boundary

`evidence-summary.json` binds the same probe BIN to the two runtimes. The old
model passes only the 80 MHz case; the corrected model passes all six. The
same-source host negative fails 18 of 23 cases; all 23 pass after the patch.

The original **Meshtastic RFID Demo 2.7.21 Landscape PN532/PN532Killer** BIN
remains **FAIL** after a separate 150-second run. Its welcome prompt is now
visible, but an IDLE watchdog restart still occurs. First-fault instruction
observations establish two separate faults:

1. The old model ignores PCR's 40 MHz choice and expires the configured
   5-second watchdog in about 2.5 seconds. The repaired model expires after
   5002 guest ticks from the first IDLE subscription.
2. The firmware's second `esp_task_wdt_init(90000 ms)` returns
   `ESP_ERR_INVALID_STATE`; the existing 5-second configuration remains.
   The firmware manually subscribes IDLE without a registered idle feed hook.
   At the first interrupt, `loopTask.has_reset=1` but `IDLE.has_reset=0`.

Both PN532 UART reads return after their intended one-second timeout. Missing
PN532 peer data alone does not explain that first watchdog fault. The displayed
“Welcome to Meshtastic” text is also present inside this original RFID BIN;
manifest/session/frame routing and unchanged application partitions were
verified. This is not the separate Meshtastic firmware's evidence.

No original BIN, watchdog timeout or assert was patched. RFID card reading,
physical hardware/RF and the complete native matrix on the new runtime are
**NOT RUN** here. Broad regression is a separate integration gate. Earlier
service setup errors and the first probe's missing inter-case feed remain
retained as invalid attempts rather than accepted controls.

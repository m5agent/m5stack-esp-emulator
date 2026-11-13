# Classic factory startup regressions

These are native Device Service virtual-device results for the unchanged public
Atom-Lite and Atom-Matrix factory BINs. They are not hardware measurements.
The bounded summary retains failing controls and incomplete Matrix acceptance.

Use a dedicated Device Service with a fresh canonical native runtime including
`qemu-unit-runtime/0021`; upload the original merged BIN, create a `qemu` session,
retain serial and `/device-state`, send `key:a` down/up through `/input`, and
compare GPIO input with actual RMT LED frames. Observe at least 120 seconds;
request `/evidence` before deleting with `purge=0&retain_flash=0`.

The classic accelerator policy supplies `M5SW_ICOUNT_MAX_PERCPU_NS=10000`.
`M5_CORE2_ICOUNT_MAX_PERCPU_NS=0` is the existing host-policy opt-out. A zero
setting is a diagnostic negative control, not the accepted factory profile.

The final integrated-main retest includes classic eFuse provisioning and a
fresh runtime. Two original Atom-Lite cold starts each ran for over 121 seconds
and produced button-driven RMT output. The complete serial streams were read
with API pagination, rather than checking only the first 262 KiB. Original
Atom-Matrix still triggers a WiFi watchdog, so issue #221 remains open.
Earlier-service failures and the unmerged offline-MAC experiment remain in the
summary; later passing runs do not erase them.


## WiFi follow-up: original Atom Matrix, 2026-11-13

The original SHA-256 `24892fcf5d5f8c97ee30a5ffb4fec166dca1c254cc6f54861af28abc8732ba2f`
was rerun through Device Service with native patch `0188`. The baseline had
omitted the MAC entirely in plain `qemu`; with an explicitly configured NIC it
could scan but exhausted its RX descriptor chain before authentication. The
missing NEXT/LAST cursor registers prevented the guest from recycling buffers.
After restoring those registers and classic CCMP RX, the unchanged image
completed scan, WPA2 authentication, DHCP, DNS and a real HTTP transaction.

The factory image fixes its AP credentials and requests
`http://example.com/index.html`. The observed HTTP status is **404**, also
confirmed independently against that public URL. The guest correctly prints
`[HTTP] HTTP code not ok`; no HTTP 200 is fabricated to produce a factory PASS.
The earlier offline-MAC `Wifi scan start` stop is not by itself a scan hang:
the original scan task records an error and deletes itself when no AP is found.

LED acceptance remains **PARTIAL** here: RMT produces 128-symbol transactions,
but the 25-LED endpoint requires 600 symbols and records incomplete frames.
The WiFi result does not close that separate controller/driver investigation or
claim physical RF behavior. Bounded results are in `wifi-rx-summary.json`.


Reproduce with an agent-owned service/runtime, the exact public BIN and the
factory test AP credentials held in `M5_TEST_WIFI_PASSWORD` (do not log or commit
them):

```sh
python3 tests/firmware/classic_factory/run_matrix_original.py \
  --service "$DEVICE_SERVICE_URL" --token-file "$DEVICE_SERVICE_TOKEN_FILE" \
  --firmware "$ATOM_MATRIX_ORIGINAL_BIN" --wifi-ssid "$FACTORY_AP_SSID" \
  --out-dir "$EVIDENCE_DIRECTORY" --seconds 130
```

Exit status validates scan, an actual HTTP response, watchdog/abort absence,
one cold boot, button edges and sampled nonblack LED output. Use `--offline`
without the WiFi arguments to exercise the ordinary radio-disabled `qemu`
profile; scan/HTTP are then outside that run's acceptance. `factory_http_pass`
remains separate: transport and LED success do not upgrade a 404 to factory PASS.

## RMT and LED follow-up: original Atom Matrix, 2026-11-13

The historical failures above are retained. Patch `0189` replaces the classic
RMT's fixed 1 ms callback with deadlines derived from each symbol and the selected
clock/divider. The original BIN has 64 symbols per refill, 48 ticks per symbol
at 40 MHz, so each refill interval is 76.8 microseconds. Its compiled FastLED
CCOUNT guard allows 1.5 times that interval. Delaying every refill to 1 ms made
the unchanged driver terminate at 128 symbols, before the required 600.

After timing was repaired, the endpoint accepted full frames but still displayed
black. The original BIN encodes zero as `0x0024800c` (12 high / 36 low ticks) and
one as `0x00188018` (24 high / 24 low). The endpoint used a strictly-longer-high
comparison and decoded both as zero. Patch `0191` admits the equal-duration one
boundary. It rejects missing phases, equal levels and invalid clock values
before updating any pixel, preserving the last complete frame on bad input.

The primary driver reference is [FastLED 3.5.0's ESP32 RMT constructor](https://github.com/FastLED/FastLED/blob/3.5.0/src/platforms/esp/32/clockless_rmt_esp32.cpp),
which forms one from `T1+T2 / T3` and zero from `T1 / T2+T3`.
[Its chipset profiles](https://github.com/FastLED/FastLED/blob/3.5.0/src/chipsets.h)
include the 300/300/600 ns SK6812 timing. The exact words and guard constants
were also verified in the unchanged BIN; these source references do not assert
an exact firmware library version or physical LED part revision.

`test_rmt_led_equal_duty_patch.py` replays the actual endpoint patch against the
pinned historical fragment. It retains the old all-black negative control and
checks independent RGB values for 25 classic LEDs and 3 S3 LEDs with both phase
orders, short frames, wrong routes and invalid symbols. This is host C evidence;
same-BIN Device Service evidence is recorded separately in `rmt-led-summary.json`.
The relative-duration decoder does not establish absolute electrical pulse
tolerance, reset timing, physical LED brightness or RF behavior.

## Combined native runtime regression

`final-runtime-summary.json` records two further 130-second runs of the same
original Atom Matrix BIN on the combined native runtime through reviewed 0192
and 0193, SHA-256
`33c0ec98b7576c22526deddf81519d8f0719efbfc5fb2221267e4d6bb83ffc58`.
Both runs have one cold boot, no watchdog/Guru/abort markers, nonblack LED
animation in all 65 samples, complete RMT-decoded frames, and modeled GPIO
button edges from down/up input. Packet captures contain DHCP, DNS, TCP and
the original HTTP 404 response. The factory HTTP assertion remains PARTIAL.
Incomplete LED frames remain counted; they are not concealed by changing the
guest's refill guard. Both ZIPs were captured before `purge=0` stop and mutable
Flash was released. These original-firmware sessions do not replace the
separate shared-runtime matrix or imply physical-hardware validation.

## Final Atom Lite and Matrix v1.1 profiles

`additional-models-final-summary.json` adds the remaining device-specific
controls on the same `33c0ec98...` runtime with Device Service source
`e8d527e48e2b471e03666fa913029df27c132886`. The earlier Atom Lite results above
used a different runtime and remain separate historical evidence.

The unchanged Atom Lite factory BIN runs for 130 seconds in plain `qemu`.
At three seconds, actual down/up input produces GPIO button edges and red LED
output; the output remains observable through the final sample. The complete
14,004,219-byte serial capture has one ROM boot and no watchdog/Guru/abort
markers. Matrix v1.1 is the independent `atom-matrix-v11` / `m5atommatrixv11`
profile. The same original Matrix BIN completes its own 130-second `qemu-wifi`
run with real DHCP/DNS/TCP/HTTP 404, nonblack animation and button edges. Its
BMI270 differs from the original Matrix's MPU6886, so these results do not
grant IMU compatibility or board-axis correctness.

The bounded summary includes exact input timing, firmware and padded-Flash
hashes, sampled state, controller counters, full-serial and ZIP hashes, and
reproduction steps. Both sessions collected ZIPs before `purge=0` stop and
released mutable Flash. Factory HTTP, physical properties, browser execution
and the separate complete high-load matrix retain their stated limits.

## IRQ lifetime and CPU clock recovery, 2026-11-13

[`irq-clock-recovery-summary.json`](irq-clock-recovery-summary.json) retains the
recovered-runtime failures, diagnostic controls and subsequent candidate results.
It does not replace the historical `33c0ec98...` records above. The recovered
`e529a11c...` runtime reproduced an original Atom Lite startup interrupt watchdog;
removing cache optimization for a short wall-time observation did not establish
application readiness, and a longer transaction-only control still failed.

A bounded observer caught the original Lite's `RFI 5` restoring PS to level zero
while the emulator's high-priority cooperative mask stayed set. The old helper
ran before restoring PS and only retired level four. Native patch `0194` tracks
accepted high-priority IRQs by their architectural EPS/EPC slot. A matching RFI
retires that slot; software PS changes, RFE/RFDE and another CPU do not retire it.
Repeated entry at the same level reuses the same hardware slot rather than
inventing a software nesting stack. Reset clears the local state. An intermediate
PS-based candidate and the subsequent slot implementation both passed the same
original Lite's 130-second initialization, real button input and LED observation.
The intermediate candidate is retained separately because software PS does not
identify actual IRQ nesting.

The next full-build candidate, `dfb73748...`, passed Lite and Core2 UIFlow1 but
failed the original Matrix before initialization. Both CPUs' panic PCs identify
the return immediately after `WAITI 0` in the idle hook. Restoring only the old
MEMW predicate in a separate `14f5c435...` control did not fix Matrix; this result
does not support blaming that predicate for the idle watchdog.

A per-CPU ring observer then captured the actual Matrix clock sequence. At one
virtual timestamp, switching CPU1 from 160 to 40 MHz changed its visible CCOUNT
from 173724830 to 43431207. Its already-programmed compare deadline did not move.
That deadline fired before the new count reached compare, and the original tick
handler scheduled its next compare several virtual seconds away. A subsequent
40-to-240 MHz switch jumped the counter forward again while retaining that late
deadline. The original interrupt watchdog fired first. These are virtual-model
observations, not physical clock measurements.

Patch `0197` carries forward elapsed cycles at the old rate before installing the
new rate, and retimes an armed future compare from its remaining unsigned ticks.
It preserves due matches, latched interrupts, unarmed timers, compare register
values and the original reset behavior. It does not clamp expired compares,
change watchdog timeouts, or alter guest instructions. The classic board samples
one virtual timestamp for both CPUs. This fix applies to serialized TCG;
MTTCG retains its existing clock-update path and its clock-continuity limitation.
The browser-WASM patch selection is unchanged.

The independent `a2c5e415...` candidate restores the original Matrix's full
130-second run: one boot, no Guru/watchdog markers, 9367 valid LED frames, real
button edges and DHCP/DNS/TCP with the original HTTP 404 response. The same
candidate also passes the original Lite for 130 seconds and Core2 UIFlow1's
Wi-Fi Config page for 180 seconds. Each session verifies the actual runtime PID,
`thread=single`, original application bytes before/after, evidence ZIP before
stop and `purge=0` cleanup. The candidate uses incremental objects and predates
the formal MTTCG guard; it is **not** a fresh-build release or a full shared
matrix result. Factory HTTP remains **PARTIAL**. Final runtime regression,
resident deployment, browser execution and physical hardware are separate gates.

Run the independent actual-C controls with:

```sh
PYTHONPATH=platform/tools:platform/tests python3 -m unittest \
  test_xtensa_restored_irq_level_patch test_xtensa_cpu_clock_rebase_patch
```

The tests execute the patch's actual accepted-IRQ, return, reset, clock-board and
compare callback functions with ASan/UBSan. They preserve old-implementation
negative controls, counter and deadline wrap, due/latched/unarmed timer cases,
initial unclocked state, unchanged reset behavior, CPU isolation, and the
MTTCG boundary. Host controls do not replace the original Device Service runs.

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

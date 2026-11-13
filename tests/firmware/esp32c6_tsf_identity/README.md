# NanoC6 TSF and eFuse controller controls

These controls separate two native model faults from the remaining application
and radio limitations. They use unchanged user BINs and dedicated Device
Service sessions. The dated [summary](evidence-summary.json) retains old failures
and candidate identities; it is not a combined-runtime deployment acceptance.

Patch 0018 implements four local 64-bit, microsecond TSF counters in the WiFi
controller. The original Honeypot's instructions at `0x420ba7e0` capture TSF
through `0x600ad014`, then read its high/low pair. The preceding model returned
zero forever. Gate/load/capture offsets were checked against the actual stock
HAL implementation; the probe calls that prebuilt HAL directly for its timing
case and uses guest MMIO for gate, 64-bit load and rollover controls. Time is
derived from QEMU's virtual clock. Fractional progress survives gate changes;
the latched pair remains coherent until the guest releases the capture request.

Patch 0019 fixes the board's eFuse mapping priority. The broad LP region had
shadowed the real controller at `0x600b0800`; attaching a backing drive alone
still gave zero from actual `esp_read_mac` calls. NanoC6 now attaches its C6
eFuse drive, and the service initializes only MAC and MAC_EXT bytes through
that backing. The fixed original IDF
[field table](https://github.com/espressif/esp-idf/blob/38628f98b9/components/efuse/esp32c6/esp_efuse_table.c)
and [guest MAC implementation](https://github.com/espressif/esp-idf/blob/38628f98b9/components/esp_hw_support/mac_addr.c)
define the layout. C6 does not run the S3 ADC calibration writer. All other
fields remain unburned, including disabled security fuses; this is a session
identity fixture, not factory calibration or silicon-revision emulation.

## Reproduce

Run the actual-C negative/positive controls and service identity tests:

```sh
PYTHONPATH=platform/tools:platform/tests python3 -m unittest \
  test_c6_wifi_tsf_patch \
  test_device_service.DeviceServiceUnitTests.test_c6_efuse_identity_and_extended_address_bytes \
  test_device_service.DeviceServiceUnitTests.test_efuse_identity_only_provisions_attached_supported_drivers
```

Build a new native C6 runtime with `scripts/bootstrap-c6-runtime.py`, which
orders patches 0018 and 0019 after 0017. Preserve the complete configure/build
logs and exact binary/ROM hashes. Do not reuse an earlier runtime's acceptance.

Prepare each guest kind in a separate owned directory using the fixed archives,
PlatformIO 6.1.19 environment and Launcher board source defined in
[`../nesso_touch_bus_shared/source-pins.json`](../nesso_touch_bus_shared/source-pins.json):

```sh
python3 tests/firmware/esp32c6_tsf_identity/prepare.py \
  --kind tsf --out "$OWN/tsf" --launcher-source "$LAUNCHER_SOURCE" \
  --archives "$ARCHIVES" --core-dir "$PIO_CORE"
```

Repeat with `--kind identity`. The board is explicitly 4 MiB DIO/40 MHz and
uses the supplied 3 MiB application partition. Set all three variables from
`owned-build-env.json`, then build with `pio run -e arduino-nesso-n1 -j 2`.
There are no Launcher build hooks, remote minification, or M5GFX dependencies.

Run the same resulting BIN on each runtime through an owned local service:

```sh
python3 tests/firmware/esp32c6_tsf_identity/run.py \
  --base-url "$OWN_SERVICE" --token-file "$TOKEN_FILE" \
  --kind tsf --mode after --firmware "$PROBE_BIN" \
  --firmware-sha256 "$PROBE_SHA" --runtime-sha256 "$RUNTIME_SHA" \
  --out "$OWN/after"
```

Use `--mode before` for the old negative. For corrected identity use
`--kind identity --mode after --reset`, then repeat in a separate session.
Both reset observations must match within each session; the two sessions'
identity hashes must differ. Raw identity values and session receipts are
private. The final ZIP serial, unchanged application bytes, native executable,
manifest binding, Flash/lease release and process exit are checked.

## Results and limits

The actual-C suite passes all twelve after controls; the old implementation
fails nine and preserves three unchanged behaviors. The same TSF guest BIN
changes from 0/6 to 6/6. Its HAL elapsed time is 19510 microseconds versus
19537 from the independent `esp_timer` clock. Two separate identity sessions
produce distinct addresses, each stable across one controlled reset.

The original Zigbee light changes from repeated zero-EUI assertion resets to
one boot with no fatal marker over 30 seconds. It still reports ZDO Config
Ready `ESP_FAIL`. The separate real guest `esp_ieee802154_set_extended_address`
and get control still returns zero: `0x600a3010/14` belong to an unimplemented
802.15.4 region. No joining, light-control, RF or complete Zigbee PASS follows.

In the earlier TSF/eFuse-only candidate, the original Honeypot survives 90 seconds without restart. Read-only original
instruction observations prove that `softAP` now returns true, rather than
remaining in the zero-TSF loop. Its Arduino HWCDC output is still not visible:
that candidate's C6 USB Serial-JTAG model lacks the asynchronous endpoint IRQ
path used by the original driver. No application-ready or network data-plane
PASS is claimed from the absence of an error. NanoC6 `qemu-wifi` remains an
unsupported admission mode; these plain `qemu` results are not network tests.

Physical hardware, RF, browser-WASM, final combined-runtime regression and
resident deployment are **NOT RUN** in this fixture's candidate summary.

The later [combined-runtime record](../esp32c6_usb_serial_jtag/pre-shared-irq-runtime-summary.json)
keeps these failures and records TSF 6/6, two distinct session identities each
stable across reset, and the corrected USB console path on its exact runtime
and production service source. The 802.15.4 extended-address control still
reports `EXPECTED_FAIL`; it does not inherit a radio result from the identity
or TSF checks. Its separate shared-interrupt-pad limitation remains open.

# NanoC6 USB Serial-JTAG fixed CDC endpoints

Patch 0020 adds the actual controller path used by Arduino HWCDC and the
official NanoC6 UIFlow2 USB REPL. It adapts the existing S3/C3 endpoint model
without changing that SoC's implementation. C6 now has 64-byte IN/OUT FIFOs,
automatic full-packet commit, explicit WR_DONE, masked/W1C interrupts, real
chardev backpressure, pad gating and interrupt-matrix source 48. An explicitly
attached virtual serial host supplies 1 ms guest-clock frames and FIFO data.

The scope is the fixed CDC data endpoints. USB enumeration, EP0 control/line
coding, USB OTG, JTAG/debug and physical signaling are **NOT RUN / unmodeled**.
The model does not acknowledge invented device traffic or overwrite firmware.
Primary contracts are the fixed
[C6 LL driver](https://github.com/espressif/esp-idf/blob/v5.1.4/components/hal/esp32c6/include/hal/usb_serial_jtag_ll.h),
[register definitions](https://github.com/espressif/esp-idf/blob/v5.1.4/components/soc/esp32c6/include/soc/usb_serial_jtag_reg.h),
and [Arduino HWCDC](https://github.com/espressif/arduino-esp32/blob/3.0.0/cores/esp32/HWCDC.cpp).
The original Honeypot's actual write function was independently located at
`0x42015fcc`; the source reference does not claim its exact compiled dependency.

## Reproduce

Run the actual-C before/after replay with ASan/UBSan:

```sh
PYTHONPATH=platform/tests python3 -m unittest test_c6_usb_serial_jtag_patch
```

Its fifteen cases include short/full TX, partial writes, backpressure/errors,
RX packet retention/order, RAW/mask/W1C, disconnected host, pad gating, frame
wrap, reset and teardown. The old model must fail fourteen cases; its existing
single-byte output is retained as the one unchanged control.

Build the native runtime in a new owned source directory with
`scripts/bootstrap-c6-runtime.py`; retain all twenty-two ordered patch hashes,
source postimages, configure/Ninja logs and binary/ROM hashes. The original
source-only manifest is not a substitute for a fresh-object build receipt.

Prepare a correct 4 MiB probe using the pinned recipe and archives described in
[`../esp32c6_tsf_identity/README.md`](../esp32c6_tsf_identity/README.md), then
replace only its sketch with this directory's `main.cpp` before building:

```sh
python3 tests/firmware/esp32c6_tsf_identity/prepare.py \
  --kind identity --out "$OWN/probe" --launcher-source "$LAUNCHER_SOURCE" \
  --archives "$ARCHIVES" --core-dir "$PIO_CORE"
cp tests/firmware/esp32c6_usb_serial_jtag/main.cpp "$OWN/probe/src/main.cpp"
```

Set the three PlatformIO environment variables from `owned-build-env.json`
and run `pio run -e arduino-nesso-n1 -j 2` there. No Launcher hooks or remote
minification are used. Use the identical factory BIN for both model versions.

Start a dedicated Device Service on an agent-owned port with fresh state.
Point `M5_C6_USJ_REAL_QEMU` at the pinned executable and `M5_QEMU_RISCV32` at
this directory's executable `qemu_host.py`. The wrapper replaces only the
third C6 serial endpoint with an explicit socket host, leaves both UARTs
intact, and starts paused until the test host is attached. QEMU writes its
USB output directly to the existing `usb-serial-jtag.log` evidence file.
The actual PID executable, not the wrapper, is checked against the supplied SHA.

```sh
python3 tests/firmware/esp32c6_usb_serial_jtag/run.py \
  --base-url "$OWN_SERVICE" --token-file "$TOKEN_FILE" \
  --kind arduino --mode after --firmware "$PROBE_BIN" \
  --firmware-sha256 "$PROBE_SHA" --runtime-sha256 "$RUNTIME_SHA" \
  --out "$OWN/after"
```

Use `--mode before` for the negative. Use `--kind uiflow --mode after` with
the pinned original NanoC6 UIFlow2 BIN for its separate REPL case. The host
sends Ctrl-C and a bounded arithmetic print command through the same RX FIFO;
the evaluated response must return through USB. It does not rewrite the app.

The runner exports each session's ZIP before `purge=0` stop, checks the complete
UART and USB logs separately, binds the manifest/firmware/native process,
compares application bytes and waits for Flash, lease and process release.
The host-received bytes must be a prefix of QEMU's own final USB log. Results
and identifiers are private; publish only bounded, redacted summaries.

## Candidate evidence and remaining application boundaries

[`evidence-summary.json`](evidence-summary.json) preserves the first candidate
and negative controls. The identical Arduino BIN changes from incomplete TX
and zero RX to an exact 257-byte TX frame, a 197-byte RX comparison in the
guest and its USB acknowledgment. The official UIFlow2 BIN evaluates
`USJ_REPL_RX_OK 2016` through its original USB REPL path. These results register
the NanoC6 device-local `usb-serial-jtag-c6` endpoint case; other boards do not
inherit it.

The original Honeypot now emits its configuration-mode message through USB
and stays alive over 90 seconds. Its UART and USB each contain one ROM banner;
those separate channels are never added together to infer a reset. This does
not validate AP association, HTTP, honeypot network behavior or RF. Earlier
TSF/eFuse and Zigbee/802.15.4 limits remain in the adjacent fixture. A later
fresh-runtime summary, broad integration matrix and resident deployment are
separate acceptance gates; candidate results do not replace them.

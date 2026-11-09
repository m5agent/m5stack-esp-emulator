# CoreMatrix C158 backend feasibility

This folder records two distinct virtual-device validation lanes against the
[isolated C61 candidate](../../../patches/qemu-esp32c61-corematrix/README.md).
The production service and browser catalogs do not admit C158 firmware.

## Reference-only Device Service probe

Build the small C61 program with clean ESP-IDF v5.5.4 at
[`735507283d5b2f9fb363a1901172dbd9e847945d`](https://github.com/espressif/esp-idf/commit/735507283d5b2f9fb363a1901172dbd9e847945d)
and its pinned submodules. It uses 16 MiB Flash and internal RAM. The ESP-IDF
driver exercises real virtual C61 HP I²C transactions.

```sh
source "$IDF_PATH/export.sh"
PROBE_SRC="$SIM_ROOT/tests/firmware/corematrix_backend_feasibility/probe"
mkdir -p "$PROBE_BUILD"
(
    cd "$PROBE_SRC"
    IDF_TARGET=esp32c61 idf.py --preview -B "$PROBE_BUILD" \
        -D "SDKCONFIG=$PROBE_BUILD/sdkconfig" build
)
python3 "$SIM_ROOT/tests/firmware/corematrix_backend_feasibility/run_service.py" \
    --qemu "$QEMU_ROOT/build/qemu-system-riscv32" \
    --rom-dir "$QEMU_ROOT/pc-bios" --build-dir "$PROBE_BUILD" \
    --out-dir "$PROBE_OUTPUT"
```

Use Python 3.12+ with Pillow. Set `SIM_ROOT`, `IDF_PATH`, `QEMU_ROOT`,
`PROBE_BUILD` and `PROBE_OUTPUT` to absolute paths. Choose a short, fresh
output path for the Unix QMP socket. The runner creates a loopback Device
Service with an OS-assigned port, unique state and one reference-only spec.
The running guest uses the normal session, input, serial, QOM, frame and
evidence APIs. A session requesting an uploaded image receives HTTP 409.

The guest checks the unpowered TM1680 address, reads the PM1 and IOE1 identities,
then enables the matrix rail over I²C. Each key is applied through
`/input`. The guest reads PM1 GPIO and IRQ registers, writes the TM1680 over
the same bus, and emits its marker. The runner checks all 256 pixels in nine
fresh frames, including overlapping A+C and separate releases. It requests
the evidence ZIP before stop, retains stopped history, and checks lease and
mutable Flash release. The ZIP, firmware and frames stay in the private output.

## Unmodified UIFlow2 stock diagnostic

The official M5Burner UIFlow2 CoreMatrix v2.5.4 artifact has firmware ID
`2104482080746106881`, version ID `2116030913772818433`, image chip ID
`0x0014`, and SHA-256
`0bfbe5a4acb467d93a7ded2186a4f73adea37511869328b563c15ab73163a018`.
Its 16,773,120 bytes are unchanged and padded with 4 KiB of erased bytes
to match the QEMU 16 MiB MTD device.

```sh
python3 "$SIM_ROOT/platform/tools/fetch_firmware.py" \
    --firmware-id 2104482080746106881 --device-slug core-matrix \
    --analyze --chip-id 20 --cache "$FIRMWARE_CACHE"
python3 "$SIM_ROOT/tests/firmware/corematrix_backend_feasibility/run_stock.py" \
    --qemu "$QEMU_ROOT/build/qemu-system-riscv32" \
    --rom "$QEMU_ROOT/pc-bios/esp32c61-rom.bin" \
    --firmware "$FIRMWARE_CACHE/community/2104482080746106881.bin" \
    --out-dir "$STOCK_OUTPUT" --corematrix
```

The unmodified firmware prints the C61 ROM marker, the UIFlow2 v2.5.4 banner
and `Startup with network type: WIFI`. The candidate's captured 16×16 frame
remains black after the bounded run. The instrumented run records repeated
reads of unimplemented MMIO `0x600ad800` after that marker. The upstream
control also logged unimplemented HP I²C interrupt polling at `0x60004020`.
The candidate removes the digital I²C gap for the IDF probe. Stock readiness
and runtime admission remain open.

The [summary](evidence-summary.json) binds the firmware, ROM, QEMU,
frames and session cleanup. These observations establish a C61 visual and input
slice for the IDF probe. Physical assembly, radio, power and stock application
functionality require separate validation.

# CoreMatrix C158 backend feasibility

This folder records virtual-device validation against the
[isolated C61 build](../../../patches/qemu-esp32c61-corematrix/README.md).
The native probe and pinned stock runner use separate Device Service instances
and firmware identities.

## Reference-only Device Service probe

Build the small C61 program with clean ESP-IDF v5.5.4 at
[`735507283d5b2f9fb363a1901172dbd9e847945d`](https://github.com/espressif/esp-idf/commit/735507283d5b2f9fb363a1901172dbd9e847945d)
and its pinned submodules. It uses 16 MiB Flash and internal RAM. The ESP-IDF
driver exercises real virtual C61 HP I²C transactions.
Pass a trusted local build of this fixture. The evidence records the composed
Flash hash from the tested build.

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

### Open the probe in the 3D workbench

Repeat the `run_service.py` command with a fresh `--out-dir` and append
`--workbench`. Open the printed loopback URL. Expand **仿真服务连接**, paste
the contents of the private `workbench-token` file into **访问 Token** and
choose **连接服务**. Expand **服务中的设备会话** and select **在工作台打开**
for the CoreMatrix diagnostic session. Focus the 3D model and hold or release
**A**, **B** or **C** to observe the corresponding white pixels and guest
serial markers. Press Ctrl+C in the runner to stop the guest and remove the
local credential. Closing the browser view detaches from the service session.

The workbench uses a temporary device row and its pre-created reference
session. The listener serves the existing workbench assets and accepts only
the diagnostic session APIs. Firmware import, artifact upload, HTTP session
creation and non-loopback origins are blocked. The production catalogs and
firmware admission rules remain separate.

To repeat the Chrome verification, install the platform test dependencies
and run the script against the printed origin while the service is running.

```sh
npm ci --prefix "$SIM_ROOT/platform/tests"
node "$SIM_ROOT/tests/firmware/corematrix_backend_feasibility/run_workbench.mjs" \
    "http://127.0.0.1:$PORT" "$PROBE_OUTPUT"
```

The script verifies fresh pixels from the real CoreMatrix display texture,
the matching guest serial and PM1 state, the API guard and session cleanup.
The [workbench summary](workbench-summary.json) records the native Device
Service path with a Chrome 3D frontend.

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

The [pre-fix record](evidence-summary.json) retains the 15-second all-black
frame and repeated reads from `0x600ad800`. The updated build exposes a
virtual-time counter and finishes the relevant idle-radio startup commands.
The M5GFX software I²C probe identifies the board before handing the same
bus to HP I²C for TM1680 traffic.

Replay the exact same stock image through Device Service to verify the
36-pixel missing-SSID cross before any user code, the 12-pixel rectangle
drawn over USB REPL and independent plus overlapping A/B/C presses and
releases.

```sh
python3 "$SIM_ROOT/tests/firmware/corematrix_backend_feasibility/run_stock_service.py" \
    --qemu "$QEMU_ROOT/build/qemu-system-riscv32" \
    --rom-dir "$QEMU_ROOT/pc-bios" \
    --firmware "$FIRMWARE_CACHE/community/2104482080746106881.bin" \
    --out-dir "$STOCK_OUTPUT"
```

The runner allows only the pinned reference on its isolated loopback
listener. It sends volatile Python through the normal program endpoint and
does not replace the stock filesystem. It exports live evidence and checks
that the stopped session retains history while the lease and Flash are
released. The [new summary](stock-startup-summary.json) binds both runs to
their runtime, ROM and firmware hashes. No physical hardware, Wi-Fi
association or external PSRAM was validated.

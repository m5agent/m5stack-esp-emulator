# Nesso independent touch bus regression

Nesso's FT6336 touch controller uses I2C SDA10/SCL8; the LCD uses SPI
MOSI21/SCLK20/CS17. `Panel_Device::getTouchRaw()` temporarily ends an active
display transaction when the touch configuration declares a shared bus.
With concurrent drawing and input tasks this releases the drawing task's
Arduino SPI mutex from the input task. The original Launcher 3.0.0 BIN reaches
FreeRTOS's `xTaskPriorityDisinherit` owner assertion through this path.

The patches change only Nesso **touch** `bus_shared` to false. The LCD's
`bus_shared=true` is retained because the LCD and radio share SPI. This does
not make arbitrary concurrent display operations thread-safe.

Primary wiring references: [Arduino pinout](https://docs.arduino.cc/resources/pinouts/TPX00227-full-pinout.pdf),
[M5Stack Nesso documentation](https://docs.m5stack.com/en/core/Arduino_Nesso_N1).
The master patch targets [M5GFX 28d47949](https://github.com/m5stack/M5GFX/tree/28d47949bdc84f30881623476f555398e2194313).

## Evidence and boundary

`evidence-summary.json` records virtual-device validation on the same native
C6 runtime and Nesso profile:

- Minimal dual-task probe: the drawing task holds the real display transaction;
  a higher-priority input task calls the library's real touch API. Both pinned
  M5GFX 0.2.19 and fixed master fail before the patch and run over 155 seconds
  with three controller-delivered touch coordinates after it.
- Full Launcher tag `4b06de691df15b0fe6a9f09f56d1d107bbf32b12`, M5Unified
  0.2.24 and M5GFX 0.2.31: before asserts; after runs over 155 seconds with
  actual menu navigation, touch selection, return and settings frames.
- The original release BIN remains a separately retained FAIL. The rebuilt
  controls are not bit-identical reconstructions. CI proves M5Unified 0.2.24;
  its cached M5GFX version could not be uniquely recovered.
- Physical hardware, RF, successful online installation and a full Launcher
  rebuild against current master are **NOT RUN**. The master control exercises
  the same library/Arduino SPI implementation through the minimal probe.

Earlier setup mistakes remain in private history: missing Arduino SPI header
visibility prevented real SPI locking; PlatformIO also installed an unused
latest M5GFX alongside the explicitly pinned version. These runs/builds are
not accepted negative or positive controls. The probe now asserts a real
`SPI.bus()` handle and explicitly exposes SPI/Wire headers to library builds.

## Prepare and build

Use Python 3.12+, PlatformIO 6.1.19 and the archive hashes in
`source-pins.json`. Obtain the platform from the pioarduino 55.03.39 release,
Arduino core 3.3.9, and the custom SDK archive named
`launcher_keyboot_esp32-arduino-libs-20260910-173758.tar.gz` from
[the Launcher SDK release](https://github.com/bmorcelli/myLibBuilder/releases/tag/builds).
The local archive filenames expected by `prepare.py` are in the pins file.
Keep packages/core/platforms in an owned directory; do not link a shared cache.

Checkout the pinned Launcher source and its six gitlink revisions. Checkout
M5GFX at the desired pin in a separate source tree. For the minimal control:

```sh
python3 tests/firmware/nesso_touch_bus_shared/prepare.py probe \
  --out "$OWN/probe" --launcher-source "$LAUNCHER_SOURCE" \
  --gfx-source "$GFX_SOURCE" --archives "$ARCHIVES" --core-dir "$PIO_CORE"
```

Set `PLATFORMIO_CORE_DIR`, `PLATFORMIO_PACKAGES_DIR` and
`PLATFORMIO_PLATFORMS_DIR` to the paths in the generated
`owned-build-env.json`. From the generated directory, run only:

```sh
pio run -e arduino-nesso-n1 -j 2
```

Preserve `firmware.factory.bin`, ELF, map and the full build log before changing
the library. Apply `m5gfx-master.patch` at the master pin, or
`m5gfx-0.2.31.patch` at 0.2.31; verify forward/reverse apply. Rebuild and verify
the artifact hash changed and the active compiler dependency file points to
the patched source. Keep the probe source, SDK and build recipe identical.

For the full Launcher control, use `prepare.py launcher` with the same arguments
except `--gfx-source`. It copies the fixed source into an owned directory,
pins the two libraries, embeds deterministic local gzip data, and disables
the outbound web minifier, source formatter, submodule mutation and upload
hooks. Both controls use this same recipe and local dummy configuration key.
Preserve the generated web header hash. The release-style merged artifact is
`Launcher-arduino-nesso-n1.bin`.

PlatformIO may install a transitive latest library as `M5GFX` and the pinned
library as `M5GFX@0.2.31`. Inspect the actual `M5GFX.cpp.d` compiler dependency
file and its `library.json`; patch only the **compiled 0.2.31** directory.
Never infer the compiled version from the shortest directory name.

## Dedicated Device Service execution

Start an agent-owned native Device Service with the frozen C6 binary and ROM,
separate state, a free local port, and at most one Nesso session. This runner
expects an unauthenticated loopback test service on the same host because it
verifies the actual native PID executable hash. Keep its output private.

```sh
python3 tests/firmware/nesso_touch_bus_shared/run_probe.py \
  --base-url "$OWN_SERVICE" --mode before --firmware "$BEFORE_BIN" \
  --firmware-sha256 "$BEFORE_SHA" --runtime-sha256 "$RUNTIME_SHA" \
  --out "$OWN/before-evidence"
```

Repeat with `--mode after` and the patched artifact/hash. Before requires the
real readiness marker and ownership assertion; after requires 155 seconds,
three actual touch coordinates and successful owner releases. The runner
persists an idempotent create request, obtains the same-session ZIP before
stop, checks application bytes, stops with `purge=0`, and waits for terminal
state, native PID exit, lease and mutable Flash release. Inspect saved frames
for live counter/touch output. Record source and patch hashes alongside its
runtime/firmware receipt. It is a probe runner, not a full Launcher UI oracle.

For full Launcher use a dedicated session, observe at least 150 seconds, send
`key:a` to move selection, use real touch down/up, and hold `key:b` for one
second to return. The accepted run mapped raw touch `(67,120)` to `(120,67)`
and raw `(100,120)` to `(120,100)`, entering OTA and CFG respectively. A
successful input response alone is insufficient: retain serial touch output
and before/after menu frames, then ZIP-before-stop and cleanup as above.

# Hardware API probes

`build_hardware_inventory.py --uiflow /path/to/official/uiflow` reconciles the
public official documentation and source exports. `probe_hardware.py` records
exports and bounded calls; those results do not establish controller data-plane
coverage. `summarize_hardware_results.py` joins retained method observations to
the inventory without converting presence or successful return into PASS.

All execution below uses visible Device Service sessions. The runner requests
the evidence ZIP before stopping with `purge=0`, preserves history, and verifies
that the runtime process is gone. Use a fresh ignored output directory per run.
The examples assume Python 3.12 and the project's local `littlefs-python`
dependency directory. Supply the existing Device Service token file privately.

For concurrent sweeps, `run_guest.py` and `run_hardware_guest.py` accept
`--ready-timeout`. The default 60 seconds matches ordinary single-session
runs; a six-session UIFlow2 local-service sweep should use at least 180
seconds so QEMU launch pressure is not misreported as a guest failure.

Fixture intake excludes host `__pycache__`, `.pyc`, `.pyo` and `.DS_Store`
files. Explicit guest `.mpy` and other binary fixtures remain supported.
Symlinks are rejected even when their names would otherwise be excluded.
The runner copies and hashes each original byte sequence once, then composes
LittleFS from that owned staging copy. This keeps fixture and firmware hashes
stable when a host Python process creates a cache beside a guest fixture.

## SPI SD and filesystem

Create a disposable blank 8 MiB image under `.work/`. Run the full transfer and
format fixture on each selected board:

```sh
PYTHONPATH=.work/py python3.12 tests/uiflow2/api_sweep/run_hardware_guest.py \
  --device cores3 --source tests/uiflow2/api_sweep/probe_sdcard.py \
  --api http://127.0.0.1:8788 \
  --fixture-dir tests/uiflow2/api_sweep/fixtures/sd_multiblock \
  --sd-image .work/sd-blank.img --done-marker HARDWARE_SD_DONE \
  --out-dir .work/api-sweep/cores3-sd-new --timeout 240 \
  --token-file /path/to/existing-token
```

Repeat with `--device cardputer-adv` and a different output directory. The
fixture performs a 1536-byte native block write/read, guest FAT formatting,
official `hardware.SDCard` mounting, a distinct 8222-byte file write and sync,
then unmounts/remounts and compares the full file again. Omitting the fixture
selects a preformatted image and a short file; that is a narrower subcase.
The final runtime smoke also uses an explicit 8195-byte pattern (8225-byte
file); its exact fixture contents and hashes are retained in the delivery
summary. It is a separate argument domain from this standard 8192-byte recipe.

The independent host FAT oracle requires `pyfatfs==1.1.0` in `.work/py`. After
the session is stopped, read its owned disk and immutable source artifact from
the same local service state directory:

```sh
PYTHONPATH=.work/py python3.12 tests/uiflow2/api_sweep/analyze_sdcard.py \
  .work/api-sweep/cores3-sd-new --file-pattern-bytes 8192 \
  --service-state /path/to/local-device-service-state
```

The oracle independently parses the FAT file, compares every expected byte,
checks the changed owned disk hash and unchanged source artifact hash, and
retains an ignored final disk copy. This observes the actual SPI backing file;
it does not insert guest filesystem values from Python.

## Microphone, camera and input

`analyze_microphone_pcm.py` compares retained native microphone samples and
WAV data with the session-owned input tone, including independent sample count,
format and frequency checks. M5Unified gain/DC removal may change bytes; the
oracle does not require the output hash to equal the source tone hash. This
does not automatically validate another recording wrapper or sample rate.

`analyze_camera_frames.py` checks complete QVGA RGB565 snapshots against two
independently generated host scenes, including borrowed-frame intervals. Other
resolutions, display color ordering and physical optics require separate tests.
The current oracle uses GC0308's high-byte-first 8-bit DVP wire order.
`--wire-order legacy-lsb-first` is only for reproducing old model-content hashes;
that historical result does not establish correct sensor byte order or colors.
`analyze_camera_interfaces.py` independently decodes native JPG/BMP with Pillow
and compares the complete scene. A byte-swapped diagnostic is retained as a
diagnosis and cannot grant an image-color PASS.

`probe_inputs.py` uses real same-session Device Service input actions and
FT6336/PMIC driver paths. `analyze_touch_coordinates.py` can compare the original
exact-coordinate subcase with a rerun on unchanged guest source and firmware.
Its touch result does not grant a PASS to the legacy PMIC short-click oracle:
the existing `key:p` input maps to a hold event. Movement, multiple points and
physical touch behavior are separate validation questions.

`probe_gc0308_sccb.py` targets CoreS3 only. It reads GC0308's actual I2C1
page-zero product ID and page-one initialization value before/after three
native init, QVGA framesize and deinit cycles. A failed init or re-probe stops
the sequence before later native camera calls, preserving the first failure.
Use `run_hardware_guest.py --device cores3 --done-marker GC0308_SCCB_DONE`
with an explicit isolated Device Service `--api`, token file and fresh output
directory. Capture lengths/hashes are observations; scene-pixel correctness,
other geometries and physical optics require their own oracles.

`probe_camera_phase.py` uses one of `fixtures/camera_{raw,jpg,bmp,snapshot}`
to isolate a single native operation, records real LCD_CAM register values,
crosses a scheduling boundary, then reconfigures QVGA and captures again.
This localizes native crashes and stale DMA-ring writes without combining
unrelated camera calls. Use `fixtures/camera_fixed_scene.json` as its host
action schedule. `probe_camera_interfaces.py` performs the broader API recipe;
it keeps pipeline teardown/reconfiguration last and stops at the first failed
re-probe. A completed serial marker does not itself establish frame/color
correctness: inspect the independent oracle and all per-method rows.

After retaining the four old/new operation sessions, run:

```sh
python3.12 tests/uiflow2/api_sweep/analyze_camera_phases.py \
  --raw-root .work/api-sweep \
  --baseline-template 'cores3-camera-{case}-phase-baseline-r1' \
  --fixed-template 'cores3-camera-{case}-phase-fixed-exact-r1'
```

This gate requires identical full firmware, guest source and explicit fixture
hashes on both runtimes, real 8-bit/no-conversion MMIO state, exact complete
wire frames after the scheduling boundary and reconfiguration, evidence ZIPs,
and retained stopped sessions with no live runtime process. Encoded BMP/JPG
color comparisons belong to `analyze_camera_interfaces.py`.

`probe_lifecycle.py` runs destructive guest lifecycle calls only in disposable
sessions. A call that returns, hangs or reaches its timeout does not establish
sleep, wake or power-off. Require the matching native state/reset evidence.

## USB library contracts

`probe_usb_core.py` checks real owned Buffer bytes, USB descriptor layout and
bounded interface callbacks. `STATE_PASS` rows explicitly cover local callback
state; `BLOCKED_MODEL` rows retain the missing OTG host/enumeration/endpoint
requirement. The `USB_BOUNDARY` records intentionally violate the Buffer
caller's preconditions and are diagnostic observations, not valid-input API
failures. Optimized official firmware can remove the source's assertions.

Prepare the exact official source and candidate correction for patch `0011`
with `prepare_usb_candidate.py`, then use `run_usb_buffer_correction.py` on each
board with an explicit `--api`, private token file and fresh ignored output
directory. Both modules execute in a guest and use real `machine` IRQ critical
sections. `analyze_usb_buffer.py <output-directory>` verifies module hashes,
the original `to_r4` NameError and consumed bytes, six corrected byte contracts,
evidence ZIP integrity and stopped-session cleanup. This candidate-source
result does not overwrite the stock frozen-firmware failure or establish a USB
endpoint transfer.

## Native LVGL allocator

`probe_lvgl_cache_entry_alloc.py` tests the original return state of
`lv.cache_entry_alloc` for payload sizes 0, 4, 8, 16 and 64. Metadata is checked
before any payload read, write or reference operation. Invalid preimage
metadata produces a FAIL row and only then receives an explicit cleanup repair;
that repair never grants an allocation PASS. Corrected allocations continue
through full zeroed payload, distinct payload/header writes, pointer roundtrip,
reference lifecycle and deletion. Use `run_guest.py --device cores3
--done-marker CACHE_ENTRY_ALLOC_DONE` with the same source on matching SDK
preimage/candidate images and a separate stock-firmware receipt.

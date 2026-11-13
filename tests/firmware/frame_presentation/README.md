# Native framebuffer presentation regression

This fixture exercises original firmware through a visible Device Service
session. The native SPI panel reports actual MADCTL and fixed panel geometry;
the service binds a stable observer generation to the captured raw PNG and
offers explicit `orient=display`. Raw coordinates, RAM writes, physical input
and the browser-WASM recipe are unchanged.

Prerequisites: Python 3.12+, Pillow, the current Device Service, and a native
Xtensa runtime built with `0187-spi-panel-frame-presentation.patch`. Supply an
agent-owned service and the original BIN whose SHA256 you have independently
verified. Do not use the user's resident test services for this fixture.

```sh
python3 tests/firmware/frame_presentation/run_original.py \
  --base-url "$DEVICE_SERVICE_URL" --token-file "$DEVICE_SERVICE_TOKEN_FILE" \
  --firmware "$ORIGINAL_BIN" --sha256 "$ORIGINAL_SHA256" \
  --device sticks3 --rotation 90 --observe-seconds 30 --out "$PRIVATE_EVIDENCE_DIR"
```

The output directory must not exist. The script uploads the exact BIN, performs
the standard merged-image normalization, creates one session, and requests
both representations from the same cached capture. Pillow independently checks
every rotated pixel. The evidence ZIP is requested before stopping with
`purge=0`; history remains available. It does not submit anything to Burner.
Frames, full responses, serial and ZIP output are private raw evidence; publish
only reviewed hashes, controller geometry, comparison booleans and cleanup.

Original StickS3 regression inputs (angles are clockwise raw-to-logical):

| Firmware | SHA256 | Expected angle |
| --- | --- | --- |
| Bruce 1.16.1 | `f4da587db0275e334231de0d458b96285d4cf9f223cf53c462b265ca66e32c4b` | 90 |
| M5Launcher 3.0 | `5eb4e04bcef3b4dbe799a8d6800dccdc583e206da163cc3acfdf898ad0ae960f` | 90 |
| PulseOS 1.4 | `d5d6f3edc42ba1fe53fa3b857039cea788aad4ee74b0ca182a7f68cf742cefa4` | 270 |
| AirMouseS3 1.0 | `bdb567de990ef5c2a0fd113c033b259acd17e49717c9fdb5e9cc9d3776b208d8` | 180 |
| 小智 v2.2.6 | `118b2afbea04832ee323e4e6edf9ea6b64bbdf9ba3ab7535660f09447ab32dba` | 0 |

The angle describes controller logical axes, not an OCR inference about text.
Applications can rotate their own drawing or change layout after this bounded
observation. Host regressions cover all MX/MY/MV rotation and mirror states,
fixed glass transforms, reset, partial windows, capture-generation races,
legacy runtimes, cached 304 metadata and retained evidence. Run them with:

```sh
PYTHONPATH=platform/tools:platform/tests python3 -m unittest \
  test_frame_presentation test_spi_panel_presentation_patch \
  test_frame_cache test_device_frame_preview test_serve_api
```

Host tests and builds are not guest execution. Label actual API runs
`virtual-device validation`; neither those runs nor this observer establishes
physical display optics, RF behavior, browser-WASM acceptance or every firmware
function. Preserve unsuccessful attempts alongside later passing results.

# Real source API and Unit acceptance harness

`run_api_acceptance.py` is ready for root to execute against the restarted local service. This authoring agent has not called any API, started a browser, created a session or run QEMU. Offline preparation is the only executed mode.

All outputs are restricted to fresh children of this directory. The runner never builds a BIN or posts binary artifact intake. It copies existing guest probes and selected official driver files byte-for-byte, generates only `probe_config.py`, sends `{device_id, files, expected_base_sha256}` to the real `/api/v1/firmware/uiflow`, and uses the returned firmware ID plus an exact `uiflow_source_sha256` session pin.

Run from the integration worktree after root has restarted the service with the new source endpoint:

```sh
M5_UNIT_WEB_BRIDGE=1 M5_PYTHON_DEPS=.work/py312 PYTHONPATH=.work/py312 \
  /opt/miniconda3/bin/python3.12 -B \
  .work/unit-agent-api-live-20261026/run_api_acceptance.py \
  --execute --api-url http://127.0.0.1:8787 \
  --expected-runtime-sha256 29d8f6ecdc83f4cbd2ca013291b05bc9ef44fb438a115b0ca97f7b5d46d8d28d \
  --out-dir .work/unit-agent-api-live-20261026/live-r1
```

Add `--case button` for a first isolated smoke case; repeated `--case` selects a subset. Use a new output directory for each run. `M5_UNIT_WEB_BRIDGE_NODE` and `PLAYWRIGHT_CHROMIUM_EXECUTABLE` are honored by the existing bridge if root needs its previously verified Node/Chrome paths. The baseline is pinned to CoreS3 SHA `1324f12d3ddd5392f47a9eff537f9ce0b01a8e6e36d829b6bd22cdf82d2c1264`.

Offline preparation and evidence replay:

```sh
/opt/miniconda3/bin/python3.12 -B \
  .work/unit-agent-api-live-20261026/run_api_acceptance.py \
  --prepare-only --out-dir .work/unit-agent-api-live-20261026/new-preparation

PYTHONPATH=.work/py312 /opt/miniconda3/bin/python3.12 -B \
  .work/unit-agent-api-live-20261026/run_api_acceptance.py \
  --check --out-dir .work/unit-agent-api-live-20261026/live-r1
```

Each case retains canonical source files/CAS identity, actual source API request and response, source artifact metadata, source provenance in the running/retained session and ZIP, raw urllib request/response bodies with actual HTTP status, real browser action/POST/DOM observations, frozen source snapshots, guest serial windows, live QOM observations, native framebuffer and ZIP-before-stop. The final source identity must match caller UTF-8 bytes and the exact source-pin request; it is not used as proof that the guest consumed an input.

Assertions:

- Button: four real trusted touch transitions, active-low fresh guest serial and input counters.
- Relay: fresh guest 0/1 serial cycle plus both live GPIO output levels and transition count; browser checks are readback-only because the Unit is output-only.
- ENV-III: two distinct temperature/humidity/pressure vectors, fresh compensated guest readings and real I2C counters.
- RGB: unchanged original `Observations`/`validate_io` RGB assertions through the native RMT path. Separate saved state/serial/QOM observations let the offline checker independently reconstruct first three-pixel GRB frame, short-frame rejection and second full frame, including threshold/refill/completion counters.
- Encoder: original signed int16 and active-low driver readings for -12345/pressed and 32767/released, I2C counters and both guest-written LED register colors.

Negative controls include wrong base, source path traversal, missing/wrong source session pins (with active count remaining zero), invalid Unit input with unchanged physical input fields, and the original RGB short-frame case. Positive input uses the actual product DOM through `Client`/`WebUIBridge`; invalid API/schema input explicitly bypasses the UI. No fake Client response or firmware upload shim is used. The HTTP recorder preserves bytes returned by the original urllib response/error reads; it only saves copies.

Every created session has a `finally` path that requests its ZIP before DELETE with `purge=0`, retains history/frame/source metadata, checks owned PID exit and mutable Flash release, and requires health `active_sessions=0`. A cleanup failure stops the batch. A browser failure still leaves a ZIP download/stop attempt. The offline checker verifies artifact SHA256SUMS, actual raw HTTP backing, fresh guest windows, native PNGs, browser DOM/HTTP matching, frozen Unit contract sources and source/session/ZIP binding.

Prepared evidence and checker results are virtual-device validation only. They do not establish hardware, electrical or full visual readability acceptance.

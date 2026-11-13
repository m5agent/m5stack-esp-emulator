# Tab5 DWC USB initialization: model-gap classification

Issue [226](https://github.com/m5agent/m5stack-esp-emulator/issues/226) remains
**PARTIAL**. The original Maker Fighter 1.4 application is not ready, and USB
enumeration is **NOT RUN**. This change corrects the repository's
`user_firmware_matrix` result classification; it does not implement USB.

The [bounded evidence](evidence-summary.json) records an unchanged original BIN,
SHA-256 `d96962362b262bcc4e5abcf6a720a2de1a53f0869c87916fd3f798eb845e08b6`,
running through an owned Device Service session for 40.199 seconds. Its complete
serial capture contains 20 `usb_dwc_hal_init` core-identity assertions. The
runtime is pinned by its binary SHA, the application partition is unchanged,
and the evidence ZIP was captured before stopping and releasing the lease and
mutable Flash. This is **virtual-device validation**, not a physical USB test.

The public session reports `device_id=tab5` and `runtime=qemu`. The internal
service kind is `tab5`; using that internal name as a classifier condition made
the condition unreachable through the actual public runtime metadata. Replaying
the same final ZIP serial with the actual metadata previously produced
`FAIL / fatal_without_display`. It now produces `PARTIAL / runtime_model_gap`
with code `tab5_usb_dwc_not_modeled`.

The diagnosis requires all three conditions: the Tab5 public `qemu` runtime,
the specific DWC `core_id`/`GSNPSID` initialization assertion, and a
`usb-host-p4-dwc` catalog entry still marked `planned`. Other boards, unrelated
USB assertions and a future controller implementation do not inherit this
classification. Existing catalog warnings and the planned controller status
remain unchanged.

## Reproduce the original path

Supply the matching original BIN, a ready Tab5 backend with its pinned ROM and
C6 companion, and an owned Device Service URL/token. Use the service's normal
artifact upload and firmware import endpoints:

```sh
curl --fail-with-body -sS "$DEVICE_SERVICE/api/v1/artifacts" \
  -H "Authorization: Bearer $DEVICE_SERVICE_TOKEN" \
  -H 'Content-Type: application/octet-stream' \
  -H 'X-Artifact-Name: maker-fighter-v1.4.bin' \
  --data-binary "@$ORIGINAL_BIN"
```

Import the returned artifact with `POST /api/v1/firmware/import`, using
`{"device_id":"tab5","artifact_id":"<returned artifact>"}`. Check the
normalized firmware SHA against the evidence summary. Create a session with
`{"device_id":"tab5","firmware_id":"<returned firmware>","ttl_seconds":300}`;
omit `runtime` to use its public default, or explicitly request `qemu`.
`runtime=tab5` is not a supported public request.

Retain the create/snapshot metadata and observe serial for 40 seconds. Fetch
`GET /api/v1/sessions/<session>/evidence?include=manifest,serial,frames,logs,flash`
before `DELETE /api/v1/sessions/<session>?purge=0`. Verify the actual runtime
binary SHA and unchanged application partition, then wait for `stopped`,
`flash_retained=false` and `worker.lease_active=false`; stop only the owned
service. Keep raw evidence private because it can contain identifying values.

The postprocessor can be replayed without starting another guest:

```sh
PYTHONPATH=platform/tools python3 - "$SERIAL_LOG" "$SESSION_METADATA" <<'PY'
import json, sys
from pathlib import Path
from user_firmware_matrix import detect_runtime_model_gaps

serial = Path(sys.argv[1]).read_text(errors="replace")
session = json.loads(Path(sys.argv[2]).read_text())
gaps = detect_runtime_model_gaps(
    serial, device_id=session["device_id"], runtime=session["runtime"],
)
assert [gap["code"] for gap in gaps] == ["tab5_usb_dwc_not_modeled"]
print(json.dumps(gaps, indent=2))
PY

PYTHONPATH=platform/tools python3 -m unittest discover \
  -s platform/tests -p test_user_firmware_matrix.py
```

## Retained mistakes and limits

The initial request used the invalid public runtime name and was rejected with
HTTP 400 before any guest started. The second run executed successfully, but
its original reporting script supplied the same wrong name to the classifier.
That report is retained unchanged. The corrected result is a separate replay
of its final ZIP serial with actual session metadata, not a new guest run or a
rewritten execution-source identity. All 35 affected host tests pass.

No frame was captured. This arbitrary BIN has no matching ELF, which also
limits Tab5 framebuffer access; the record does not equate missing capture with
a measured black framebuffer. Repeated USB initialization panics establish
that application readiness was not demonstrated.

The current P4 backend contract provides no DWC controller/root-port/endpoint
attachment data plane. The backend is not rebuildable through this repository's
native QEMU patches. No register read is intercepted, no `GSNPSID` value is
fabricated, and no guest instruction, timeout or driver result is changed.
Closing the USB gap requires a real controller implementation and same-path
HID or MSC enumeration and transfer. Reference Tab5 display/touch/RS-485 guest
tests were not repeated for this postprocessor-only change. Physical hardware,
USB enumeration and transfers remain **NOT RUN**; Burner was not submitted.

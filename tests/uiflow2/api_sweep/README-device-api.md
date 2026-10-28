# Device Service API sweep

`inventory_api.source.json` maps every operation in the pinned OpenAPI contract.
`operation_id` is the exact `METHOD /path/{parameter}` string. Rejected requests
and successful functionality are separate coverage categories: an expected 400,
401 or 404 does not prove a working Run, guest, controller, or lifecycle.

The runners default to an offline plan. Execute against a local Device Service
with a control-token file; never print its contents. Use a new ignored output
directory for each attempt. Raw HTTP responses, source, Flash snapshots, PNGs
and evidence ZIPs remain outside source Git.

```sh
python3 tests/uiflow2/api_sweep/run_device_api.py \
  --execute --api "$M5_API_URL" --token-file "$M5_TOKEN_FILE" \
  --out-dir .work/api-sweep/read-new

PYTHONPATH=.work/py312 python3.12 \
  tests/uiflow2/api_sweep/run_isolated_control.py \
  --execute --firmware-device cores3 --out-dir .work/api-sweep/control-new

PYTHONPATH=platform/tools:.work/py312 python3.12 \
  tests/uiflow2/api_sweep/run_contract_with_receipts.py \
  --execute --contract live --reset --preview --api "$M5_API_URL" \
  --token-file "$M5_TOKEN_FILE" --expected-runtime-sha256 "$M5_QEMU_SHA256" \
  --out-dir .work/api-sweep/live-new

PYTHONPATH=platform/tools:.work/py312 python3.12 \
  tests/uiflow2/api_sweep/run_contract_with_receipts.py \
  --execute --contract network --api "$M5_API_URL" \
  --token-file "$M5_TOKEN_FILE" --expected-runtime-sha256 "$M5_QEMU_SHA256" \
  --out-dir .work/api-sweep/network-new
```

`M5_API_URL` includes `/api/v1` and must identify the dedicated agent test
service. `M5_QEMU_SHA256` pins the executable configured for that service.
The receipt wrapper runs the existing contract unchanged, freezes the actual
PID/start identity and executable hash, checks each pre-stop ZIP against that
session/firmware, then verifies worker/companion teardown and retained history.
It releases the full retained Flash after the explicit snapshot/retention
checks. The original `report.json` and independent `report-with-receipts.json`
remain distinct; only the latter can supply complete artifact-bound acceptance.

The first runner performs safe reads and invalid/missing-resource admission
checks; it never creates a session. The second uses the production HTTP Handler
and stores in a newly owned, ephemeral-port service. It exercises actual artifact,
package, firmware, worker HMAC, job-lease and retention operations without a guest
or mocked store. It does not mutate the shared service's worker or history.

The live runner creates visible CoreS3 guests with a passive HUB, ENV III, NCIR
and Encoder. It uses original firmware drivers, frozen GPIO wiring, explicit
sensor/encoder fixtures, guest serial values, real controller transaction
counters, LED output and same-execution frames. Repeated Run state uses a
dedicated `sys.modules` key. Reset requires fresh boot serial after its cursor.
Each guest receives an evidence ZIP request before stop or Preview close; history
is retained. Flash snapshots in the ordinary-session test explicitly retain Flash.

These are virtual-device checks. They do not establish physical sensor accuracy,
electrical behavior, RF, mechanical rotation or arbitrary firmware compatibility.
Network fault and packet behavior require their own unified-network session;
the ordinary session does not inherit that lane's result.

The dated [Device Service evidence](../../../docs/evidence/2026-10-27-uiflow2-api-sweep/device-service.json)
maps exact operation IDs to positive HTTP cases, rejection-only cases and
unexecuted slots. Positive reads and control-plane operations do not prove
guest functionality or every parameter/device combination. The selected Unit
functional lane is CoreS3 only; the recorded Cardputer-ADV admission response
has no admitted Units. Archived Core2 board/startup and explicit WiFi results
remain separate lanes with their original firmware/runtime hashes.

One retained attempt recorded a receipt failure because Python text reads
normalized CRLF before comparing archived serial with API history. The original
failure is preserved. Its independent `verified-report.json` is produced by
`recheck_contract_receipts.py --report ORIGINAL --out NEW`: it checks the actual
ZIP/history/HTTP-response bytes and requires every other original lifecycle
gate to have passed. This correction grants no missing functionality or missing
runtime/cleanup evidence to older reports.

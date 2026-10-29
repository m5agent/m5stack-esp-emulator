# Lease-bound worker evidence store

Date: `2026-10-29`

## Result

`PASS` for the real authenticated WorkerAgent/control-plane HTTP path. This is
not a QEMU-guest, physical cross-host or object-store replication result.

Device Service API `1.50.0` adds an immutable evidence record derived from the
job ID, live lease ID, worker ID, instance ID and generation. The archived ZIP
is content-addressed by SHA256. A worker must present all three binding headers
and a valid worker HMAC:

- `X-M5-Job-Id`
- `X-M5-Lease-Id`
- `X-M5-Evidence-SHA256`

## Executed evidence

The integration fixture uploaded a `2,097,444`-byte, two-entry ZIP through a
real Device Service subprocess and real `WorkerAgent`.

1. The first upload completed on the server, then the client intentionally
   discarded the successful response.
2. WorkerAgent re-registered and retried the same bytes. The server returned
   the same evidence ID with `idempotent_replay=true`.
3. The control-plane process was stopped and restarted with the same state
   directory. Metadata and ZIP bytes remained readable and hash-identical.
4. Different bytes for the same job/lease returned
   `409 evidence_conflict`.
5. A result carrying a different evidence ID returned 409 before terminal
   state; the correct evidence ID/SHA pair completed the job.
6. Evidence metadata and blob files were mode `0600`; raw evidence markers
   were absent from `jobs.json` and metadata, and the service log did not
   contain the token.

All 17 checks passed.

## Boundaries

- No physical cross-host execution or migration was performed.
- No QEMU guest was started.
- No object-store replication or shared-filesystem-independent durability was
  tested.
- This does not prove ownership of worker-external side effects.
- This does not satisfy the physical-hardware verification gate.

## Reproduction

```bash
PYTHONPATH=platform/tools \
  python3 tests/network/evidence_store/run_test.py \
  --out-dir /tmp/m5-evidence-store
```

Machine-readable summary:
[`summary.json`](summary.json).

# Worker claim response-loss idempotency

This fixture starts a real Device Service HTTP control plane, registers one
worker, queues two jobs and performs one claim with a stable
`claim_idempotency_key`. It then restarts the service from the same state
directory and replays the same claim.

Expected behavior:

- the replay returns the same `job_id` and `lease_id`;
- `claim_idempotent_replay=true`;
- the real `WorkerAgent` receives a committed claim response, then has that
  response discarded by an injected client fault and successfully retries
  with the same key;
- the second queued job is not claimed by the retry;
- reusing the key with a different `job_id` returns
  `409 claim_idempotency_conflict`;
- raw claim keys are not persisted; only identity/request hashes and the
  resulting job/lease IDs are stored;
- a new claim key can claim the second job.

```bash
PYTHONPATH=platform/tools:.work/py python3 \
  tests/network/worker_claim_idempotency/run_test.py \
  --out-dir /tmp/m5-worker-claim-idempotency
```

The fixture does not execute a QEMU guest. It also does not claim physical
cross-host execution, arbitrary packet loss, cross-host process migration or
external side-effect fencing.

The retained summary is
[`evidence-2026-10-29-worker-claim-idempotency-pass.json`](evidence-2026-10-29-worker-claim-idempotency-pass.json).

# Remote worker durable job queue

Last reviewed: `2026-10-24`

This contract slice covers `NET-04` job admission and lease supervision. It
does not launch a QEMU process, execute a claimed request, upload an evidence
bundle or re-attach a process inherited from an earlier Device Service
instance.

## Contract

- `jobs.json` is an atomic, mode-`0600` persistent state file.
- submission is idempotent by `idempotency_key` and canonical request digest;
- worker capabilities must satisfy the job's declared requirements;
- `claim` selects the oldest compatible queued job and increments attempts;
- heartbeat extends only the identity-bound current lease;
- lease expiry or worker stale/stop/missing/generation replacement requeues
  while attempts remain, then marks the job failed;
- result and cancel are terminal; PASS/PARTIAL/REVIEW become completed and
  FAIL becomes failed;
- expired terminal jobs are pruned only when the bounded queue reaches its
  capacity.

HTTP endpoints:

```text
GET  /api/v1/jobs
POST /api/v1/jobs
GET  /api/v1/jobs/{job_id}
POST /api/v1/jobs/claim
POST /api/v1/jobs/{job_id}/heartbeat
POST /api/v1/jobs/{job_id}/result
POST /api/v1/jobs/{job_id}/cancel
```

## Reproduce

```bash
PYTHONPATH=platform/tools python3 -m unittest discover \
  -s platform/tests -p 'test_worker_queue.py' -v
PYTHONPATH=platform/tools python3 -m unittest discover \
  -s platform/tests -p 'test_device_service.py' -v
```

The retained contract result is
`evidence-2026-10-24-queue-pass.json`.

## Boundaries

Queue state is durable, but a claimed job is not proof that a device session
or evidence bundle exists. The independent worker executor, evidence
transfer, active QEMU re-attach and production multi-host scheduling remain
open. This is not an untrusted-firmware sandbox.

# Worker control-plane restart continuity

This Linux/macOS fixture starts separate real control-plane and worker-runtime
Device Services. A `WorkerAgent` claims a job, the central service is killed,
and the worker-local runtime continues booting QEMU. The central service then
restarts from the same state directory; the worker uses bounded reconnect,
re-registers its unchanged identity/generation, retries heartbeat/result and
submits the original lease with collected evidence.

```bash
PYTHONPATH=platform/tools python3 \
  tests/network/worker_control_restart/run_test.py \
  --out-dir /tmp/m5-worker-control-restart
```

The fixture proves control-plane restart continuity and same-lease evidence
reporting. It does not move QEMU between hosts, replace the runtime service,
restore companion helpers, or validate physical hardware.

The first run is retained as a FAIL:
[`evidence-2026-10-25-initial-runtime-qemu-failure.json`](evidence-2026-10-25-initial-runtime-qemu-failure.json).
It exposed an uninitialized `nic` lookup for `runtime=qemu` sessions without a
network profile. The pass evidence is linked as its successor after that code
path was initialized and retested.

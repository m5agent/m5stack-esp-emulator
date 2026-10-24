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

# Worker runtime-service restart and evidence continuity

This fixture keeps the central control plane and WorkerAgent running while the
worker-local Device Service is killed with `SIGKILL`. The StickS3 QEMU child
survives; a new runtime service starts on the same port/state directory,
re-attaches only after PID start-time, QMP ownership and running checks, and
serves the original session evidence.

WorkerAgent retries status/evidence/stop after it has a concrete session ID.
Session creation uses the separate persisted idempotency-key fixture, so a
response-loss retry returns the same session ID instead of creating another
QEMU.

```bash
PYTHONPATH=platform/tools python3 \
  tests/network/worker_runtime_restart/run_test.py \
  --out-dir /tmp/m5-worker-runtime-restart
```

This is local QEMU/QMP continuity, not cross-host process migration,
companion HTTP/BLE continuity or hardware validation.

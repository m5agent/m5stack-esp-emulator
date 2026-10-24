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

The default workload is `runtime=qemu` and proves QEMU/QMP continuity only.
Cross-host process migration and hardware validation remain out of scope.

## Unified companion continuity

Build the unified StickS3 test image and pass it with `--unified-image`:

```bash
PYTHONPATH=.work/py python3 \
  tests/uiflow2/unified_sticks3/make_image.py \
  --base platform/.cache/firmware/sticks3/uiflow2.bin \
  --build-dir \
    .work/uiflow-core2-2.5.3/m5stack/build-M5STACK_StickS3-unified \
  --out /tmp/sticks3-unified.bin

PYTHONPATH=platform/tools python3 \
  tests/network/worker_runtime_restart/run_test.py \
  --unified-image /tmp/sticks3-unified.bin \
  --out-dir /tmp/m5-worker-companion-continuity
```

The BLE peer emits its first `BLE_BUMBLE_PASS`, then waits on a
session-local continuity trigger. After the fixture restarts the runtime:

1. the service recreates the in-process HTTP fixture on the same profile port
   and loads generation-1 requests from durable storage;
2. the service adopts the surviving BLE peer only when PID, exact start time
   and the complete process command SHA256 still match;
3. the fixture writes the trigger, the same peer completes GATT cycle 2, and
   the guest performs an HTTP request against fixture generation 2;
4. the worker waits for the declared evidence delay, collects the final
   evidence ZIP, stops the original session and reports the original lease.

Committed evidence:
[`evidence-2026-10-25-runtime-companion-continuity-pass.json`](evidence-2026-10-25-runtime-companion-continuity-pass.json).
It binds unified image SHA
`04b008c60cf54d1e9fc52b8c9a1c2c4738a7ee046a64000779bebc8de9074c9d`
and verifies same QEMU PID, adopted BLE peer, HTTP generations `[1, 2]`,
network evidence `PASS`, original lease/evidence and QEMU/companion cleanup.

This remains same-host virtual-device validation. It does not claim
cross-subnet discovery, cross-host migration, namespace/Tab5 companion
recovery, RF behavior or hardware.

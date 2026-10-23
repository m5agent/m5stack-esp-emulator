# Worker lifecycle fixture

This fixture starts the real local Device Service and a StickS3 QEMU session,
then verifies the worker control plane:

- stable worker identity and fresh heartbeat;
- active lease visibility;
- drain blocks new leases while the active QEMU session stays usable;
- the worker result retains the session's pcap availability;
- the worker becomes `drained` after the last lease stops;
- resume restores admission;
- a forced service-process-group crash leaves an active lease record;
- the next worker generation records that lease as abandoned and restores the
  session as interrupted `failed` history;
- all service-owned QEMU processes are gone after the crash.

Current passing evidence:
[`evidence-2026-10-24-pass.json`](evidence-2026-10-24-pass.json).

Run from a checkout with the normal `.work/` QEMU runtime and StickS3 reference
firmware:

```bash
python3 tests/network/worker_lifecycle/run_test.py \
  --out-dir /tmp/m5-worker-lifecycle
```

This is local worker lifecycle validation. It does not prove remote worker
registration, task queueing, active QEMU process re-attach, warm pools,
multi-host scheduling or physical hardware behavior.

The fixture uploads the cached StickS3 reference through the normal
Artifact/Firmware API so the `qemu-wifi` lane receives an exact padded 8 MiB
image. A partial reference image is not accepted by the radio runtime.

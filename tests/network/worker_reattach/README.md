# Local QEMU restart re-attach

Last reviewed: `2026-10-26`

This contract slice implements `SVC-01` local control-plane recovery for a
QEMU process that survives a Device Service restart.

Re-attach requires all of:

1. persisted positive PID;
2. exact `ps -o lstart=` start-time token;
3. current process command line contains the session-specific QMP socket;
4. the QMP socket accepts a connection;
5. `query-status` returns `running`;
6. the durable worker lease can be re-created under the new worker generation.

Any mismatch restores the session as `failed`, `interrupted=true`, with a
safe-reattach error and an `interrupted` event. A process is never adopted
from PID alone.

Successful re-attach exposes:

```text
state=running
restored=true
interrupted=false
reattached_process=true
recovery_scope=qemu-control-plane
```

## Reproduce

```bash
PYTHONPATH=platform/tools python3 -m unittest \
  test_device_service.DeviceServiceUnitTests.test_running_orphan_is_rejected_and_verified_process_is_reattached \
  -v
```

Retained result:
`evidence-2026-10-24-reattach-pass.json`.

The same result includes a live service restart: a real `sticks3` QEMU session
was started, only the Device Service PID was killed, the QEMU process stayed
alive, a second service generation re-attached the same PID after all identity
checks, and stopping the session terminated QEMU.

## Boundaries

This fixture only re-attaches the local QEMU/QMP control plane. A separate
runtime-restart fixture now covers trusted-host HTTP/BLE companion continuity;
namespace-managed and Tab5 companions, continuous evidence streaming,
cross-host processes and multi-host scheduling remain `NOT RUN`. The result is
virtual-device infrastructure evidence, not hardware validation.

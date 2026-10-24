# Cross-network-namespace worker control plane

Last reviewed: `2026-10-25`

This Linux-only fixture creates two private network namespaces connected by a
veth pair:

- a server namespace running the real Device Service;
- a worker namespace running the real `WorkerAgent` registration, job claim,
  worker/job heartbeat, result submission and worker stop paths.

The worker uses the service URL over the veth boundary and authenticated
Bearer + worker HMAC requests. The submitted job is deliberately
`control_plane_only` and has no QEMU capability. The fixture verifies that:

1. the worker route resolves through the expected veth;
2. worker registration succeeds;
3. a capability-matching job is submitted and claimed;
4. both lease heartbeats succeed;
5. the terminal result is `completed`;
6. no QEMU process or device session is created;
7. the API token is absent from server/worker logs;
8. both namespaces are removed.

Run as Linux root with `CAP_NET_ADMIN` and `CAP_SYS_ADMIN`:

```bash
PYTHONPATH=platform/tools python3 \
  tests/network/worker_cross_netns/run_test.py \
  --out-dir /tmp/m5-worker-cross-netns
```

This is worker control-plane validation, not cross-host QEMU execution.
`worker_agent.py` now has a separately configurable runtime service API, but
the default invocation still submits a no-QEMU job.

The prepared execution-plane mode starts a second Device Service in the worker
namespace and runs a real StickS3 QEMU session there:

```bash
PYTHONPATH=platform/tools python3 \
  tests/network/worker_cross_netns/run_test.py \
  --qemu \
  --firmware /path/to/sticks3-full.bin \
  --out-dir /tmp/m5-worker-cross-netns-qemu
```

The runtime must be a Linux QEMU build with the M5Stack StickS3 machine at the
repository's registered runtime path. The fixture checks that the central
service does not receive session calls, the worker-local service starts QEMU,
evidence includes manifest/serial data, token redaction holds, QEMU is reaped
and both namespaces are removed. This mode has not yet been executed after the
API split. It validates separate network namespaces on one host, not physically
separate hosts, companion/evidence-stream continuity, cross-host process
re-attach or production multi-host scheduling.

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
this fixture still submits a no-QEMU job. The next integration must launch the
real Device Service/QEMU runtime in the worker namespace, keep artifact uploads
and evidence on that execution plane, then verify process cleanup through the
central job result. Cross-host QEMU executor, companion/evidence-stream
continuity, process re-attach and production multi-host scheduling remain
`NOT RUN`.

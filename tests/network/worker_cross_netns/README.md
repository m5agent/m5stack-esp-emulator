# Cross-network-namespace worker control and execution

Last reviewed: `2026-10-26`

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

The no-QEMU control-plane path was revalidated after the control/runtime API
split in
[`evidence-2026-10-25-control-runtime-split-smoke.json`](evidence-2026-10-25-control-runtime-split-smoke.json):
all 13 checks passed and the token was absent from both service and worker logs.
Endpoint advertisement is covered separately by
[`evidence-2026-10-25-endpoint-advertisement-smoke.json`](evidence-2026-10-25-endpoint-advertisement-smoke.json):
the central directory returned the registered worker endpoint and all 14
control-plane checks passed.

The worker-local execution path was then run with a Linux arm64 QEMU build in
[`evidence-2026-10-25-worker-local-qemu-cross-netns-pass.json`](evidence-2026-10-25-worker-local-qemu-cross-netns-pass.json):
all 18 checks passed. The worker namespace owned an independent Device
Service, uploaded and normalized a StickS3 image, created a real QEMU session,
and returned manifest/serial/QOM evidence to a central durable job. The
result binds source firmware, normalized artifact and QEMU SHA256, reaches
terminal `completed/PASS`, keeps the API token out of logs, and reaps QEMU and
both namespaces. The test also covers the `argv[0]`-based process check so a
host command containing `qemu-system-xtensa` as an argument is not mistaken
for a live emulator.

Run as Linux root with `CAP_NET_ADMIN` and `CAP_SYS_ADMIN`:

```bash
PYTHONPATH=platform/tools python3 \
  tests/network/worker_cross_netns/run_test.py \
  --out-dir /tmp/m5-worker-cross-netns
```

This is worker control-plane validation, not cross-host QEMU execution.
`worker_agent.py` now has a separately configurable runtime service API, but
the default invocation still submits a no-QEMU job.

Authenticated automatic control-plane discovery is covered separately by
[`worker_discovery`](../worker_discovery/README.md): a real worker verifies an
active-token multicast beacon, registers without a hard-coded service URL, and
rejects wrong and pre-rotation tokens. That result is scoped to one multicast
domain and does not prove NAT/cross-subnet forwarding.

The execution-plane mode starts a second Device Service in the worker
namespace and runs a real StickS3 QEMU session there:

```bash
PYTHONPATH=platform/tools python3 \
  tests/network/worker_cross_netns/run_test.py \
  --qemu \
  --qemu-path /path/to/linux/qemu-system-xtensa \
  --firmware /path/to/sticks3-full.bin \
  --out-dir /tmp/m5-worker-cross-netns-qemu
```

The runtime must be a Linux QEMU build with the M5Stack StickS3 machine at the
path supplied by `--qemu-path`; when omitted, the executable path is resolved
from `tests/uiflow2/device_matrix.json`. `--qemu-path` also sets
`M5_QEMU_XTENSA` for the worker-local service. This mode validates separate
network namespaces on one host. It does not claim physically separate hosts,
NAT/cross-subnet discovery, companion/evidence-stream continuity, cross-host
process re-attach or production multi-host scheduling. Same-domain
authenticated discovery has separate evidence in
[`worker_discovery`](../worker_discovery/README.md).

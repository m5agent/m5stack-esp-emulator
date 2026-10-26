# HTTP-only worker executor

Last reviewed: `2026-10-26`

`platform/tools/worker_agent.py` is an independent process that uses only the
public Device Service API:

1. persists worker ID, instance ID and monotonically increasing generation;
2. registers in the remote worker directory;
3. heartbeats the worker directory;
4. claims the oldest capable durable job;
5. creates the requested Device Service session on the execution API;
6. waits for `running`, heartbeating both worker and job lease;
7. downloads and hashes the evidence ZIP;
8. stops the session with `purge=0`;
9. submits PASS/FAIL and the evidence SHA256;
10. marks the worker generation stopped on clean exit.

The executor stores evidence and result metadata under its own work directory.
The control API and execution API can be different services. The worker claims
and heartbeats centrally through `--service-url`, then creates, waits for,
collects evidence from and stops the session through
`--runtime-service-url`. When the runtime URL is omitted, both planes use the
same service for same-host compatibility. A distinct runtime endpoint must
return `/api/health` with `ok=true` before each worker claim. A failed runtime
health check prevents registration/claim and never turns into a queued-job
failure on the central service.
Use `--advertise-endpoint` when the central directory should store an
externally reachable worker HTTP(S) endpoint; credentials, query strings and
fragments are rejected by the directory contract.

When `--token` or `M5_SERVICE_API_TOKEN` is configured, worker-specific
claim/heartbeat/result requests also carry an HMAC signature derived from the
worker ID, instance ID and generation. Timestamp and nonce prevent replay, and
the signed identity must match the JSON body.

## Reproduce

```bash
PYTHONPATH=platform/tools python3 -m unittest discover \
  -s platform/tests -p 'test_worker_agent.py' -v
```

One job:

```bash
python3 platform/tools/worker_agent.py \
  --service-url http://127.0.0.1:8787 \
  --runtime-service-url http://127.0.0.1:8788 \
  --advertise-endpoint https://worker.example:8788 \
  --token "$M5_SERVICE_API_TOKEN" \
  --worker-id local-executor \
  --work-dir /tmp/m5-worker-agent \
  --once
```

Retained result:
`evidence-2026-10-24-executor-pass.json` and authenticated live evidence
`evidence-2026-10-24-executor-auth-pass.json`.

## Boundaries

The control/execution URL split and local-session cleanup are covered by unit
contracts. Worker-local QEMU execution in a separate Linux network namespace
and in a separate Docker container is covered by
[`worker_cross_netns`](../worker_cross_netns/README.md) and
[`worker_cross_container`](../worker_cross_container/README.md). Both still
share one physical host and use a local artifact/firmware store.

The retained QEMU job runs use the same host and service process. HTTPS/mTLS,
real QEMU and unified StickS3 jobs over mTLS are verified separately by
`tests/network/worker_tls/`; the historical evidence in this directory
predates that transport. Certificate rotation and two-worker
generation-pointer migration are verified in `tests/network/worker_tls/`;
multicast and reachable unicast-seed discovery are verified in
`tests/network/worker_discovery/` and `tests/network/worker_discovery_seed/`;
trusted-host companion continuity is verified in
`tests/network/worker_runtime_restart/`. Physical cross-host execution,
namespace-managed/Tab5 companions, no-seed NAT traversal, untrusted-firmware
isolation, production scheduling and hardware remain `NOT RUN`.

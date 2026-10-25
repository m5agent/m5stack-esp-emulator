# Worker network-partition side-effect fencing

This Linux-only fixture proves that a worker fails closed when it can no
longer confirm that it still owns a job lease.

The fixture:

1. creates independent server and worker network namespaces;
2. runs a real central Device Service and a worker-local authenticated runtime
   API with a child process representing an external side effect;
3. lets a real `WorkerAgent` claim a job and create the runtime session;
4. drops only worker-to-control traffic with nftables while leaving the local
   runtime API reachable;
5. forces the job heartbeat to exhaust its bounded reconnect interval;
6. requires the worker to DELETE the runtime session, reap its child process
   and refuse to report a stale result;
7. restores the network, waits for the central lease to expire and be requeued;
8. starts a second worker whose new lease completes the same job.

Run as root or with equivalent network-namespace privileges:

```bash
sudo env \
  "PATH=$PATH" \
  "PYTHONPATH=$PWD/platform/tools" \
  python3 tests/network/worker_partition_fencing/run_test.py \
  --out-dir /tmp/m5-worker-partition-fencing
```

The runtime fixture is intentionally not QEMU. This test proves the
control-plane fencing protocol and a real OS-process side effect, not QEMU
placement, physical cross-host execution, RF or hardware.

Committed evidence:
[`evidence-2026-10-25-partition-fencing-3x.json`](evidence-2026-10-25-partition-fencing-3x.json).
Three independent runs pass `18/18` checks; each first worker fences and reaps
its side effect, the lease expires and is requeued, and attempt 2 completes
`PASS`.

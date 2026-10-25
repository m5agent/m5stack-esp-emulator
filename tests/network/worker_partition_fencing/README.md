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

The default runtime fixture is a lightweight authenticated HTTP session with a
real OS child process, suitable for CI. The optional QEMU lane runs a real
worker-local Device Service and StickS3 QEMU:

```bash
sudo env \
  "PATH=$PATH" \
  "PYTHONPATH=$PWD/platform/tools" \
  python3 tests/network/worker_partition_fencing/run_test.py \
  --qemu \
  --qemu-path /path/to/linux/qemu-system-xtensa \
  --firmware /path/to/sticks3-full.bin \
  --out-dir /tmp/m5-worker-partition-qemu
```

The stronger lane runs one `qemu-unified` guest with the HTTP fixture, external
BLE peer and pcap in the same runtime:

```bash
sudo env \
  "PATH=$PATH" \
  "PYTHONPATH=$PWD/platform/tools" \
  python3 tests/network/worker_partition_fencing/run_test.py \
  --qemu-unified \
  --qemu-path /path/to/linux/qemu-system-xtensa \
  --firmware /path/to/sticks3-unified-8MiB.bin \
  --out-dir /tmp/m5-worker-partition-unified
```

Both lanes prove control-plane fencing and process cleanup. The QEMU lane
additionally proves that the worker-local QEMU PID is reaped after the
blackhole and that attempt 2 can boot a fresh QEMU and complete the job.

Committed evidence:
[`evidence-2026-10-25-partition-fencing-3x.json`](evidence-2026-10-25-partition-fencing-3x.json).
Three independent runs pass `18/18` checks; each first worker fences and reaps
its side effect, the lease expires and is requeued, and attempt 2 completes
`PASS`.

The QEMU lane also has three independent runs:
[`evidence-2026-10-25-partition-fencing-qemu-3x.json`](evidence-2026-10-25-partition-fencing-qemu-3x.json).
All three runs pass `18/18` checks. In each run, attempt 1 starts a real
StickS3 QEMU, loses the control plane, is fenced, and has its QEMU PID
reaped; attempt 2 starts a fresh QEMU and reaches terminal `PASS`.

The plain `--qemu` lane uses `runtime=qemu` and proves ownership and cleanup
of the worker-local QEMU **process**. The `--qemu-unified` lane additionally
waits for the same session's HTTP request, BLE pass and non-empty pcap before
partitioning, then requires both companion states to terminate, the BLE peer
PID to be reaped, the pcap summary to finalize, and a fresh unified retry to
complete.

Neither lane proves physical cross-host execution or hardware behavior. The
unified lane also does not expose guest/controller-internal state after QEMU
exit; process and provider cleanup must not be described as an internal guest
quiesce.

# Worker QEMU execution across containers

Last reviewed: `2026-10-25`.

Status: `PASS` for the reviewed two-container implementation. The committed
three-run aggregate is
[`evidence-2026-10-25-cross-container-qemu-3x.json`](evidence-2026-10-25-cross-container-qemu-3x.json).
This closes the one-Docker-daemon cross-container QEMU boundary; it is not a
claim of physical cross-host execution.

This fixture advances the existing one-host network-namespace worker test to
two independent Docker containers on a user-defined bridge:

- central container: durable queue, worker directory and control API;
- worker container: one `worker_agent` job path plus a worker-local Device
  Service that owns the real QEMU session and evidence.

The worker talks to the central queue only by the container-network name. The
runtime API remains worker-local. The job must reach terminal `completed`
with `execution_plane=worker-local`, a real QEMU PID/session, manifest and
serial evidence, exact source/normalized firmware and QEMU hashes, no leaked
QEMU process, no credential in any log, and complete container/network
cleanup.

Build the pinned runtime image:

```bash
docker build \
  -t m5-emulator-cross-container:latest \
  -f tests/network/worker_cross_container/Dockerfile \
  .
```

Run with a Linux arm64 QEMU build and a StickS3 full-flash image:

```bash
python3 tests/network/worker_cross_container/run_test.py \
  --qemu .work/M5StopWatch-QEMU/build/qemu-linux-arm64/qemu-system-xtensa \
  --rom-dir .work/M5StopWatch-QEMU/build/qemu/pc-bios \
  --firmware .work/cname-guest-dev/probe.bin \
  --out-dir .work/worker-cross-container
```

Run the fixture three times from fresh container/network names and summarize:

```bash
python3 tests/network/worker_cross_container/summarize_runs.py \
  --run .work/worker-cross-container-9 \
  --run .work/worker-cross-container-10 \
  --run .work/worker-cross-container-11 \
  --diagnostic-failure .work/worker-cross-container \
  --diagnostic-failure .work/worker-cross-container-2 \
  --out tests/network/worker_cross_container/evidence-2026-10-25-cross-container-qemu-3x.json
```

This proves two independent execution units on one Docker daemon. It does not
prove physically separate hosts, arbitrary NAT traversal without a reachable
seed, process migration or re-attach, companion continuity, production
scheduling or hardware.

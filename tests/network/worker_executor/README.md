# HTTP-only worker executor

Last reviewed: `2026-10-24`

`platform/tools/worker_agent.py` is an independent process that uses only the
public Device Service API:

1. persists worker ID, instance ID and monotonically increasing generation;
2. registers in the remote worker directory;
3. heartbeats the worker directory;
4. claims the oldest capable durable job;
5. creates the requested Device Service session;
6. waits for `running`, heartbeating both worker and job lease;
7. downloads and hashes the evidence ZIP;
8. stops the session with `purge=0`;
9. submits PASS/FAIL and the evidence SHA256;
10. marks the worker generation stopped on clean exit.

The executor stores evidence and result metadata under its own work directory.

## Reproduce

```bash
PYTHONPATH=platform/tools python3 -m unittest discover \
  -s platform/tests -p 'test_worker_agent.py' -v
```

One job:

```bash
python3 platform/tools/worker_agent.py \
  --service-url http://127.0.0.1:8787 \
  --worker-id local-executor \
  --work-dir /tmp/m5-worker-agent \
  --once
```

Retained result:
`evidence-2026-10-24-executor-pass.json`.

## Boundaries

The retained live run uses the same host and service process. Cross-host
networking, worker authentication hardening, companion continuity after
service restart, untrusted-firmware isolation, production scheduling and
physical hardware remain `NOT RUN`.

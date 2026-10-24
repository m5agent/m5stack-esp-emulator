# Authenticated worker control-plane discovery

This live fixture starts a real Device Service with an HMAC-authenticated IPv4
multicast beacon and a real `WorkerAgent` without a hard-coded control URL.
The worker discovers the advertised base URL, registers, heartbeats and stops.

Run:

```bash
PYTHONPATH=platform/tools python3 \
  tests/network/worker_discovery/run_test.py \
  --out-dir /tmp/m5-worker-discovery
```

The fixture also proves that a worker with the wrong token does not register.
It does not create a QEMU session, traverse NAT/subnets without multicast, or
validate multi-host scheduling. Discovery trusts only a beacon signed with the
same active master token as the control plane; HTTPS certificate verification
remains separate.

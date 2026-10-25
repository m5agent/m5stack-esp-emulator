# Authenticated unicast worker discovery across subnets

This Linux-only fixture proves a routable unicast bootstrap path for workers
that cannot receive the control plane's multicast domain.

Topology:

```text
worker namespace             router namespace             control namespace
10.213.2.10/24   <->   10.213.2.1 / 10.213.1.1   <->   10.213.1.10/24
                         IPv4 forwarding + NAT
```

The control plane continues to announce authenticated multicast locally, but
that beacon is not forwarded by the router. A worker therefore uses a
reachable discovery seed URL. The seed returns the same HMAC-signed beacon,
and `WorkerAgent` verifies the signature before using the advertised control
URL.

Run as root or with equivalent network-namespace privileges:

```bash
sudo env \
  "PATH=$PATH" \
  "PYTHONPATH=$PWD/platform/tools" \
  python3 tests/network/worker_discovery_seed/run_test.py \
  --out-dir /tmp/m5-worker-discovery-seed
```

The evidence requires:

- isolated `10.213.2.0/24` and `10.213.1.0/24` namespaces with a routed,
  masqueraded path;
- multicast discovery timeout despite the control-plane announcer;
- unicast seed discovery, registration and clean worker shutdown;
- wrong/old token rejection and token rotation;
- the control-side seed access log showing the router address rather than the
  worker address;
- namespace, nftables and process cleanup.

This is virtual control-plane validation. It does not prove physical
cross-host execution, arbitrary NAT traversal, QEMU placement, production
multi-host scheduling or hardware.

The seed test uses HTTP inside an isolated private network. Production
deployments should expose the seed over HTTPS or a trusted private transport;
the HMAC signature proves beacon authenticity, not confidentiality.

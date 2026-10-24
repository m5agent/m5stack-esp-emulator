# Exact IP and port egress allowlist

Last reviewed: `2026-10-24`

This Linux-only integration test proves that an isolated namespace can reach
one exact IPv4 TCP destination and one exact IPv6 TCP destination while
blocking a different port and a different address in each family.

The fixture creates a private worker namespace and a separate upstream
namespace. The worker has IPv4 and IPv6 default routes to the upstream, while
the sandbox creates:

- a private QEMU namespace;
- an inner veth pair and temporary worker-side `inet` NAT table;
- an nftables input/output policy with default `drop`;
- one explicit IPv4 endpoint and one explicit IPv6 endpoint;
- only IPv6 neighbor solicitation/advertisement as the required control-plane
  exception;
- loopback-only allowances for controlled DNS/HTTP and host control sockets.

Run on a Linux worker with `CAP_NET_ADMIN`, `CAP_SYS_ADMIN`, `iproute2`,
`nftables`, root privileges, and IPv4/IPv6 forwarding enabled:

```bash
python3 tests/network/egress_allowlist/run_test.py \
  --out-dir /tmp/m5-egress-allowlist
```

The fixture starts HTTP servers in the upstream namespace. The inner probe
must:

1. connect to the explicitly allowed IPv4 address and port;
2. fail to connect to a second listening port on the same address;
3. fail to connect to the same allowed port on a different IPv4 address;
4. connect to the explicitly allowed IPv6 address and port across the IPv6
   default route;
5. fail to connect to a second IPv6 port and to the same port on another IPv6
   address.

Only the allowed servers may receive requests. The upstream peer addresses
must equal the worker veth addresses, proving that both IPv4 and IPv6 used
masquerade rather than a loopback shortcut. Evidence also records the nftables
enforcement mode, routes, inner probes and cleanup outcome.

This validates the network policy engine. It does not by itself prove a
firmware guest, physical RF, general public-internet availability, CIDR or
domain policy, IPv6 DNS/AAAA behavior or malware safety.

GitHub Actions runs this deterministic fixture as the
`network-namespace-policy` job together with the full platform suite. The
successful Ubuntu runner evidence is
[`evidence-2026-10-24-github-actions-pass.json`](evidence-2026-10-24-github-actions-pass.json).
That CI job validates Linux namespace/nftables policy and cleanup, not QEMU
guest behavior or a self-hosted worker lifecycle.

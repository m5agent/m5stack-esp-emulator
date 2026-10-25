# IP/CIDR and port egress allowlist

Last reviewed: `2026-10-25`

This Linux-only integration test proves that an isolated namespace can reach
one allowed IPv4 CIDR and one exact IPv6 TCP destination while blocking a
different port and an address outside the IPv4 CIDR.

The fixture creates a private worker namespace and a separate upstream
namespace. The worker has IPv4 and IPv6 default routes to the upstream, while
the sandbox creates:

- a private QEMU namespace;
- an inner veth pair and temporary worker-side `inet` NAT table;
- an nftables input/output policy with default `drop`;
- one bounded IPv4 `/30` endpoint and one exact IPv6 endpoint;
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

1. connect to an address and port inside the allowed IPv4 `/30`;
2. fail to connect to a second listening port on the same address;
3. fail to connect to the same allowed port on an IPv4 address outside the
   `/30`;
4. connect to the explicitly allowed IPv6 address and port across the IPv6
   default route;
5. fail to connect to a second IPv6 port and to the same port on another IPv6
   address.

Only the allowed servers may receive requests. The upstream peer addresses
must equal the worker veth addresses, proving that both IPv4 and IPv6 used
masquerade rather than a loopback shortcut. Evidence also records the nftables
enforcement mode, routes, inner probes and cleanup outcome.

CIDRs narrower than `/16` for IPv4 and `/48` for IPv6 are accepted. The policy
rejects broad rules and CIDRs overlapping unspecified, loopback, link-local,
multicast, IPv4-mapped IPv6 or QEMU SLiRP synthetic space. Domain suffixes are
validated separately by the controlled DNS and HTTP tests; a domain grant
must resolve to an address covered by an allowed endpoint.

This validates the network policy engine. It does not by itself prove a
firmware guest, physical RF, general public-internet availability, arbitrary
domain-to-IP binding, same-guest firmware IPv6 DNS/HTTP behavior or malware
safety.

The local repeat result is recorded in
[`evidence-2026-10-25-cidr-dual-stack-docker-pass.json`](evidence-2026-10-25-cidr-dual-stack-docker-pass.json):
22/22 checks pass, including an allowed `/30`, denied outside address, denied
port, exact IPv6 address, dual-stack NAT source rewrite and cleanup.

The earlier exact-IP-only baselines remain available as
[`evidence-2026-10-24-dual-stack-docker-pass.json`](evidence-2026-10-24-dual-stack-docker-pass.json)
and
[`evidence-2026-10-24-dual-stack-github-actions-pass.json`](evidence-2026-10-24-dual-stack-github-actions-pass.json).

GitHub Actions runs this deterministic fixture as the
`network-namespace-policy` job together with the full platform suite. The
successful Ubuntu runner evidence is
[`evidence-2026-10-24-github-actions-pass.json`](evidence-2026-10-24-github-actions-pass.json).
The next source-bound CI run re-executes the current CIDR fixture. These jobs
validate Linux namespace/nftables policy and cleanup, not QEMU guest behavior
or a self-hosted worker lifecycle.

# Exact IP and port egress allowlist

Last reviewed: `2026-10-24`

This Linux-only integration test proves that an isolated namespace can reach one
exact TCP destination while blocking a different port on the same host and the
same port on a different IP.

The sandbox creates:

- a private QEMU namespace;
- a veth pair and temporary worker-side NAT table;
- an nftables input/output policy with default `drop`;
- one explicit allowed endpoint;
- loopback-only allowances for controlled DNS/HTTP and host control sockets.

Run on a Linux worker with `CAP_NET_ADMIN`, `CAP_SYS_ADMIN`, `iproute2`,
`nftables`, root privileges and IPv4 forwarding enabled:

```bash
python3 tests/network/egress_allowlist/run_test.py \
  --out-dir /tmp/m5-egress-allowlist
```

Add `--public` to additionally allow and test `1.1.1.1:80`. This exercises the
per-session veth/NAT path; the default run uses a worker-local target for a
deterministic CI check.

The fixture starts two HTTP servers outside the isolated namespace. The inner
probe must:

1. connect to the explicitly allowed IP and port;
2. fail to connect to a second listening port on the same IP;
3. fail to connect to the same allowed port on a different IP.

Only the allowed server may receive a request. The evidence records the nftables
enforcement mode, veth/NAT metadata, inner probe results and cleanup outcome.

This validates the network policy engine. It does not by itself prove a
firmware guest, physical RF, public-internet availability, IPv6 egress or
malware safety.

GitHub Actions runs this deterministic fixture as the
`network-namespace-policy` job together with the full platform suite. The
successful Ubuntu runner evidence is
[`evidence-2026-10-24-github-actions-pass.json`](evidence-2026-10-24-github-actions-pass.json).
That CI job validates Linux namespace/nftables policy and cleanup, not QEMU
guest behavior or a self-hosted worker lifecycle.

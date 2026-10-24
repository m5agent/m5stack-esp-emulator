# ESP-IDF DNS and UDP probe

This fixture connects to the network lane's virtual AP and:

1. obtains a DHCP lease;
2. resolves `example.com` through the emulator's configured DNS forwarder;
3. sends a fixed UDP datagram to the user-mode gateway on port `19000`; and
4. requires the host peer to return `UDP_REPLY:` plus the original payload.

The DNS step intentionally uses the network lane's host resolver path. It is a
DNS/UDP data-plane probe, not an offline DNS-policy fixture. Controlled
A/NXDOMAIN policy is now covered separately by
[`../tls_allowlist/README.md`](../tls_allowlist/README.md) inside the Linux
private net/mount namespace; do not describe this probe as offline DNS
isolation.

Expected terminal marker:

```text
DNS_UDP_RESULT: PASSED
```

Validated evidence:
[`evidence-2026-10-24-dns-udp-pass.json`](evidence-2026-10-24-dns-udp-pass.json).
The guest resolved the DNS name through the host-forwarder path, sent the exact
UDP payload, and received the exact `UDP_REPLY:` payload. This is data-plane
evidence, not controlled A/NXDOMAIN policy.

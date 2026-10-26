# Controlled DNS CNAME chain

Last reviewed: `2026-10-26`.

This fixture exercises exact-name CNAME aliases in the controlled DNS resolver:

- aliases must be covered by policy exact hosts or an allowed domain suffix;
- chains are limited to eight links and reject cycles;
- every final target must resolve through an existing exact or suffix record;
- a CNAME owner cannot also have exact or domain-suffix address data;
- A/AAAA answers include the CNAME chain plus the final address record;
- CNAME queries return the chain without an address;
- DNS logs retain chain links, terminal name and final exact/suffix rule.

Run:

```bash
python3 tests/network/dns_cname_chain/run_test.py \
  --out /tmp/m5-dns-cname.json
```

This is resolver-data-plane evidence. It does not start a guest firmware, a
network namespace or QEMU. Public DNS, DNSSEC, rebinding resistance and
hardware remain outside scope.

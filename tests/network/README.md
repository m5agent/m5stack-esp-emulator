# Network and worker test index

Last reviewed: `2026-10-25`

These fixtures cover virtual radio data planes, Linux network policy, pcap,
multi-guest fabric and the distributed worker control/runtime planes. Current
capability and open tasks remain in
[`docs/project-status.md`](../../docs/project-status.md) and
[`docs/project-backlog.md`](../../docs/project-backlog.md).

## Fixture map

| Fixture | What it executes | What it does not prove |
| --- | --- | --- |
| [`linux_isolation`](linux_isolation/README.md) | Guest boot and route isolation inside a private Linux namespace | production malicious-firmware sandbox |
| [`tls_allowlist`](tls_allowlist/README.md) | Test CA, controlled DNS, Host decision, TLS 200/403 and pcap | arbitrary public services or certificate pinning |
| [`dns_cname_chain`](dns_cname_chain/README.md) | Bounded CNAME resolution, A/AAAA-chain encoding, CNAME-query encoding, NXDOMAIN and invalid graph rejection | guest firmware lifecycle or public DNS |
| [`cname_guest_lifecycle`](cname_guest_lifecycle/README.md) | Three Device Service leases with guest CNAME→terminal A→HTTP, denied name/port, pcap and namespace cleanup | public DNS/DNSSEC or physical RF |
| [`egress_allowlist`](egress_allowlist/README.md) | Bounded IPv4 CIDR plus exact IPv6 destination, protocol and port policy with cleanup | Arbitrary broad/special CIDRs or unbound public-domain resolution |
| [`idf_dns_udp`](idf_dns_udp/README.md) | ESP-IDF DNS/UDP data plane through the controlled resolver | UI or complete-device behavior |
| [`idf_dhcp_renewal`](idf_dhcp_renewal/README.md) | Guest-issued DHCP renewal with address and HTTP continuity | long-term lease churn |
| [`wrong_password`](wrong_password/README.md) | WPA2-PSK wrong-password rejection and no-DHCP/no-HTTP negative gate | WPA3 or RF behavior |
| [`reconnect_probe`](reconnect_probe/README.md) | Radio/link loss, rescan, DHCP and HTTP recovery | AP roaming or physical signal behavior |
| [`lab_fabric`](lab_fabric/README.md) | Two StickS3 guests over a private QEMU socket L2 switch | production multi-host worker fabric |
| [`ipv6_end_to_end`](ipv6_end_to_end/README.md) | Controlled AAAA, allowed IPv6 HTTP, denied port, pcap and cleanup | stock UIFlow2 IPv6 default configuration |
| [`core2_openeth`](core2_openeth/README.md) | Core2 OpenETH-like host data-plane diagnostic | Core2 WiFi or complete-device acceptance |
| [`core2_openmac_wifi`](core2_openmac_wifi/README.md) | Core2 OpenMAC scan/DHCP/HTTP path | complete Core2 board or physical RF |
| [`worker_lifecycle`](worker_lifecycle/README.md) | Local worker heartbeat, drain, resume and abandoned lease classification | remote multi-host scheduling |
| [`worker_queue`](worker_queue/README.md) | Durable submit/claim/heartbeat/result/cancel and lease expiry | execution of the job |
| [`worker_executor`](worker_executor/README.md) | HTTP worker claim, real session, evidence and result | cross-host migration |
| [`worker_tls`](worker_tls/README.md) | HTTPS/mTLS, worker HMAC, rotation, drain, overlap and real QEMU jobs | production secret manager or physical multi-host PKI |
| [`worker_discovery`](worker_discovery/README.md) | Authenticated same-domain multicast control discovery and token rotation | NAT or cross-subnet discovery |
| [`worker_control_restart`](worker_control_restart/README.md) | Central control-plane restart and original job/evidence convergence | runtime-service replacement or process migration |
| [`worker_runtime_restart`](worker_runtime_restart/README.md) | Runtime Device Service SIGKILL, same-PID/QMP reattach, evidence retry, trusted-host HTTP recreation and BLE peer adoption | namespace/Tab5 companion recovery, cross-host migration or hardware |
| [`worker_reattach`](worker_reattach/README.md) | Local QEMU PID/start-time/QMP ownership reattach | companion HTTP/BLE helper reattach |
| [`worker_cross_netns`](worker_cross_netns/README.md) | Server/worker veth namespaces and optional worker-local StickS3 QEMU | two physical hosts or automatic NAT traversal |
| [`session_idempotency`](session_idempotency/README.md) | Concurrent and restart-safe `POST /sessions` idempotency | cross-host/tenant idempotency storage |

Every evidence file is an observation for its run, not a promise that a later
public firmware or runtime produces the same result. See the root
[`tests/README.md`](../README.md) for evidence naming and validation-layer
rules.

## Common commands

Most policy fixtures require Linux root with `CAP_NET_ADMIN` and
`CAP_SYS_ADMIN`. Read the case README for the exact capability and runtime
assets, then run, for example:

```bash
PYTHONPATH=platform/tools python3 \
  tests/network/worker_runtime_restart/run_test.py \
  --out-dir /tmp/m5-worker-runtime-restart
```

The no-QEMU worker paths prove control and lifecycle contracts only. A result
is a virtual-device result only when the fixture starts the matching guest and
captures its serial/frame/network/peer evidence.

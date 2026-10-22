# ESP-IDF DNS and UDP probe

This fixture connects to the network lane's virtual AP and:

1. obtains a DHCP lease;
2. resolves `example.com` through the emulator's configured DNS forwarder;
3. sends a fixed UDP datagram to the user-mode gateway on port `19000`; and
4. requires the host peer to return `UDP_REPLY:` plus the original payload.

The DNS step currently uses the host resolver path. A fully controlled DNS
resolver requires a privileged port-53 fixture or a future dedicated DNS test
service; do not describe this probe as offline DNS isolation.

Expected terminal marker:

```text
DNS_UDP_RESULT: PASSED
```

# Core2 OpenMAC WiFi model

This patch imports the ESP32 classic WiFi device from
`esp32-open-mac/qemu` commit
`47ff9135c3f8890c9d93a2775eb4e5f6d8e65c04` into the current M5 QEMU 9.2.2
source tree.

Upstream:

- https://github.com/esp32-open-mac/qemu
- commit message: `Implement undocument wifi registers, get AP mode working`
- upstream date: `2023-07-04`

The patch includes:

- ESP32 ANA/FE/PHY-A register stubs;
- the WiFi MAC MMIO, DMA descriptor handling and IRQ path;
- QEMU-hosted 802.11 beacon/probe/auth/association frames;
- a default test AP named `myssid`;
- an APB alias for the WiFi register block;
- current QEMU 9.2 `qemu_new_nic()` integration with a real
  `MemReentrancyGuard`.

## Verified boundary

On QEMU 9.2.2, a stock Core2 UIFlow2 `network.WLAN` probe passes:

- WiFi active;
- `scan()` returns three APs;
- probe/authentication/association management exchange is observable;
- DHCP succeeds and UIFlow2 receives `10.0.2.15/24`, gateway `10.0.2.2` and
  DNS `10.0.2.3` from QEMU user networking;
- a controlled HTTP GET through the QEMU user-net gateway returns
  `HTTP/1.0 200 OK`.

DNS requests, external internet access and BLE remain `NOT RUN`.

This is a simulation bring-up patch, not a complete WiFi implementation and not
real-hardware validation.

## Base and apply check

The patch was generated against the current working tree of:

```text
.work/M5StopWatch-QEMU/build/qemu
```

with existing M5 board patches applied and QEMU version `9.2.2`.

```bash
git -C .work/M5StopWatch-QEMU/build/qemu apply --check \
  "$PWD/patches/qemu-core2-openmac-wifi/0001-esp32-openmac-wifi-model.patch"
```

## Rollback

```bash
git -C .work/M5StopWatch-QEMU/build/qemu apply --reverse \
  "$PWD/patches/qemu-core2-openmac-wifi/0001-esp32-openmac-wifi-model.patch"
```

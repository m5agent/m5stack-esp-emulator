# ESP32-C6 QEMU WiFi public-network probe

This probe replaces only the UIFlow2 application scripts in the official
NanoC6 v2.5.3 image. It exercises the QEMU `misc.esp32c6.wifi` NIC through the
stock `network.WLAN` driver:

1. activate STA mode and scan the open `myssid` virtual AP;
2. complete Authentication and Association;
3. obtain `10.0.2.15/24`, gateway `10.0.2.2` and DNS `10.0.2.3` through SLiRP;
4. resolve `example.com`; and
5. send a raw TCP HTTP/1.0 GET and require an `HTTP/` response.

Build and run:

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/c6_qemu_wifi_probe/make_image.py \
  --base platform/.cache/firmware/nanoc6/uiflow2.bin \
  --build-dir .work/uiflow-core2-2.5.3/m5stack/build-M5STACK_NanoC6-wifi \
  --app-only \
  --out /tmp/m5-c6-wifi-public.bin

.work/M5StopWatch-QEMU/build/qemu-c6/build/qemu-system-riscv32 \
  -M esp32c6 \
  -drive file=/tmp/m5-c6-wifi-public.bin,if=mtd,format=raw,snapshot=on \
  -L .work/M5StopWatch-QEMU/build/qemu-c6/pc-bios \
  -display none -serial null -serial null \
  -serial file:/tmp/m5-c6-wifi-public-serial.log \
  -nic user,model=misc.esp32c6.wifi,id=wifi0
```

Required markers are `C6_QEMU_WIFI_CONNECTED 1`,
`C6_QEMU_WIFI_DNS_IPV4`, `C6_QEMU_WIFI_HTTP` and
`C6_QEMU_WIFI_PUBLIC 1`.

This is virtual-device validation of QEMU MAC/DMA/IRQ and SLiRP. It is not RF,
PHY, antenna, electrical or real-hardware validation. The public HTTP check
depends on the host's network; the controlled unified tests use a local HTTP
fixture for repeatable CI.

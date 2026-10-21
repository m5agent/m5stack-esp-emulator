# QEMU ARM64 CardputerZero backend

This patch adds the Linux/BCM2837 side used by CardputerZero to the M5Stack
QEMU source tree. It is simulation infrastructure, not real-hardware support
validation.

Apply it after the standalone shared M5Stack peripheral snapshot:

```bash
cd "$QEMU_ROOT/build/qemu"
git apply /path/to/0003-m5stack-shared-spi-full.patch
git apply /path/to/qemu-linux-arm64-cardputerzero/0001-qemu-linux-arm64-cardputerzero.patch
git apply /path/to/qemu-linux-arm64-cardputerzero/0002-bcm2835-i2s-dreq-dma.patch
git apply /path/to/qemu-linux-arm64-cardputerzero/0003-sr9900a-usb-ethernet.patch
```

The patch includes:

- BCM2835 ASB register block with the `BRDG` identity and ACK behavior needed
  by Linux `bcm2835-power`;
- BCM2835 GPIO level/edge interrupt registers and an ARM-side input bridge;
- a real BCM2835 watchdog timer instead of treating watchdog arming as an
  immediate board reset;
- `raspi3b -m 512M` support so QEMU can represent CardputerZero's physical
  512 MiB LPDDR2;
- BCM2835 I2S CS/FIFO/mode MMIO, bounded TX PCM capture and RX PCM injection;
- DREQ-gated BCM DMA control-block scheduling for cyclic ALSA playback and
  capture, including bounded `M5SW_DMA_TRACE` diagnostics;
- ES8389 8-bit I2C register model with identity `0x83/0x89` and powered
  `CSM_STATE1=0x0D`;
- autonomous IP2315 QOM power-path model with `charging`, `vbus-mv` and
  `ntc-ohms` properties; charging state drives the BQ27220 signed-current
  register used by Linux `power_supply`;
- a GL852G USB 2.0 hub subtype of QEMU's standard hub model with the
  datasheet-default `05e3:0610` identity and four downstream ports;
- an SR9900A/RTL8152B-compatible USB Ethernet model with vendor register
  requests, bulk TX/RX descriptors, `r8152` driver binding and a QEMU socket
  packet bridge;
- BCM GPIO13 LIRC receive waveform injection and GPIO12 GPIO-IR TX edge capture;
- TCA8418 interrupt-status write-one-to-clear and active-low idle-high wiring;
- BQ27220 16-bit command word handling, little-endian byte pairing and
  seal/unseal control.

## Verification

The patch was built and tested with:

- official CardputerZero Trixie arm64 image;
- Linux `6.18.39+rpt-rpi-v8`;
- QEMU `-M raspi3b -m 512M`;
- generated M5Stack DTB from `tests/cardputer_zero/build_dtb.py`;
- no `bcm2835-powermgt.ignore-reset` global workaround.

Verified paths:

- BCM2835 power domains and watchdog;
- 320x170 ST7789v3 DRM framebuffer;
- QMP TCA8418 event through BCM GPIO27 to Linux `/dev/input`;
- BMI270/BMM150 IIO, RX8130 RTC, M5IOE1 pinctrl/PWM/ADC and BQ27220
  power_supply;
- ES8389 I2C probe and identity/state readback.
- ALSA playback with real BCM DMA-to-I2S PCM capture.
- Microphone capture with byte-exact RX PCM/WAV round-trip and `arecord`
  exit status 0.
- Runtime IP2315 QOM charging injection changes Linux battery status from
  `Charging` to `Discharging` and current from `+250000` to `-250000` uA.
- BCM2837 DWC2 host mode enumerates the GL852G hub as `05e3:0610` with the
  expected Genesys Logic product/manufacturer strings.
- Linux `r8152` creates `eth0`, reports carrier on, and exchanges custom
  Ethernet request/response frames byte-for-byte with a host packet peer.
- GL852G and SR9900A both enumerate at High-Speed through the hub, and the
  Ethernet frame round-trip passes on that high-speed path.
- The TT compatibility path routes a Full-Speed SR9900A Ethernet child and a
  Low-Speed USB HID through the High-Speed upstream hub; Linux reaches `eth0`
  and the HID input device.
- Linux DAPM AW8737A enable observed on BCM GPIO24 during the playback path.
- Linux LIRC mode2 receive and NEC GPIO transmit capture.

GL852G TT routing is functional rather than cycle-accurate; USB split
transaction timing is not modelled packet-by-packet. AW8737A analog validation
still requires real hardware.

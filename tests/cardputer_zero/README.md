# CardputerZero ARM64 Linux backend

CardputerZero is an RP3A0/BCM2837 Linux computer, not an ESP32/UIFlow2
firmware target. This directory contains the reproducible QEMU boot,
display, input, I2C-peripheral and audio probes.

All results here are **simulation results**. They do not replace validation
on physical CardputerZero hardware.

## Official image

The official M5Stack manifest is:

`https://cardputer-zero-repo.oss-cn-shenzhen.aliyuncs.com/os-list.json`

Current stable arm64 image:

- image: `cardputerzero-trixie-arm64-stable.img.xz`
- compressed size: `1786957924`
- compressed SHA256: `b37a702aea8b5d75015b48c99b8c969efc2636b82757282fb27cf03056788c91`
- extracted size: `7415529472`
- extracted SHA256: `cc95c131e8f77d96d016fac22579fd0a08009e4b821fc4c543fa122fdda84f0f`
- kernel: `6.18.39+rpt-rpi-v8`

The extracted raw image must be expanded to a power-of-two size accepted by
QEMU's SD model. The current work image is 8 GiB.

Download, verify, extract, expand and install probes:

```bash
python3 tests/cardputer_zero/prepare_image.py
```

It reads the official manifest, verifies both compressed and extracted
SHA256, extends the raw image to 8 GiB, and calls `install_guest.py`.
The boot partition still needs `kernel8.img`, `bcm2710-rpi-cm0.dtb`, and the
vendor `overlays/` copied into `.work/cardputerzero/boot/`.

## Build the test DTB

The vendor audio overlay contains a duplicate unnamed `simple-audio-card`
DAI link. One link points at a nonexistent codec phandle, which makes
`asoc-simple-card` reject the complete sound card. The helper removes only
that invalid link while preserving the valid `dai-link@0`. It also adds the
vendor GPIO IR overlays and moves RX/TX from the conflicting default GPIO18
to schematic GPIO13/GPIO12.

```bash
python3 tests/cardputer_zero/build_dtb.py \
  --base-dtb .work/cardputerzero/boot/bcm2710-rpi-cm0.dtb \
  --overlay-dir .work/cardputerzero/boot/overlays \
  --out .work/cardputerzero/boot/cardputerzero-v5-test.dtb
```

Add `--imx219` to merge the official two-lane `imx219.dtbo` onto CSI1. The
helper also replaces the firmware-private Unicam VPU clock with a 250 MHz
fixed clock and removes the synthetic CSI/power devlink cycle used by the
QEMU-only boot path.

Required host tools: `dtc`, `fdtoverlay`, and QEMU.

## Install guest probes

The installer writes the probe scripts and systemd units into the ext4 root
partition. On macOS it uses `hdiutil` and Homebrew `e2fsprogs`; on Linux it
uses `losetup --partscan`.

```bash
python3 tests/cardputer_zero/install_guest.py \
  --image .work/cardputerzero/cardputerzero-work.img
```

The installer also builds a small AArch64 `FBIOBLANK` compatibility shim for
the headless factory UI. It uses `aarch64-linux-gnu-gcc` when available,
otherwise Homebrew `llvm` + `lld`.

The probes are gated by kernel command-line flags:

- `m5.key_probe=1`: capture one keyboard event and framebuffer hashes.
- `m5.audio_probe=1`: exercise ALSA controls, playback and capture.
- `m5.ir_probe=1`: discover LIRC RX/TX devices and run raw receive/send.

## Boot, display and keyboard

```bash
M5SW_I2C_TRACE=1 M5SW_GPIO_TRACE=1 \
python3 tests/cardputer_zero/run_linux_boot.py \
  --machine raspi3b --memory 512M \
  --image .work/cardputerzero/cardputerzero-work.img \
  --kernel .work/cardputerzero/boot/kernel8.img \
  --dtb .work/cardputerzero/boot/cardputerzero-v5-test.dtb \
  --append "console=ttyAMA1,115200 \
root=PARTUUID=f6c408b0-02 rootfstype=ext4 rootwait rw \
earlycon=pl011,0x3f201000 systemd.unit=multi-user.target" \
  --out-dir /tmp/m5-cardputer-zero-keyframe \
  --complete-marker M5_KEY_FRAME_DONE \
  --qmp-key-event 129 \
  --expect-cardputerzero-peripherals \
  --timeout 180
```

The runner injects TCA8418 event `0x81` after the guest reports
`M5_KEY_FRAME_READY`. Verified path:

`QMP -> TCA8418 FIFO -> BCM GPIO27 -> Linux tca8418_keypad -> /dev/input`.

Verified display path:

`ST7789v3 panel-mipi-dbi -> DRM card0-SPI-1 -> /dev/fb1 -> 320x170 RGB565`.

The current headless guest leaves the registered panel framebuffer black, so
the guest fbdev before/after hashes are equal. The keyboard event itself is
asserted through a non-empty Linux input event record.

The official `factory_test` completes framebuffer selection, TCA8418 input
discovery, asset loading and LVGL startup at `320x170`. The QEMU SPI panel sink
can reconstruct RGB565 pixels from the panel-mipi-dbi stream; the probe also
captures `/dev/fb1` directly. The LVGL frame is fully non-black
(`54400/54400` pixels) with 127 distinct RGB565 values and a changed frame hash.

```bash
python3 tests/cardputer_zero/run_factory_ui_probe.py --require-frame
```

The runner requires the startup path above and now reports `frame=PASS` from
the DRM framebuffer evidence.

## Audio

Create a bounded RX PCM input, then run with:

```bash
M5SW_I2S_TX_FILE=/tmp/cardputerzero-tx.pcm \
M5SW_I2S_TX_LIMIT_BYTES=1048576 \
M5SW_I2S_RX_FILE=/tmp/cardputerzero-rx.pcm \
M5SW_I2S_RX_LIMIT_BYTES=64000 \
M5SW_GPIO_TRACE=1 \
M5SW_DMA_TRACE=1 \
python3 tests/cardputer_zero/run_linux_boot.py \
  --machine raspi3b --memory 512M \
  --image .work/cardputerzero/cardputerzero-work.img \
  --kernel .work/cardputerzero/boot/kernel8.img \
  --dtb .work/cardputerzero/boot/cardputerzero-v5-test.dtb \
  --append "console=ttyAMA1,115200 \
root=PARTUUID=f6c408b0-02 rootfstype=ext4 rootwait rw \
earlycon=pl011,0x3f201000 systemd.unit=multi-user.target m5.audio_probe=1" \
  --out-dir /tmp/m5-cardputerzero-audio \
  --complete-marker M5_CZ_PROBE_DONE \
  --expect-audio-gpio24 \
  --expect-audio-capture \
  --timeout 180
```

The QEMU BCM2835 I2S model exposes CS/FIFO/mode registers. BCM DMA writes
are captured from the TX FIFO as real PCM words. DREQ-driven DMA runs one
control block per timer period instead of completing a cyclic descriptor chain
synchronously; this keeps ALSA's circular buffer live without forcing DMA
abort/EIO. Verified result:

- ALSA card 0 is registered as `ES8388Audio / simple-card`.
- `aplay` exits 0.
- 1 MiB of playback PCM is captured.
- 524288 S16 samples contain 211178 nonzero samples, peak 2896, RMS 1299.6.
- Linux DAPM asserts the AW8737A enable on BCM GPIO24 during playback.
- A 2-second, 16 kHz stereo 440 Hz PCM source injected through the I2S RX FIFO
  produces a 64044-byte WAV capture. Its canonical WAV SHA256 exactly matches
  the injected 64000-byte PCM payload with a 44-byte PCM header.
- `arecord` exits 0.

## Infrared

Run with:

```bash
M5SW_IR_TX_FILE=/tmp/cardputerzero-ir-tx.txt \
M5SW_IR_RX_FILE=/tmp/cardputerzero-ir-rx.txt \
python3 tests/cardputer_zero/run_linux_boot.py \
  --machine raspi3b --memory 512M \
  --image .work/cardputerzero/cardputerzero-work.img \
  --kernel .work/cardputerzero/boot/kernel8.img \
  --dtb .work/cardputerzero/boot/cardputerzero-v5-test.dtb \
  --append "console=ttyAMA1,115200 \
root=PARTUUID=f6c408b0-02 rootfstype=ext4 rootwait rw \
earlycon=pl011,0x3f201000 systemd.unit=multi-user.target m5.ir_probe=1" \
  --out-dir /tmp/m5-cardputerzero-ir \
  --complete-marker M5_CZ_PROBE_DONE \
  --qmp-ir-inject \
  --timeout 180
```

Verified path:

- `/dev/lirc` capabilities are discovered at runtime because Linux may assign
  receiver/transmitter node numbers in either order;
- QMP starts a GPIO13 waveform only after the guest receiver reports ready;
- Linux `gpio-ir-receiver` returns 773 bytes of mode2 pulse/space data;
- `ir-ctl --scancode=nec:0x10ef` drives GPIO12;
- QEMU captures 2136 timestamped GPIO12 output edges.

## Camera

The IMX219 CCI device answers Linux at I2C address `0x10`. BCM2837 Unicam CSI1
is a real MMIO model: Linux programs the RG10 format, 1280-byte stride and the
guest V4L2 DMA address, then QEMU writes the complete frame and raises CAM1
frame-start/frame-end interrupts.

```bash
python3 tests/cardputer_zero/run_camera_probe.py \
  --out-dir /tmp/m5-cardputerzero-camera \
  --expected-sha256 5568cf027da59228168e211e27283adaad4eaf6c299a4ad44026b0b703f7af4c
```

Verified path:

- `imx219` and `unicam` both bind;
- `/dev/media0` exposes the sensor -> `unicam-image` link and `/dev/video0`;
- `v4l2-ctl --stream-mmap=4 --stream-count=1` exits 0;
- the 640x480 RG10 frame is 614400 bytes;
- two independent runs produced the same frame SHA256.

The sensor model now stores the real IMX219 mode, output window, frame/line
timing, exposure, analogue/digital gain, orientation and test-pattern
registers. Unicam generates each frame from those register values instead of
ignoring the sensor configuration. A control-path probe uses the official
Linux V4L2 controls and verifies the resulting register state through QOM:

```bash
python3 tests/cardputer_zero/run_camera_probe.py \
  --controls \
  --expected-sha256 d837dbbc02798310b0f7f940cc5e1c6e469ef5a7ffbe7feb8d92f0c8a8f5bcbe
```

Verified controls are `test_pattern=Solid Color`, `exposure=1000`,
`analogue_gain=64` and `digital_gain=320`. The driver divides exposure by the
2x2 binning factor, so the sensor registers contain exposure `500`; the
resulting frame hash differs from the default scene. This is a deterministic
simulated sensor frame, not a physical-camera capture.

## Charging state

The schematic shows IP2315 as an autonomous charger; its LEDs are hard-wired
and it has no BCM I2C control path. The emulator therefore models the charger
at the power-path level and exposes it as `/machine/peripheral/m5-ip2315`.
Changing its `charging` property updates the BQ27220 signed current, which
Linux `bq27xxx` exposes through `power_supply`.

```bash
python3 tests/cardputer_zero/run_linux_boot.py \
  --image .work/cardputerzero/cardputerzero-work.img \
  --kernel .work/cardputerzero/boot/kernel8.img \
  --dtb .work/cardputerzero/boot/cardputerzero-v5-test.dtb \
  --append "console=ttyAMA1,115200 \
root=PARTUUID=f6c408b0-02 rootfstype=ext4 rootwait rw \
earlycon=pl011,0x3f201000 systemd.unit=multi-user.target" \
  --out-dir /tmp/m5-cardputerzero-charge \
  --complete-marker M5_CZ_PROBE_DONE \
  --qmp-charging-marker M5_CHARGE_PROBE_READY \
  --expect-charging-control \
  --timeout 180
```

Verified transition:

```text
CHARGE_STATUS_BEFORE=Charging
CHARGE_CURRENT_BEFORE=250000
CHARGE_STATUS_AFTER=Discharging
CHARGE_CURRENT_AFTER=-250000
```

Run the full combined regression, including PCM hashes, keyboard injection,
charger transition, V4L2 camera frame hash, framebuffer and driver bindings:

```bash
python3 tests/cardputer_zero/run_full_probe.py
```

## USB hub

The test DTB enables the BCM2837 DWC2 controller in host mode. QEMU attaches
an `m5sw-gl852g` model to the root port using the GL852G default identity from
the datasheet (`05e3:0610`) and four downstream ports.

Verified Linux enumeration:

```text
usb 1-1: New USB device found, idVendor=05e3, idProduct=0610
usb 1-1: Product: GL852G USB 2.0 Hub
usb 1-1: Manufacturer: Genesys Logic, Inc.
```

The SR9900A model uses the RTL8152B register programming interface expected by
Linux `r8152`. The guest creates `eth0`, negotiates a link and exchanges real
RTL8152 TX/RX descriptors with a host-side packet peer:

```text
USB_ETH_TX=02000000990102000000990088b54d352d535239393030412d5458...
USB_ETH_RX=02000000990002000000990188b54d352d535239393030412d5258...
USB_ETH_ROUNDTRIP=PASS
```

The hub model provides an MTT-compatible routing path: the child model retains
its real full/low speed while the HCD sees a High-Speed upstream port and sends
normal packets through the hub. This is the functional QEMU equivalent of the
hub's transaction translator; packet timing is not cycle-accurate.

Both direct root-port attachment and the GL852G downstream path enumerate at
High-Speed.

Run the isolated driver and packet round-trip test:

```bash
python3 tests/cardputer_zero/run_usb_ethernet_probe.py
```

The SR9900A full-speed descriptor and data path are independently verified at
the root port:

```bash
python3 tests/cardputer_zero/run_usb_ethernet_probe.py \
  --direct --full-speed
```

This produces `USB_ETHERNET PASS PASS speed=full` at the root port. The same
Full-Speed descriptor/endpoint model behind the GL852G TT also completes the
Ethernet round trip:

```bash
python3 tests/cardputer_zero/run_usb_ethernet_probe.py \
  --full-speed --tt-compat
```

An independent low-speed HID child validates the LS routing branch:

```bash
python3 tests/cardputer_zero/run_usb_low_speed_probe.py
```

It reports `tt_mask=2`; Linux binds the QEMU USB mouse input device while the
hub's QOM property shows that downstream port 2 is TT-translated.

## Peripheral status

| Path | Status | Evidence |
| --- | --- | --- |
| Linux boot with 512 MiB | PASS | BCM2835 power domains probe without the previous ASB abort |
| ST7789v3 framebuffer | PASS | DRM card0-SPI-1, fb1, 320x170 RGB565 |
| TCA8418 keyboard | PASS | QMP event to Linux input event |
| M5IOE1 | PASS | Linux pinctrl/PWM/ADC children probe |
| BMI270 + BMM150 | PASS | Linux IIO devices `bmi270` and `bmm150` |
| RX8130CE | PASS | Linux `rtc-ds1307` |
| BQ27220 | PASS | 4.0 V, 250 mA, 87%, 1750 mAh design capacity |
| SD card | PASS | Root filesystem and data read through QEMU SD |
| ES8389 playback | PASS | ALSA playback and DMA/I2S PCM capture |
| ES8389 microphone | PASS | RX FIFO injection, exact 64 KiB PCM/WAV capture |
| AW8737A speaker | PASS | Playback PCM + BCM GPIO24 amplifier enable observed |
| IP2315 charger | PASS | QOM charging injection to BQ27220 signed current and Linux power_supply |
| GL852G USB hub | PASS | HS hub, FS Ethernet TT round-trip and LS HID enumeration/input |
| SR9900A Ethernet | PASS | High-Speed `r8152`/`eth0` and bidirectional frame round-trip |
| IMX219 CSI-2 | PASS | CCI + Unicam CSI1, V4L2 RG10 frame, 614400 bytes |
| IR TX/RX | PASS | GPIO13 LIRC RX mode2 + GPIO12 NEC TX edge capture |

Machine-readable evidence:
`tests/cardputer_zero/evidence/2026-10-21-linux-backend.json`.

# ESP32-P4 peripheral backend requirements

Last reviewed: `2026-10-24`. Capability evidence remains the Tab5
`2026-10-22` focused probe.

This document defines the minimum runtime interfaces needed to close the
remaining Tab5 peripheral gaps without bypassing the firmware driver,
controller, DMA/FIFO or endpoint path.

The current native `esp-emu 0.50.0` backend exposes UART, GPIO, GDB, ESP-Hosted
and a startup-only I2C register file. Those interfaces are sufficient for
display, touch mailbox, RS-485, deterministic power snapshots and static I2C
probes, but not for a full interactive peripheral simulation.

## 1. Dynamic I2C device bridge

Required operations:

```text
attach(port, address, model, options)
read_state(device_id)
write_state(device_id, changes)
watch(device_id, register, callback)
inject_irq(device_id, line)
```

Requirements:

- Host writes update the device model state, not the guest memory.
- Guest transactions must still pass through the ESP32-P4 I2C controller.
- Register-pointer, repeated-start, multi-byte and burst semantics must match
  the chip model.
- Device-side state machines must be able to run asynchronously: RTC time,
  BMI270 initialization/sample updates, INA226 conversion/alert, PI4IOE input
  and interrupt changes, ST7123 touch reports and IP2326 charger transitions.
- A model must expose its reset state and survive or react to reset writes from
  the firmware in the same way as hardware.

Tab5 acceptance:

- `machine.I2C` / `M5.In_I2C` reads BMI270 `CHIP_ID=0x24`, then returns new
  accel/gyro samples after a host update.
- RX8130 and PCF8563-compatible time continues moving after an initial host
  synchronization.
- INA226 voltage/current updates and alert bits change at runtime.
- PI4IOE `0x0F` CHG_STAT and interrupt bits change without relaunching the
  emulator.
- ST7123 touch coordinates arrive through its controller registers.
- IP2326 charging current and termination transition from charging to complete
  without a process restart.

## 2. I2S / PCM endpoint

Required operations:

```text
attach_i2s(port, mode, clock, format)
push_rx_pcm(port, samples)
pull_tx_pcm(port, max_samples)
```

The host ring buffer must sit after the P4 I2S controller and GDMA FIFO. Tests
must capture the bytes the firmware writes and provide bytes the firmware reads.

Tab5 acceptance:

- ES7210 microphone configuration over I2C followed by PCM RX reaches
  `Mic.record()`.
- ES8388 I2C configuration and I2S TX produce a non-silent host capture.
- NS4150B enable GPIO is asserted on the same path.

## 3. MIPI-CSI frame endpoint

Required operations:

```text
attach_csi_controller(lanes, format)
attach_camera_i2c(address, model)
push_frame(width, height, format, bytes)
frame_complete()
```

The SCCB register model configures the camera; the P4 CSI controller and DMA
deliver the frame. A host must not write the MicroPython camera buffer directly.

Tab5 acceptance:

- SC2356 identity and mode configuration pass over SCCB.
- A known RGB/RAW frame reaches `camera.snapshot()` with the expected dimensions
  and pixel hash.

## 4. USB Host controller and endpoints

Required operations:

```text
attach_usb_host(controller)
attach_usb_device(port, descriptor, endpoints)
send_endpoint(address, payload)
receive_endpoint(address)
```

Enumeration must use the P4 DWC host controller and standard Chapter 9
transfers. HID, storage and network devices should be attachable without board
specific guest hooks.

## 5. SDIO block backend

Required operations:

```text
attach_sdio(slot, image_path)
read_blocks(lba, count)
write_blocks(lba, count, bytes)
```

The block device must be visible through the normal SDMMC driver and filesystem
stack. Raw-image verification is performed by the host after guest writes.

## 6. GPIO and interrupt side effects

Dynamic peripheral models need a host-visible event path for:

- charger status and power-good transitions;
- IO-expander interrupts;
- INA226 alert and conversion-ready;
- BMI270 interrupt lines;
- ST7123 touch interrupt;
- SD card detect and write-protect;
- USB over-current and port-power state.

GPIO injection must update the physical line model. Firmware-facing status must
be consumed through the same GPIO/IRQ controller path as hardware.

## 7. Conformance gate

The backend is not complete until:

1. Every Tab5 component in `platform/peripherals/catalog.json` is `simulated`.
2. Tab5's completion-policy exemption is removed.
3. `run_tab5_peripheral_scenarios.py` includes live state transitions rather
   than launch-time preloads.
4. `run_tab5_ui_test.py` captures display, touch, audio, camera, USB and storage
   evidence in one reproducible device profile.
5. No test writes the firmware's MicroPython variables to fake a device reading.

## 8. Deferred backlog status (2026-10-22)

The remaining Tab5 data planes are intentionally deferred rather than treated
as a blocker for every other device. The current backend already supports
virtual flashing, UIFlow2 boot, 1280x720 MGFX output, touch mailbox input,
RS-485, C6 ESP-Hosted and static I2C register probes.

Deferred work, in suggested priority order:

| Priority | Work | Acceptance boundary | Rough effort |
| --- | --- | --- | --- |
| P1 | Dynamic I2C bridge and device state machines | BMI270 samples, RX8130 progression, INA226 alert, PI4IOE IRQ and IP2326 transitions without process restart | 3–5 days |
| P1 | P4 I2S/PCM | ES7210 microphone RX and ES8388 speaker TX through the P4 controller/GDMA | 2–4 days |
| P2 | MIPI-CSI | SC2356 SCCB configuration and a deterministic frame through `camera.snapshot()` | 3–5 days |
| P2 | P4 USB Host | Chapter 9 enumeration and at least one HID/storage endpoint | 4–7 days |
| P2 | SDIO block backend | Guest-visible block device and host-side image verification | 2–4 days |
| P3 | ST7123 controller-level touch | Touch reports through the real I2C controller instead of the GDB mailbox | 2–3 days |
| P3 | IP2326 charger state machine | Current/termination/charging transitions observable through the normal power path | included in P1 |

The estimates assume a rebuildable/extensible P4 backend and do not include
the separate long-term work of running all board peripherals and WiFi in one
QEMU instance. Resume this backlog only when a firmware under review needs one
of these data planes or when ST7123/IP2326 behavior becomes part of a release
gate.

See [`tab5-deferred-backlog.md`](tab5-deferred-backlog.md) for the current
usable boundary, resume conditions and evidence requirements.

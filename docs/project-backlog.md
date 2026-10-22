# Project backlog

Date: `2026-10-22`

This backlog separates product-facing work from the already completed
UIFlow2 board/peripheral validation. Estimates are engineering ranges, not
release commitments.

## P0: network simulation lane

Goal: let S3/C6/P4 virtual devices run real network-dependent firmware against
a controlled network, with DNS/TCP/UDP evidence and packet summaries.

Deliverables:

1. One-device UIFlow2 or ESP-IDF proof for scan, association, DHCP, DNS and TCP;
2. isolated user-mode networking with `hostfwd`;
3. pcap/DNS/connection evidence bundle;
4. S3/C6/P4 profile integration and reconnect/wrong-password cases;
5. Tab5 P4 ↔ C6 ESP-Hosted end-to-end proof;
6. separate Core2 ESP32 LX6 WiFi/PHY path;
7. same-instance board + WiFi model only if later required.

Implemented on 2026-10-22:

- reusable isolated network/BLE runner with redacted, hashed evidence;
- StickS3/CoreS3 and NanoC6/Nesso N1 WiFi/DHCP and controlled HTTP/TCP
  download;
- StickS3 UIFlow2 BLE server observed by an external Bumble GATT peer;
- C6 WiFi stays active during external Bumble scan/connect/GATT
  write/readback;
- host-forwarder DNS plus controlled UDP request/reply;
- Device Service `runtime=network` sessions and evidence endpoint.

Still open:

- isolated DNS policy and host packet summaries;
- device-level C6 and remaining S3 runs;
- combined board-peripheral plus network guest.

Rough effort:

- S3/C6/P4 network lane: 2–3 working weeks;
- Tab5 ESP-Hosted closure: 2–4 additional working days;
- Core2 LX6 network path: 1–2 working weeks;
- same-instance QEMU board + WiFi: 2–4 additional working weeks.

See [`network-simulation-plan.md`](network-simulation-plan.md).

## P0: generic firmware intake and review

Goal: make “firmware under review” a first-class input, not an implicit
UIFlow2 image.

Initial supported families:

- UIFlow1/UIFlow2;
- ESP-IDF;
- Arduino ESP32;
- MicroPython;
- vendor or custom full-flash ESP32 images.

Required work:

1. Define a firmware manifest for:
   - complete merged image;
   - separate bootloader/partition/app/filesystem segments and offsets;
   - chip, flash size, SHA-256, source and license;
   - optional ELF, MAP, `flasher_args.json` and sdkconfig metadata;
2. accept artifacts from local upload, public URL and build-worker output;
3. normalize M5Burner/WebBurner-style downloads into a complete virtual flash;
4. reject incompatible chip, partition, eFuse or address layouts with a reason;
5. run static image/partition/filesystem/string checks before boot;
6. keep the current UIFlow2 metadata as a built-in default, not the only path;
7. add one ESP-IDF and one Arduino reference artifact for onboarding tests.

Rough effort: 1–2 working weeks for intake and static checks; 2–4 additional
working days for broker/UI integration.

See [`firmware-review-and-simulation-workflow.md`](firmware-review-and-simulation-workflow.md).

## P0: simulator host service and worker pool

Goal: expose virtual devices to Device Center as leased sessions with serial,
frame, input, flash and evidence APIs.

Required work:

1. one-instance-per-lease lifecycle with immutable flash base and
   copy-on-write overlay;
2. cached runtime container images and bounded warm pools;
3. device-model concurrency policy (`min_ready`, `max_instances`, `idle_ttl`);
4. task-scoped exact firmware flash, never shared mutable flash;
5. serial/frame/input/evidence APIs and lease cancellation;
6. separate trusted-preview and untrusted-firmware review pools;
7. resource quotas, network isolation and teardown verification.

Rough effort: 3–4 working weeks for a usable MVP; 2–3 additional weeks for
production isolation, observability and capacity management.

See [`simulator-service-architecture.md`](simulator-service-architecture.md).

Implemented on 2026-10-22:

- local on-demand QEMU process runner;
- session leases with TTL and concurrency limits;
- content-addressed artifact upload;
- merged/segmented firmware composition;
- prepared-flash cache plus per-session isolated flash copy;
- serial, frame, input, QOM, reset and log APIs.
- restart-safe stopped/failed session history, events, last frame and device
  state; active processes are marked interrupted rather than silently lost.

Still backlog:

- resumable active emulator processes across service restart;
- prestarted warm pool;
- remote worker scheduling and multi-host capacity;
- untrusted-firmware isolation and quota enforcement;
- network namespace and pcap integration.

## P1: Tab5 deferred peripheral closure

The current Tab5 virtual host already supports virtual flashing, UIFlow2 boot,
1280×720 framebuffer, touch mailbox, RS-485, C6 ESP-Hosted and static I2C
register probes.

Deferred items:

- dynamic I2C/device state machines;
- P4 I2S/PCM;
- MIPI-CSI/SC2356;
- P4 USB Host;
- SDIO block backend;
- controller-level ST7123 touch;
- IP2326 current/termination state machine.

See [`tab5-deferred-backlog.md`](tab5-deferred-backlog.md). With a rebuildable
P4 backend, the remaining work is roughly 4–6 serial weeks or 2–3 weeks with
parallel workstreams.

## P1: high-fidelity device visual modeling

Current visual fidelity is not sufficient: only StopWatch has a dedicated
physical shell and screen opening; the other devices still use approximate
generic shells and CSS decorations.

This is a specialist visual/3D modeling task. The future agent must build
measured per-device manifests, layered body/screen/control assets, physical
hitboxes, framebuffer clipping and visual regression evidence. Do not try to
close this by tweaking the generic shell dimensions alone.

See [`device-visual-fidelity-backlog.md`](device-visual-fidelity-backlog.md).

## P1: long-running stability and hardware evidence

- Fix the Core2 intermittent cache panic rather than relying on retries.
- Run the latest clean full matrix before a milestone.
- Add real-hardware validation on the same implementation paths for any public
  or release-facing claim.

# AtomS3 C123 candidate probe

This probe targets the independent `m5atoms3` board, ESP32-S3FN8, 8 MiB
Flash, no PSRAM and package eFuse 0. It must use the official **AtomS3**
UIFlow2 image (`1897200000000002444`, v2.5.3), not AtomS3R firmware.

The original M5 display and GPIO41 `M5.BtnA` driver draw a 128×128 screen,
increment a guest-owned counter on a press and print the matching release.
The initial marker is red; the first press changes it to green. Serial
markers use `ATOMS3_*` so another board's output cannot satisfy this probe.

The device matrix declares its exact VFS layout and `memory: "0"`. Compose
through the existing source/image tools, then upload and execute through a
dedicated Device Service with a separate port/state/token. Preserve the
same session's serial, frame, input and evidence receipt before stopping.
Do not use the user's service ports 8787 or 8830.

Registration is a candidate, not a functional PASS. MPU6886, GPIO35 WS2812,
GPIO4 IR, arbitrary applications and hardware behavior require separate
device-local evidence.

# Firmware review and runtime evidence

Last reviewed: `2026-10-24`

This directory stores committed evidence for firmware normalization, static
review and public-firmware runtime tests. The evidence files are snapshots, not
the implementation or the test runner.

Implementation lives under `platform/tools/` and contract tests live under
`platform/tests/`. The public firmware matrix runner is
`platform/tools/user_firmware_matrix.py`.

Common checks:

```bash
PYTHONPATH=platform/tools python3 -m unittest \
  platform/tests/test_firmware_manifest.py \
  platform/tests/test_firmware_analysis.py \
  platform/tests/test_firmware_filesystems.py \
  platform/tests/test_firmware_static_review.py \
  platform/tests/test_user_firmware_matrix.py
```

The historical cross-vendor snapshot records 18 non-baseline samples on six
S3/C6 devices; the combined current selection adds three public Core2 images,
for 21 non-baseline samples on seven devices. Its `PARTIAL` results are not all
simulator defects:
`runtime_model_gap`, missing application frame, absent input response,
serial-only devices and fatal post-frame evidence retain separate reasons.
The original C6 software-reset chip-id gap has a separate fix evidence snapshot;
that firmware now reaches the ordinary `fatal_after_application_frame` path
without a `runtime_model_gap`. The C6 Zigbee gap remains open:
`c6_zigbee_thread_sim/run_feasibility.py` observed bidirectional 802.15.4
frames from source-built switch/light examples, but commissioning/join did not
complete.

Filesystem inventories include a per-file `permission_policy`. FAT directory
attributes are recorded without treating them as POSIX access control;
LittleFS and SPIFFS explicitly report that Unix mode bits are absent. Runtime
permission/ACL enforcement remains `NOT RUN`.

Packages that include source files also receive a bounded SPDX header scan.
Source path hashes and declarations are eligible for license policy, while
generated code, absent third-party sources and legal review remain out of
scope.

The API and WebBurner accept explicit required/optional hardware capabilities.
The same normalization and mismatch contract applies to CLI and HTTP imports:
aliases are canonicalized, declarations are bounded and a target without a
required capability returns a structured manifest rejection. Declarations are
operator-provided; they do not prove that every firmware code path uses the
declared peripheral.

For the Core2 public-firmware runtime gap, focused I2C tracing distinguishes a
successful AXP2101 chip-id read from the later legacy controller/board-bus
routing failure. The next controller transaction targets address `0x51` and
receives no ACK before another address-0x34 PMIC read occurs. Frozen BM8563
qstrs and the call stack point to the RTC-candidate path; PMIC register
semantics are not yet the proven first cause.

Known emulator capability gaps are maintained in
[the runtime model-gap register](../../docs/runtime-model-gap-register.md).
Current overall status and unfinished work must be read from
[project status](../../docs/project-status.md) and
[project backlog](../../docs/project-backlog.md), not inferred from an older
evidence date.

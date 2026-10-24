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

The public cross-vendor snapshot currently records 18 non-baseline samples on
six S3/C6 devices. Its `PARTIAL` results are not all simulator defects:
`runtime_model_gap`, missing application frame, absent input response,
serial-only devices and fatal post-frame evidence retain separate reasons.
The original C6 software-reset chip-id gap has a separate fix evidence snapshot;
that firmware now reaches the ordinary `fatal_after_application_frame` path
without a `runtime_model_gap`. The C6 Zigbee gap remains open.

Known emulator capability gaps are maintained in
[the runtime model-gap register](../../docs/runtime-model-gap-register.md).
Current overall status and unfinished work must be read from
[project status](../../docs/project-status.md) and
[project backlog](../../docs/project-backlog.md), not inferred from an older
evidence date.

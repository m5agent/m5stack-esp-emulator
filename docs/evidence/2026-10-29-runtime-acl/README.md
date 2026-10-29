# Device Service runtime ACL

Date: `2026-10-29`

## Result

`PASS` for `host-runtime validation`. Device Service API/OpenAPI `1.51.0`
loads an optional operator-owned runtime ACL from a bounded regular JSON file.
When configured, undeclared devices and operations fail closed before runtime
I/O; when omitted, the service reports `NOT_CONFIGURED` and retains the
historical local-control behavior.

The policy covers `serial.read`, `input.write`, `guest.reset`, `program.read`,
`program.execute`, `program.interrupt`, `filesystem.write` and `flash.read`.
Program execution requires an explicit `main.py`/`main.mpy` allowlist. Package
file writes require allow rules, with deny rules evaluated first and exact
paths or trailing-`/` directory prefixes supported.

Real HTTP validation used the actual `RuntimeACL`, `DeviceService`,
`DeviceSession`, handler and package preflight. It confirmed:

- session and capacity responses expose the semantic policy SHA256;
- allowed program status succeeds;
- program execute, serial read, input write, reset, flash read and program
  interrupt return `403 runtime_acl_denied` before console/QMP/flash I/O;
- serial-marker wait cannot bypass the serial-read permission;
- an invalid policy fails `serve.py` before the HTTP listener starts;
- SIGHUP publishes a valid replacement policy while an invalid replacement
  leaves the prior policy active;
- a denied package path is rejected before revision publication, while an
  allowed `main.py` package reaches the expected unavailable-console gate;
- denied operations produce policy-bound audit events;
- session snapshots and evidence ZIPs omit denied program detail, serial/runtime
  logs and virtual Flash content with explicit redaction receipts;
- unconfigured compatibility, wildcard/device selection, malformed policy,
  oversized file, symlink and unknown-device rejection are fail closed.

Machine evidence:
[`evidence-2026-10-29-runtime-acl.json`](../../../tests/firmware/evidence-2026-10-29-runtime-acl.json).

Reproduce from the repository root:

```bash
PYTHONPATH=platform/tools python3 \
  tests/firmware/runtime_acl/run_test.py \
  --out /tmp/runtime-acl-evidence.json
```

## Boundary

This is a management-plane policy for guest-facing operations owned by the
service. It does not prove firmware-authored filesystem ACLs, guest execution
of file permissions, arbitrary native-firmware sandboxing, QEMU guest
quiescence or physical hardware. Those remain `NOT RUN`.

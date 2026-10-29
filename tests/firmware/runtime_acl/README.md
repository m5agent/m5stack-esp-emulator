# Runtime ACL HTTP validation

This runner exercises the operator-owned Device Service runtime ACL without
starting a guest. It uses the real `RuntimeACL`, `DeviceService`,
`DeviceSession`, HTTP handler and immutable program package preflight.

Run from the repository root:

```bash
PYTHONPATH=platform/tools python3 \
  tests/firmware/runtime_acl/run_test.py \
  --out /tmp/runtime-acl-evidence.json
```

The result covers service-owned serial/input/reset/program/flash permissions
and program package path admission. It does not prove firmware-authored
filesystem ACLs, guest enforcement, QEMU sandboxing or physical hardware.

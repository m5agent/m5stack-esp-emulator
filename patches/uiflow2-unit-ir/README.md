# Optional IR callback lifetime patch

`0001-root-native-receive-callback.patch` applies only to a generated copy of
the pinned official `io_drivers/ir.py`:

- upstream: `m5stack/uiflow-micropython@3a86d8f611b3639cca755a933e01a5a829771ef1`;
- original SHA256:
  `b342ff962ffe119e0f1e4d072182a6ea1b251d9dd52dcea8980e386b04ce3896`;
- license: the original file's MIT SPDX notice is preserved.

The wrapper creates a nested `_ir_rx_callback` and passes it to the native
module. The native module holds that object in a C static `mp_obj_t` without
a registered GC root. The patch stores the same callable on the live wrapper
instance before native receiver construction, keeping it reachable from the
MicroPython object graph. It does not replace the callback, call it from the
host, change decoding, alter TX bytes, or modify QEMU/native module code.

The default runner preserves the original driver. Explicit opt-in is required:

```sh
python3 tests/units/run_io_cases.py --case ir --ir-callback-root-patch \
  --prepare-only --out-dir /tmp/m5-ir-callback-root-prepared
```

The runner verifies the exact original SHA, applies the patch with zero fuzz,
checks reverse applicability, records the patch/original/patched hashes, and
remounts the generated LittleFS image to compare the packaged Python bytes.
Runtime reports label this `custom-guest-ir-callback-root-patch`; its outcome
cannot be reported as a PASS of the original published wrapper. The probe
requires normal GC, explicitly collects after registration, and then requires
valid RX, malformed-leader rejection, NEC repeat and receiver rearming.

GC-disabled runs remain diagnostic evidence. Existing original-driver failure
reports are retained unchanged. Firmware images stay in ignored work storage.

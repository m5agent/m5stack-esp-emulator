# Core2 native VHCI BLE GATT bridge

Last reviewed: `2026-10-25`

This lane runs the stock Core2 UIFlow2 application image with its built-in
controller build and intercepts the firmware's real `esp_vhci_host_*` boundary.
It does not use the HCI-UART test build.

> Status: **legacy/diagnostic**. The canonical no-GDB path is
> `tests/uiflow2/core2_native_hci/` with Device Service profile
> `core2-native-hci`; `HCI-4` passed five independent leases. This GDB lane
> remains useful for root-cause comparison only.

The QEMU GDB bridge:

1. resolves the three bridge addresses from the matching ELF symbol table;
2. reads H2C packets at `API_vhci_host_send_packet`;
3. suppresses the incomplete in-guest controller path;
4. forwards the exact H4 stream to a Bumble controller;
5. injects Bumble C2H events through the callback registered with the firmware;
6. lets a second Bumble peer scan, connect, discover NUS, subscribe, write and
   validate the guest notification.

The symbol source defaults to `pinned`: `xtensa_elf_symbols.py` resolves
`API_vhci_host_send_packet`, `vhci_env_p` and `esp_cpu_wait_for_intr`, and the
runner passes them as `M5_NATIVE_VHCI_SEND_PC`, `M5_NATIVE_VHCI_ENV_PTR` and
`M5_NATIVE_VHCI_IDLE_PC`. The bridge prints
`NATIVE_VHCI_SYMBOL_FALLBACK` only if that contract is bypassed and GDB
expression lookup is used.

`--symbol-source gdb` remains a comparison path. It does not remove GDB from
guest control: breakpoints, callback invocation and the synthetic
`API_vhci_host_send_packet` return still run in the debugger. Removing that
control plane is why `core2-native-hci` is the new canonical path; this result
remains debugger-mediated.

Run:

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/core2_native_vhci/run_test.py \
  --attempts 3 \
  --symbol-source pinned \
  --out-dir /tmp/core2-native-vhci
```

The stock internal-controller path is exercised without rebuilding UIFlow2 for
UART HCI. The current bridge replaces controller execution at the VHCI boundary
with Bumble; it is not a bit-exact model of the Espressif Bluetooth baseband or
controller firmware. RF, pairing/security, coexistence, performance and
physical hardware remain out of scope.

Pinned-symbol evidence is recorded in
`evidence-2026-10-24-symbol-pinned.json` as five independent PASS attempts.
The evidence includes the ELF-derived addresses and per-attempt serial, peer
and bridge hashes.

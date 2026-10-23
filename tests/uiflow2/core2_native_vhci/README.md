# Core2 native VHCI BLE GATT bridge

This lane runs the stock Core2 UIFlow2 application image with its built-in
controller build and intercepts the firmware's real `esp_vhci_host_*` boundary.
It does not use the HCI-UART test build.

The QEMU GDB bridge:

1. reads H2C packets at `API_vhci_host_send_packet`;
2. suppresses the incomplete in-guest controller path;
3. forwards the exact H4 stream to a Bumble controller;
4. injects Bumble C2H events through the callback registered with the firmware;
5. lets a second Bumble peer scan, connect, discover NUS, subscribe, write and
   validate the guest notification.

Run:

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/core2_native_vhci/run_test.py \
  --attempts 3 \
  --out-dir /tmp/core2-native-vhci
```

The stock internal-controller path is exercised without rebuilding UIFlow2 for
UART HCI. The current bridge replaces controller execution at the VHCI boundary
with Bumble; it is not a bit-exact model of the Espressif Bluetooth baseband or
controller firmware. RF, pairing/security, coexistence, performance and
physical hardware remain out of scope.

# C6 Nesso PI4IOE controller preimage

This single C file is the exact controller postimage of the ordered
24-patch C6 recipe through `0022-c6-usb-serial-jtag-host-timing.patch`.
[Source provenance](source-provenance.json) records the upstream revision,
recipe commit, ordered patch hashes and controller hash.

The platform test applies 0023 to a temporary copy and uses the same
[actual-C controller harness](../../../../tests/firmware/esp32c6_nesso_pi4ioe_irq/README.md)
for both sides. ASan/UBSan are enabled. No network, runtime binary, ROM or
local cache is required.

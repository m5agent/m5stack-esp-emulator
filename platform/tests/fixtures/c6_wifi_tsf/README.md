# C6 TSF preimage

The C and header files are the exact postimages of the 19-patch native C6
recipe through `0017-c6-mwdt-pcr-clock.patch`, based on Espressif QEMU
`febae182e132e4055529be423a818225ebddaa3a`.

`test_c6_wifi_tsf_patch.py` extracts the actual MMIO/reset functions, stubs the
QEMU clock and object declarations, and executes both this preimage and patch
0018 with ASan/UBSan. It does not reproduce the controller algorithm in Python.
The before model must fail nine clock cases while preserving three existing
behaviors. The after model must pass all twelve. Guest controls and limits are
in `tests/firmware/esp32c6_tsf_identity/README.md`.

# StickS3 IR TX probe

Uses the official UIFlow2 `hardware.IR` wrapper and its StickS3 pin mapping
(`RX=42`, `TX=46`). The app sends one NEC frame with address `0x56` and
command `0xA3`.

Set `M5SW_RMT_TX_FILE` before QEMU. The captured file contains little-endian
`rmt_symbol_word_t` values read from the emulated RMT hardware memory.

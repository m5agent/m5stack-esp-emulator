# StickS3 IR RX probe

Initializes the official UIFlow2 `hardware.IR` NEC receiver on the StickS3
`RX=42` pin. QEMU injects `M5SW_RMT_RX_FILE` into RMT channel 4 hardware
memory and raises the real RX_END interrupt.

The expected callback values are address `0x56` and command `0xA3`.

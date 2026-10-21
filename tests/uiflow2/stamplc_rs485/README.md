# StamPLC RS485 probe

Uses the official UIFlow2 `hardware.PWR485` half-duplex API on the documented
StamPLC pins: UART2 TX/BOOT `G0`, RX `G39`, direction `G46`. QEMU attaches a
byte-level UART peer and requires the guest to write and read the same payload
through the real UART controller.

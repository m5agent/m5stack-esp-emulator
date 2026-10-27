# StamPLC CAN probe

Uses the official UIFlow2 `hardware.CAN` API on the documented StamPLC pins:
CAN_TX `G42` and CAN_RX `G43`. QEMU connects the ESP32-S3 TWAI controller to a
virtual CAN bus with an echo peer; the guest must transmit and receive the same
frame through the real SJA1000-compatible register path.

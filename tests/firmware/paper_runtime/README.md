# PaperS3 and PaperDIY factory firmware

`run_test.py` uses Device Service to run PaperS3 Factory V0.5 or the
PaperDIY V1.0 factory demo. It checks the device's native EPD output after
GT911 touch on PaperS3 or independent A/B press and release on PaperDIY.
It exports the evidence before stopping the session and releasing Flash.

See the [validation record](../../../docs/evidence/2026-11-09-paper-et047tc1/README.md)
for the QEMU build, firmware versions, PaperDIY NVS fixture, and replay commands.

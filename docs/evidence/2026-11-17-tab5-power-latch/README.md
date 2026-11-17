# Tab5 ST7123 standby latch and restart

Virtual-device validation, 2026-11-17. The unchanged Arduventure 1.0.0
upload was imported through Device Service and ran with native esp-emu 1.1.0,
the ST7123 board Part and 720×1280 DSI. No matching ELF was supplied.
[Full artifact and evidence hashes](summary.json)

A short power-icon tap and a three-second hold outside the icon left EN high.
A three-second hold at (672,53) drew the guest POWER OFF frame and generated an
HP I²C1 write of `0x99` to expander `0x44`, register `0x05`. The qualified
Part pulled EN low 688 ns after issuing its EN drive, on the emulator's
timeline. The native co-sim trace contains one asserted EN event and no
subsequent reset before the explicit restart. The baseline Part had register
readback and repeated power-off writes without a latch. [Prior hold evidence](../2026-11-17-tab5-st7123-hold/README.md)

The API reported the latch and disabled chip. The interrupted hold and a
subsequent tap both returned `tab5_guest_powered_off`. The captured POWER OFF
frame stayed available while UART remained unchanged over 2.4 wall seconds.
The evidence ZIP contains the recorded power state and last DSI frame.
Explicit reset recreated the board and the original title frame returned.
Original CarPlay independently passed its GT911 drag and confirmation dialog,
which was left unaccepted. Both sessions stopped with Flash released and zero
active worker leases.

## Concurrent DSI readback

The receiver batches bounded socket reads and skips unrelated GPIO broadcasts
and idle heartbeats. It still consumes the clock watermark for a pending
sparse diff. Device Service retains one PNG encoding for the exact immutable
frame it received. Reset clears that rendering before the next generation.

With four loopback clients requesting uncached PNGs after the title screen
and waiting 125 ms between requests, the original firmware passed the EN,
shutdown PNG, ZIP, and restart-title checks on both builds. The baseline
served 96 successful image reads and the candidate served 237 over their
respective runs. Neither emitted a native TCP drop warning at that pacing.
At 25 ms pacing, the candidate passed those checks with 946 successful image
reads in 13.101 seconds, and the runtime reported at least 4,194,304 advisory
messages dropped. The warning supplies one count for all message types on the
connection. An earlier 25 ms run
captured the shutdown PNG and power ZIP, then timed out waiting for the
restart title. Reliable readback under arbitrary host load remains open.
All these tests used the identical original upload and qualified runtime and
Part. [Bounded concurrency evidence](dsi-receiver-summary.json)

The latch is qualified for this ST7123 configuration. Other Tab5 profiles,
physical power rails and standby current, backlight power, and panel behavior
on a physical power button remain outside the result. No Burner submission
was performed.

Reproduce with the [Arduventure power runner](../../../tests/firmware/tab5_st7123/README.md).
For the recorded digital timing, capture native co-sim `BusRequest`,
`BusReply`, `EnDrive`, `EnLevel` and `ChipReset` on the isolated launcher.

[Board schematic, sheets 1 and 5](https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/1132/Tab5_Schematics_PDF.pdf)
· [PI4IOE5V6408 register definitions](https://www.diodes.com/datasheet/download/PI4IOE5V6408.pdf)
· [Tab5 reference BSP power request](https://github.com/m5stack/M5Tab5-UserDemo/blob/main/platforms/tab5/components/m5stack_tab5/m5stack_tab5.c)
· [esp-emu 1.1.0 EN wiring contract](https://github.com/espressif/esp-emulator/blob/v1.1.0/docs/guides/PARTS.md#wire-a-part-to-en-reset)

# UART RX reset replay seeds

The six C/header files are exact bytes from Espressif QEMU commit
`40edccac415693c5130f91c01d84176ae6008566`, identified individually in
`manifest.json`. Their original license notices are retained. These are source
seeds, not generated runtime evidence, firmware, ROM or binary fixtures.

`test_uart_rxfifo_reset_patch.py` applies the current tracked UART patch stack
to these seeds, then applies `0098` only to the positive control. It compiles
the actual parent UART read/write, RX/FIFO/timeout/IRQ functions, actual S3
register shim, actual QEMU Fifo8 implementation and the tracked SCS response
emitter. QOM registration, migration metadata and host timer/IRQ/character
backend plumbing are outside the tested algorithm boundary. No `.work` cache,
network access, guest, browser or installed QEMU is needed.

The input pulse corresponds to ESP32-S3 ESP-IDF 4.4.7
`components/hal/esp32s3/include/hal/uart_ll.h`:
`uart_ll_rxfifo_rst()` writes `hw->conf0.rxfifo_rst = 1`, followed by `0`.
`components/soc/esp32s3/include/soc/uart_reg.h` identifies that field as CONF0
bit 17. The fixed Arduino framework `3.20017.241212+sha.dcc1105b` bundles this
same path. The test models its MMIO pulse, not an IDF software-ring buffer.

The two negative controls must fail without `0098`: a six-byte SCS WRITE ACK
left in hardware FIFO survives the IDF pulse, and pending RX timeout/throttle
state remains after reset. Positive controls verify that the pulse clears only
RX state, retains TX data/framing/interrupt masks, and permits a fresh eight-byte
SCS ReadPos response through timeout IRQ and exact MMIO byte drain. An unrelated
CONF0 write and the generic/classic parent path retain their original behavior.

These controller cases do not prove that a particular browser `ReadPos=-1`
was caused by stale FIFO bytes. That needs a same-guest transaction trace with
the SDK error code, FIFO/driver-buffer timing and returned byte sequence.

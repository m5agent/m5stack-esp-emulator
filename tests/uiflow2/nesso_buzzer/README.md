# Arduino Nesso N1 buzzer probe

Diagnostic probe for the documented GPIO11 buzzer through the official
UIFlow2 `Speaker` API.

Current status: M5Unified detects the board, `Speaker.begin()` returns true
and starts the C6 I2S TX/GDMA descriptor path, but the DMA buffer capture is
still all zero. The buzzer remains `planned` in the peripheral catalog until
the C6 I2S interrupt/completion handshake produces a non-zero delta-sigma
stream.

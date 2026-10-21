# StackChan RGB probe

Uses the official M5IOE1/NeoPixel driver over I2C to configure 12 RGB LEDs.
The test reads the LED RAM back from the M5IOE1 model and requires all tested
pixels to contain red RGB565 `0xF800`.

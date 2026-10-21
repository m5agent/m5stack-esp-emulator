# Tab5 I2C diagnostic

This probe isolates the native ESP32-P4 `machine.I2C` controller from the
Tab5 display/board initialization. It compares `readfrom_mem()`, a register
write followed by a read, and a raw write-pointer/read sequence against the
same `esp-emu --i2c-dev` register device.

Use it to diagnose why a preloaded register is visible or not before changing
the actual peripheral model.

Verified result:

```text
TAB5_I2C_PROBE_ID_BEFORE 0x00 00c1802e00c1802e
TAB5_I2C_PROBE_ID_AFTER_WRITE 0x00 24c1802e00c1802e
TAB5_I2C_PROBE_AFTER_WRITE_02 0x02 a1a2a3c1802e
TAB5_I2C_PROBE_RAW_AFTER_PTR0 24c1a1a2a3c1802e
```

The P4 controller and generic register device can address register zero and
can store `CHIP_ID=0x24` when UIFlow2 writes it.  The boot-time board path has
already cleared the preloaded value before `main.py`; therefore Tab5 BMI270
needs a real state machine and reset/init semantics rather than another
preload value or a Python-side workaround.

# PaperMono SX1262 LoRa probe

This probe drives the native `lora.SX1262` driver against the PaperMono
SX1262 model:

- enables the PaperMono LoRa power/antenna path through M5PM1;
- configures frequency, modulation, packet, PA and TCXO parameters;
- writes `M5LORA` into the SX1262 TX FIFO and starts TX;
- switches to RX and reads the locally looped packet, RSSI and SNR.

The test-side SPI adapter keeps CS asserted while splitting transfers into
four-byte chunks. This avoids an unresolved MicroPython/IDF `>4`-byte
`spi_device_acquire_bus()` stall in the emulator; all bytes still traverse the
ESP32-S3 GP-SPI controller, GDMA path and SX1262 command/data state machine.

Expected UI:

```text
packet=b'M5LORA'
status=ok
```

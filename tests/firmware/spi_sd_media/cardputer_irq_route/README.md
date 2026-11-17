# Cardputer K132 GP-SPI interrupt routing

This ESP-IDF 5.5.4 guest sends a FIFO transfer through each controller.
It samples the Xtensa pending IRQ register with the two level-one ISRs
masked, acknowledges the other controller, then acknowledges the
controller that transferred data. The originating SPI RAW flag is also
read after the other controller is acknowledged.

Build for ESP32-S3 and create an 8 MiB merged Flash image.

```sh
idf.py -C tests/firmware/spi_sd_media/cardputer_irq_route -B "$GPSPI_IRQ_BUILD" build
cd "$GPSPI_IRQ_BUILD"
python -m esptool --chip esp32s3 merge_bin --fill-flash-size 8MB -o "$GPSPI_IRQ_FIRMWARE" @flash_args
```

Import the result on an isolated native Device Service for `cardputer`.
Each `GPSPI_IRQ` line must show `transfer=own`, `other_ack=own`,
`own_ack=00000000` and `raw=1`. The final
`STAGE_PROBE_DONE gpspi_irq_route pass=1` requires both host directions.
Collect the serial and evidence ZIP from that same session, then stop
it and release its lease. The tested [A/B receipt](summary.json) retains
the failing and passing interrupt observations and the scope of NC1020
and stock-firmware checks.

ESP-IDF assigns the [SPI2 and SPI3 interrupt sources](https://github.com/espressif/esp-idf/blob/v5.5.4/components/soc/esp32s3/spi_periph.c)
independently. This test covers the K132 virtual board and Xtensa CPU
interrupt delivery.

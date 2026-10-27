# PaperColor SPI microSD probe

Uses `machine.SDCard(slot=2, width=1)` with the documented PaperColor pins
`SCK=G15`, `MOSI=G13`, `MISO=G14`, `CS=G47`. QEMU backs the card with a raw
image via `M5SW_SPI_SD_IMAGE`.

# Cardputer-ADV SPI microSD probe

Uses `machine.SDCard(slot=3, width=1)` with the documented pins
`SCK=G40`, `MOSI=G14`, `MISO=G39`, `CS=G12`. QEMU's SD SPI protocol model is
backed by a raw image via `M5SW_SPI_SD_IMAGE`.

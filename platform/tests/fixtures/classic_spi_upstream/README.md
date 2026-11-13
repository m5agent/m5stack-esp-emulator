# Classic SPI source fixture

Complete unmodified `hw/ssi/esp32_spi.c` from Espressif QEMU commit
`40edccac415693c5130f91c01d84176ae6008566`, SHA-256 `c563518d0829bd656389629ea0cbd951ad5e89def13f4777e49dc6526386b797`.
Original BSD-licensed header is retained. The host regression replays the
maintained native patch chain before comparing chip-select/FIFO behavior;
no local runtime cache or network is needed. This fixture is not guest evidence.

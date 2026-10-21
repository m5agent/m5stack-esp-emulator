# PaperMono ST25R3916 NFC probe

Uses the official UIFlow2 `hardware.NFC` API and ST25R3916 I2C protocol at
address `0x50`. QEMU emulates command registers, FIFO status/data, ISO14443A
REQA/WUPA, anti-collision, SELECT and NTAG213 page read/write.

Expected tag:

- UID `DEADBEEF`;
- page 4 `M5N1`;
- page 8 can be written with `TEST` and read back.

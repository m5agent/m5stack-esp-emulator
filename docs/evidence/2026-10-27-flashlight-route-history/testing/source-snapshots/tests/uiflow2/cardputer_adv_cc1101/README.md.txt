# Cardputer-ADV CC1101 SPI probe

Exercises the CC1101 Sub-GHz Cap path on the Cardputer-ADV SPI2 bus:

- SCK `G40`
- MOSI `G14`
- MISO `G39`
- CC1101 CS `G5`
- GDO0 `G15`

The probe configures the official `cap.CC1101Cap`, sends `M5CC1101`, and
receives the deterministic chip FIFO loopback. The same bus also carries
microSD (`CS G12`) and ST25R3916 NFC (`CS G6`).

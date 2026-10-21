# Cardputer-ADV NFCCap SPI probe

Exercises the ST25R3916 SPI transport on the Cardputer-ADV SPI2 bus:

- SCK `G40`
- MOSI `G14`
- MISO `G39`
- NFC CS `G6`
- IRQ `G4`

The probe detects the deterministic `DEADBEEF` Type 2 tag, reads page 4,
writes page 8 with `TEST`, and reads the page back. The microSD model remains
attached on the same bus with CS `G12`.

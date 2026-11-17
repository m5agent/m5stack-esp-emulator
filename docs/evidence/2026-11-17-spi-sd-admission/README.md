# 2026-11-17 SPI SD in Device Service

The old session parser rejected Cardputer and PaperS3 despite existing native
SPI attachments. The candidate admits those mounts and keeps Basic V2.7's
planned slot unavailable. The separate network diagnostic runtime rejects
SD fixtures because it does not use the QEMU guest mount path.

Five native sessions exercised the real ESP-IDF SDSPI and FAT VFS drivers.
Cardputer, Cardputer-ADV and PaperS3 listed a seeded FAT32 directory and read its
file before writing and remounting the mounted card. A fresh Cardputer guest
found the prior write before running its own write. Its input was the stopped
first session's SD disk uploaded as a new artifact. A no-media Cardputer control
reported `ESP_ERR_TIMEOUT`. The independent FAT oracle confirmed the file bytes,
and upload artifacts retained their original hashes. Each ZIP passed CRC
verification before stop, and all guests exited.

The harness first stopped on a local import error and next received a
400 for a trace switch outside the session allowlist. Neither attempt started
a guest. The recorded run used the isolated worker's trace configuration.

[Run summary](summary.json) · [Guest source and procedure](../../../tests/firmware/spi_sd_media/README.md)

PaperDIY keeps its existing scope until GPIO48 card detect follows actual media.
The internal filesystem overlay and reviewer fixture intake are separate paths.
Physical hardware and browser WASM were not run.

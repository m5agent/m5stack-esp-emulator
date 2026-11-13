# ESP32-C6 Nesso display address rotation

This ESP-IDF 5.5.4 probe writes the real SPI2 controller, with the Nesso display
CS/DC pins and the radio deselected. It sends DCS `MADCTL`, `CASET`, `RASET` and
RGB565 pixel data. Each of the four rotations holds a four-color quadrant image
for four seconds after `C6_PANEL_ROTATION_<n>_READY`.

The panel is physically 135 by 240 pixels, cut from a 240 by 320 GRAM at offset
52,40. Guest landscape addresses can extend to column 279; they must be swapped
and mirrored by MADCTL before the physical crop. Applying only the fixed crop
loses image data. The controller mapping follows the same DCS address transform
as the generic SPI panel model. The window/rotation table is independently
consistent with M5GFX's fixed-source [Panel_LCD rotation code](https://github.com/m5stack/M5GFX/blob/9bcedf4e19d4cab7a0793de0598ae5390b4689fe/src/lgfx/v1/panel/Panel_LCD.cpp#L118).
That source is a protocol reference, not a recovered build manifest for the
original community BIN.

| Rotation | MADCTL | Window origin | Logical size | Physical TL,TR,BL,BR |
| --- | --- | --- | --- | --- |
| 0 | `08` | 52,40 | 135x240 | red, green, blue, white |
| 1 | `68` | 40,53 | 240x135 | blue, red, white, green |
| 2 | `c8` | 53,40 | 135x240 | white, blue, green, red |
| 3 | `a8` | 40,52 | 240x135 | green, white, red, blue |

Build with ESP-IDF 5.5.4 activated:

```sh
idf.py -C tests/firmware/esp32c6_panel_madctl -B .work/c6-panel build
python -m esptool --chip esp32c6 merge_bin -o .work/c6-panel/merged.bin \
  0x0 .work/c6-panel/bootloader/bootloader.bin \
  0x8000 .work/c6-panel/partition_table/partition-table.bin \
  0x10000 .work/c6-panel/c6_panel_madctl_probe.bin
```

Upload the same merged BIN into dedicated Device Service `nesso-n1` sessions.
For each serial marker, capture `frame.png?orient=panel` and
`frame.png?orient=display`. Check physical corners against the table and logical
corners against red, green, blue, white. `orient=display` uses controller QOM
metadata, not image heuristics. Old runtimes without metadata must retain the
unknown-orientation response. Request the session evidence ZIP before stopping
with `purge=0`.

The firmware declares input coordinates in physical glass space as before;
rotation does not change the touch data plane. Original application validation
and touch/button interaction are recorded separately. Physical optics, RF and
hardware timing are NOT RUN.

The additional `C6_PANEL_DMA_READY` phase clears the image and sends the same
landscape quadrants using 352-byte SPI2/GDMA blocks. The prior model interpreted
`SPI_MS_DLEN[17:0]` through SPI1's 10-bit field, reducing 352 bytes to 96 bytes.
This phase detects the resulting missing rows independently from rotation.
Coverage here is FIFO traffic up to 64 bytes and single-descriptor DMA blocks;
large chained or split DMA transactions remain outside this fixture.

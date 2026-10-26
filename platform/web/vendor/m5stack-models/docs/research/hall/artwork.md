# U084 printed artwork

Both observed printed faces have matching high-resolution PNGs in this batch. They were redrawn from exact Unit Hall official photos using text and shapes, with no photographic crop, screenshot, blurred enlargement or private vector distributed.

| Face | File | Pixels | Registered size / position (mm) |
| --- | --- | --- | --- |
| Front directional illustration and HALL footer | `reference-redraw-front.png` | 2400 × 1680 | 20 × 14 at (0, 7, 3.8) |
| Back HALL, A3144E, SIGNAL and pin colors | `reference-redraw-back.png` | 1944 × 1464 | 16.2 × 12.2 at (0, 7, −3.8) |

The front preserves the TOP/BOTTOM arrow, the printed S/N magnet illustration, HALL text and blue footer. The rear preserves HALL/A3144E, orange SIGNAL tab and arrow, and the observed I / blank gray / 5V / GND blocks. The blank block remains blank rather than inventing a printed NC legend. These are printed marks; they implement no sensing logic or magnetic response.

`printedArtwork` projects only onto existing native shell surface triangles. Holes, cutouts, reliefs and molded marks remain physical geometry. `artwork:false` removes all printed panels while keeping every physical position/normal/index buffer and transform unchanged. Color, typography and registration are reference estimates, not production-print measurements. M5Stack artwork, marks and printed designs retain their respective rights. See [artwork.json](./artwork.json) for exact source URLs, hashes and output registration.

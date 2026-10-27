# U216 NFC artwork

Two exact supplied body-label vector panels were rasterized directly to final high-resolution PNG. The front contains the blue NFC symbol and title; the rear contains NFC, ST25R3916, PORT.A.I2C and SCL/SDA/5V/GND. The separate bag-name label was excluded. The supplied body photograph and current official U216 photographs agree on this pair.

The converter exports compound glyph paths with `evenodd`; their winding semantics were restored to `nonzero` before rasterization. Original glyph/shape contours, fills and panel placement within each label are preserved. This processing is explicitly classified `source-vector-raster`, not an unmodified converter export. No preview upscaling, photo crop, substituted font or invented microtext was used.

| Panel | PNG pixels | Physical print area | Body position | Surface |
| --- | --- | --- | --- | --- |
| front | 2200 × 3443 | 17.7 × 27.7 mm | [0, 6.5, 3.8] mm | native +Z recessed face |
| back | 2000 × 3509 | 15.9 × 27.9 mm | [0, 6.5, −3.8] mm | native −Z recessed face |

Registration follows the original native recesses and official body photos; no production-print fit is claimed. Each PNG projects onto the existing explicit physical shell using `printedArtwork`, retaining native holes and walls. `artwork:false` changes only print meshes.

Only the two final ordinary PNG files and safe provenance are distributed. The original vectors, spreadsheet, private links/names/mapping, photos, export scripts, converted SVG and intermediate rasters remain private. Printed designs, names and marks retain their respective rights. PNG decoding and an artwork contact sheet were inspected; exhaustive browser pixel re-review was deferred.

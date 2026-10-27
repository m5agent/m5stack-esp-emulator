# Synth U178 printed labels

Both labels are manually reconstructed as new high-resolution PNG graphics from the exact U178 official product photographs. No photograph pixels, photographic crops, vector originals, private table, mappings or generators are distributed. M5Stack product marks and original label designs retain their respective rights; the raster reconstructions are not official production artwork.

| Face | Exact official reference | Reference SHA-256 | Final raster | Size and registration in model axes |
| --- | --- | --- | --- | --- |
| Front | [https://static-cdn.m5stack.com/resource/docs/products/unit/Unit-Synth/img-fe511f44-85db-4d2c-aabb-189ba2d24de7.webp](https://static-cdn.m5stack.com/resource/docs/products/unit/Unit-Synth/img-fe511f44-85db-4d2c-aabb-189ba2d24de7.webp) | `2662aaa1f4acce632efd77079b256b486d733005ecf6f868edc5efa38bdcf64a` | `src/units/synth/reference-redraw-front.png` (1008 × 4608) | 6.3 × 28.8 mm; center [0, 9, 8.012], front |
| Back | [https://static-cdn.m5stack.com/resource/docs/products/unit/Unit-Synth/img-2aa61223-8769-4734-be2d-578c18ddb2b6.webp](https://static-cdn.m5stack.com/resource/docs/products/unit/Unit-Synth/img-2aa61223-8769-4734-be2d-578c18ddb2b6.webp) | `31fc4ac29f909372b0663432b8c293b089f2e88e67038c6813e140a53af67cbb` | `src/units/synth/reference-redraw-back.png` (2624 × 4640) | 16.4 × 29 mm; center [0, 7.1, -7.8], back |

Retrieved 2026-10-26. Sizes, colours, glyph geometry and alignment are reconstructed from photographs and native shell landmarks; they are not production-print measurements. The front label repeats the visible musical note, arrows, vertical SYNTH title and MIDI legend. The rear label repeats the visible SYNTH title, speaker symbol and 8Ω@1W annotation, NS4150B/SAM2695/LDO block diagram, PORT.C.UART band and NC/IN/5V/GND pin legends.

The real narrow front adhesive film visibly spans the source shell's central perforations. `printedFilm` reproduces that physical film; the original grille openings and complete fixed speaker remain underneath and are visible with `artwork:false`. `printedArtwork` projects the rear label onto the native recessed back surface, retaining the shell's existing geometry. Both panels use `artworkKind: reference-redraw`. No artwork is used to replace missing assembly geometry.

Necessary local smoke confirms both registered panels have finite nonempty geometry, `artwork:false` removes both, all physical mesh buffers/transforms remain identical, and mounting bores/Grove and speaker backing remain intact. Browser pixel inspection has not been performed under the user's current request to avoid lengthy re-review.

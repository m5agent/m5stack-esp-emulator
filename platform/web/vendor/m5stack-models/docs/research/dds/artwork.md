# Unit DDS U105 artwork

Two newly drawn high-resolution PNGs reproduce the exact U105 labels. The front (1920 × 4356 px) shows Direct Digital Synthesis and the four printed curves labelled SINE, SQUARE, TRIANGLE and SAWTOOTH. The rear (1944 × 4344 px) preserves the observed block diagram, IC names, 25MHz text and PORT.A.I2C colour key. Text and line primitives were drawn at high resolution; product photographs were not cropped or enlarged into textures.

The front registration follows the native 16 × 36.3 mm recess; the rear follows 16.2 × 36.2 mm. Both are projected onto the retained physical shell. No sheet covers a port or a mounting bore. Disabling artwork with `new Model({ artwork:false })` or `new GroveModule({ artwork:false })` leaves physical position/normal/index buffers and world transforms unchanged. Options apply per instance.

Typeface, hue, curve shape and diagram layout are reconstructed. The curves are fixed printed graphics. The observed rear 25MHz print is preserved despite a product specification stating10MHz reference; neither label nor model asserts an actual runtime clock. See the source note in [modeling.md](modeling.md).

Final ordinary PNGs may be distributed according to the project image policy. M5Stack branding, industrial artwork and trademarks remain their owners' property. Raw photographs, original vectors, private tables and generators are excluded. [artwork.json](artwork.json) records hashes, physical placement and public photographic references.

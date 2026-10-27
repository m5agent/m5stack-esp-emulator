# Unit MIDI U187 label reconstruction

Two high-resolution `reference-redraw` PNGs reproduce the same-model official front and back labels: front 4200 × 2997 px; back 4200 × 3405 px. The front carries the cyan MIDI title, SAM2695, AUDIO/3.5MM and IN/OUT markers, and the observed Bypass/Separate and TXD/RXD wording. The back carries the DIN five-contact numbering, TRS Tip/Ring/Sleeve illustration, UART colour key and printed block diagram. These are newly drawn text and shapes; product photos were not cropped into texture maps.

The official photos are reference material, not original vector artwork. Typography, colour, line shape and physical label registration remain reconstructed. The original observed routing text is retained even where the product description and schematic use different signal perspectives; the model does not implement that diagram as routing logic. No unreadable serial or QR code is invented.

`printedArtwork` projects each final PNG onto its explicit native shell, preserving apertures, seams and moving controls. `new Model({ artwork:false })` and `new GroveModule({ artwork:false })` omit the printing while keeping physical attributes, indices and world transforms unchanged. Options are per instance.

The final ordinary PNGs may be distributed under the project's image rights policy. M5Stack branding and industrial artwork remain their owners' property. Original source files and generation assets are not distributed. See [artwork.json](artwork.json) for exact PNG hashes, physical registration and public reference provenance.

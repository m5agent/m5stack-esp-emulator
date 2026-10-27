# Unit ASR U194 labels

Both final ordinary PNGs are newly drawn from exact official U194 photos. No photographic pixels, crops, private table, mapping, source vectors or generator are distributed. M5Stack marks and original label designs retain their rights; these are reconstructed reference rasters, not production artwork.

| Face | Exact official source | Final PNG | Registration |
| --- | --- | --- | --- |
| Front | [U194 front](https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/635/U194_02.webp) | `reference-redraw-front.png`, 756 × 3456 | 6.3 × 28.8 mm, [0, 9, 8.012], front physical adhesive film |
| Back | [U194 rear](https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/635/U914_07.webp) | `reference-redraw-back.png`, 1968 × 3480 | 16.4 × 29 mm, [0, 7.1, -7.8], projected onto native rear shell |

The official gallery has several files named U914; its product page and displayed physical device explicitly identify Unit ASR U194. Module ASR M147 artwork was excluded. Reference hashes and final PNG hashes are in `artwork.json`.

The front repeats the actual SPK symbol, green vertical ASR mark and MIC symbol. The rear repeats ASR, the blue bulb/3.3V print, SPK 8Ω@1W, CI-03T block, PB5/PB6, MIC, diode/5V, PORT.C.UART and TXD/RXD/5V/GND blocks. **The body specification says 8Ω@0.8W, while the official physical rear label prints 8Ω@1W.** The artwork faithfully retains 1W; it is not an electrical-rating decision. The printed blue bulb is not a visible blue LED.

The narrow real front adhesive film spans native central grille holes, as in the exact photo. The fixed physical speaker remains behind the full original grille and is visible with `artwork:false`. Rear artwork follows the native shell surface. Both use `artworkKind: reference-redraw`; the necessary smoke checks finite registration, two panels and identical physical buffers/transforms with artwork disabled. Colors, lettering, dimensions and alignment are reconstructed from photos. No exhaustive browser pixel review was performed.

# Unit ByteSwitch U191 labels

Two high-resolution PNG labels are fresh code-drawn reconstructions of the exact official product photographs. No photograph pixels/crops, supplied table, mapping, vector source or generator is distributed. Sources, image hashes, raster hashes, dimensions and registration are in `artwork.json`.

- Front: 6384 × 792 PNG, 53.2 × 6.6 mm, fixed native front-shell recess centered at [-7.05, 0, 5.85], rotated −90°.
- Back: 2496 × 6480 PNG, 20.8 × 54 mm, fixed native rear-shell recess centered at [0, 0, -5.85].

The front repeats the product title and original 0–7 channel legends. Printed 0 is at the bottom CH0 position, corresponding to API control 1; printed 7 is at top CH7, corresponding to API control 8. The rear repeats the visible printed channel/GPIO table, STM32G031 block, connector pin colours, RGB package symbols and LDO/PORT.A.I2C annotation. These are static printed graphics, with no firmware or electrical effect.

Both labels use `printedArtwork` with `artworkKind: reference-redraw` and project onto their explicit native fixed-shell meshes. No film spans a Grove mouth, lightpipe, mounting hole or moving cap/lever. `artwork:false` disables both. The original non-art mesh buffers, normals, indices, materials and world transforms match the saved before-change implementation exactly; original component state and cap/lever behavior are unchanged. Four-wire Grove attachment, pose and detach smoke also passed. See `sticker-smoke.json`.

The matching official front reference is [https://m5stack.oss-cn-shenzhen.aliyuncs.com/resource/docs/products/unit/Unit%20ByteSwitch/6.webp](https://m5stack.oss-cn-shenzhen.aliyuncs.com/resource/docs/products/unit/Unit%20ByteSwitch/6.webp); the back reference is [https://m5stack.oss-cn-shenzhen.aliyuncs.com/resource/docs/products/unit/Unit%20ByteSwitch/5.webp](https://m5stack.oss-cn-shenzhen.aliyuncs.com/resource/docs/products/unit/Unit%20ByteSwitch/5.webp). Retrieved 2026-10-26. Colours, typography, layout and surface registration are estimated from these references and native recesses, not production-print measurements. Browser pixel inspection was deferred under the user's request to avoid lengthy re-review. Stage remains modeled. Product marks and original label designs retain their respective rights.

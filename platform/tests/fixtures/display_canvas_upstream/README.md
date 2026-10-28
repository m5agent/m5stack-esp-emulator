# Pinned UIFlow2 Canvas constructor

`gfx_new_canvas.cpp` is the exact `gfx_newCanvas` function from
`m5stack/components/M5Unified/mpy_m5gfx.cpp` in UIFlow2 commit
`3a86d8f611b3639cca755a933e01a5a829771ef1` (MIT, M5Stack 2024).
The companion patch metadata binds the extracted function and complete
translation unit by SHA256. Tests compile this exact function before and after
patching against controlled allocation outcomes; they do not model the SDK
allocator or claim hardware validation.

# Cached display binding audit

No production files, firmware or QEMU changed. No guest run. UIFlow source below is the existing 2.5.3 cache. It is byte-identical to parent-fetched fixed 3a86 binding: SHA256 b13f252dbfd05eaa9135169acb13c65766af7529973debdc45690e4e9ae853f7. Identity receipt: `binding-identity.json`.

## Strongest cause: boxed length used as integer

Confirmed in byte-identical fixed 3a86 binding, not just an older cache.

- `mpy_m5gfx.cpp:1028` tests `(size_t)mp_obj_len(img) < 128`; drawPng repeats it at 944.
- MicroPython fixed 78ff170d `py/obj.c:538-548` returns boxed `mp_obj_t`; `py/obj.h:84-90` encodes repr A small integers as `(n << 1) | 1`; `ports/esp32/mpconfigport.h:18` chooses repr A.
- For ordinary ASCII paths the effective maximum is 63 characters: 63 -> 127 < 128, 64 -> 129 >= 128. Paths at least 64 characters are therefore treated as image bytes.
- `py/objstr.c:2062-2068` supports READ buffer for str. `drawImage` tests only the first two bytes (1067/1074/1081); an ordinary absolute path begins with `/`, matches no image signature, and reaches unconditional `None` at 1090 without opening the file. This explains silent non-rendering without implicating PNG data or filesystem.
- `drawPng(long_path)` passes the path text as encoded image bytes and likewise ignores decoder failure at 963.
- Shorten cwd-relative path to <=63 ASCII characters, or pass actual image bytes, for a targeted guest experiment. At 63/64 chars preserve identical file contents and drawing coordinates. Do not patch firmware to conduct the experiment.

## Independent silent file-failure path

- `drawImage` file branch 1028-1061 chooses extension from lowercased last four bytes, dispatches PNG to `drawPngFile(LFS2Wrapper*, path)` at 1053-1059, and discards its bool.
- `drawPng` file branch 944-952 bypasses extension dispatch but uses the same LFS2 wrapper.
- M5GFX fixed 9bcedf4e `LGFXBase.hpp:936-947` initializes false, preRead, calls `open(path)`, invokes the decoder only on open success, closes/postRead and returns bool. An open false result produces no drawing.
- The bytes overload (`LGFXBase.hpp:926-930`) uses `PointerWrapper.set(data,len)` and calls the same PNG decoder. It is not a separate or len=0 decoder. UIFlow passes `bufinfo.len` at 1083 / 957.
- `LGFXBase.cpp:3425-3437` returns false on PNG allocation/prepare failure; 3472-3481 returns false on decomp error. Binding discards all these booleans and unconditionally returns None.
- PNG begin clipping can return true with no pixels (3440-3452, `image_decoder_t.begin` 2846-2847), but same coords with bytes success narrows that away.

## Missing cached evidence and aliases

- `mpy_m5gfx.cpp:34` includes `mpy_m5lfs2.txt`, but that file is absent from this exact cache. Cannot conclude its mount-prefix handling from cached sources.
- `m5unified_gfx.c:72-75,144-147` registers separate drawPng/drawImage methods; drawImage is a dispatcher, not an alias.
- `mpy_m5unified.cpp:100,670-671` binds gfx object to `M5.Display`. The module table exposing exact M5.Lcd/Display alias names is not cached; no claim about those aliases from this cache alone.

## Additional source hazards, outside current diagnosis

- drawImage uses strlen(path)-4 without a short-path guard (1032-1035).
- bytes image signature accesses [0],[1] without a bufinfo.len>=2 guard (1065-1081).
- These are pre-existing upstream bounds issues; do not send empty/malformed inputs to guest for the present test.

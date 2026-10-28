# Pinned LVGL cache-entry regression source

`lv_cache_entry.c` is unmodified LVGL source from commit
`9c043167685fc08fbcd30ddf2c285ea1089be82d`, file `src/misc/cache/lv_cache_entry.c`:
https://github.com/lvgl/lvgl/blob/9c043167685fc08fbcd30ddf2c285ea1089be82d/src/misc/cache/lv_cache_entry.c

SHA256: `b936460d587d5aaa35876a8f9cc11ee5d2b4313d85e25be8bb8eb9af717f3cba`.
It is the submodule pinned by UIFlow2 commit
`3a86d8f611b3639cca755a933e01a5a829771ef1`.
The matching upstream MIT license is retained as `LICENCE.txt`.

`test_lvgl_cache_entry_patch.py` verifies these bytes, applies the exact reviewable
patch, verifies the candidate hash, then compiles each complete source with only
its include lines replaced by allocator/assert/logging/opaque-cache shims.
All production functions and the private metadata layout execute unchanged.
Host payload sizes are aligned to 16 bytes; the guest probe separately tests
the actual ESP32 ABI. No firmware, build output, or execution trace is stored here.

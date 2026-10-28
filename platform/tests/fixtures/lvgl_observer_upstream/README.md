# Pinned LVGL observer regression source

`lv_observer.c` is unchanged LVGL source from commit
`9c043167685fc08fbcd30ddf2c285ea1089be82d`:
https://github.com/lvgl/lvgl/blob/9c043167685fc08fbcd30ddf2c285ea1089be82d/src/others/observer/lv_observer.c

SHA256: `d496b0835ec9fe60b9b197c3b9b553b784673fa0bfabff5ee7cd78600d3a9627`.
UIFlow2 commit `3a86d8f611b3639cca755a933e01a5a829771ef1` pins this submodule.
The matching MIT license is retained as `LICENCE.txt`.

The regression applies the exact reviewable patch and compiles the unchanged
observer/object cleanup functions with linked-list and event-list transport
shims. It checks exact subscription membership, subject ownership, explicit
removal and deletion callback behavior. Visible native SDK validation is a
separate evidence layer.

# ESP32-S3 TIMG 回放种子

这些文件是 Espressif QEMU commit
`40edccac415693c5130f91c01d84176ae6008566` 的精确上游文本，保留原 GPL
许可与版权。它们只用于无需本机 `.work`、网络或固件的 C 逻辑回归。

| 文件 | 上游路径 | SHA256 |
| --- | --- | --- |
| `esp_timg.c` | `hw/timer/esp_timg.c` | `7003cdc57bf17a80615106bede8291241d6c2b164d46d2836ae20fd76d26e2b0` |
| `esp_timg.h` | `include/hw/timer/esp_timg.h` | `8d415c04fac0be34278de2bd1fcb97f7f5804f9c00465a8ec1764ffbb353df41` |
| `esp32s3_timg.c` | `hw/timer/esp32s3_timg.c` | `e451781d4994a6b4b98dee479d98f0b0363657815d7a4af7453463b85ef9df05` |

`test_s3_watchdog_patch.py` 应用仓库补丁后提取真实 watchdog 配置、计时、
IRQ 和 feed 函数；只替换宿主虚拟时钟/QOM/IRQ 接线。此回归不是 guest
启动或物理看门狗验证，后两者必须有独立证据。

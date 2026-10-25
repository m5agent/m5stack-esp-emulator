# 设备档案矩阵

一页理解代码阅读顺序、成熟度和下一步，见
[`docs/engineering-handoff.md`](../docs/engineering-handoff.md)。

项目级能力和最新验证快照见
[`docs/project-status.md`](../docs/project-status.md)；本页只描述设备登记与
运行时分类。

| 分组 | 型号 | SoC | 显示 | UIFlow2 | m5ui | 运行时 |
| --- | --- | --- | --- | --- | --- | --- |
| ESP32-S3 | StickS3 | ESP32-S3 | 135×240 | 支持 | 否 | reference-ready |
| ESP32-S3 | CoreS3 | ESP32-S3 | 320×240 触摸 | 支持 | 是 | reference-ready |
| ESP32-S3 | StopWatch | ESP32-S3R8 | 466×466 圆屏触摸 | 支持 | 是 | reference-ready |
| ESP32-S3 | Cardputer-ADV | ESP32-S3FN8 | 240×135 + 56 键 | 支持 | 否 | reference-ready |
| ESP32-S3 | PaperMono | ESP32-S3R8 | 480×800 单色 EPD 触摸 | 支持 | 否 | reference-ready |
| ESP32-S3 | PaperColor | ESP32-S3R8 | 400×600 彩色 EPD | 支持 | 否 | reference-ready |
| ESP32-S3 | StackChan | ESP32-S3 | 320×240 触摸 + 舵机 | 支持 | 是 | reference-ready |
| ESP32-S3 | AtomS3R | ESP32-S3 | 128×128 | 支持 | 否 | reference-ready |
| ESP32-S3 | StamPLC | ESP32-S3FN8 | 135×240 | 支持 | 否 | reference-ready |
| ESP32-C6 | NanoC6 | ESP32-C6FH4 | 无屏 | 支持 | 否 | headless-ready |
| ESP32-C6 | Arduino Nesso N1 | ESP32-C6 | 135×240 触摸 | 支持 | 否 | reference-ready |
| ESP32-P4 | Tab5 | ESP32-P4 + C6 | 1280×720 触摸 | 支持 | 是 | reference-ready（外设 partial） |
| ESP32 LX6 | Core2 | ESP32-D0WDQ6-V3 | 320×240 触摸 | 支持 | 是 | reference-ready |
| Linux ARM64 | CardputerZero | RP3A0 / BCM2837 | 320×170 + 46 键 | 不支持 | 否 | backend-required |

`catalog.source.json` 是设备档案的权威源；运行 `python3 platform/tools/generate_catalog.py` 重新生成目录和每个设备的 JSON/README。

> `reference-ready` 当前表示显示和输入重绘闭环；`headless-ready` 表示无屏
> 设备的固件、串口、板级外设和自动化数据面闭环。IMU、摄像头、音频等外设 API
> 的完整度以 [`docs/uiflow2-peripheral-test-matrix.md`](../docs/uiflow2-peripheral-test-matrix.md)
> 为准。
>
> `backend-required` 是固件族分类，表示设备使用独立架构后端，不表示后端还没有
> 实现。CardputerZero 的实际完成度仍是 `PARTIAL`，具体边界见
> [`docs/project-status.md`](../docs/project-status.md)。

## 统一虚拟主机回归

运行全部 ESP32 虚拟主机：

```bash
python3 tests/uiflow2/run_device_matrix.py \
  --out-dir /tmp/m5-uiflow2-device-matrix
```

单独运行一个型号：

```bash
python3 tests/uiflow2/run_device_matrix.py --device nesso-n1
```

矩阵会为每个有屏设备检查目标分辨率首帧、输入后的画面变化，并输出规范
`before.png`/`after.png`。ESP32-S3/C6/P4 先通过 `esp-emu` + `esptool`
执行 `write-flash`，Core2 通过 QEMU ESP32 ROM + `esptool --no-stub`
写入，写完均逐字节校验完整虚拟 flash。NanoC6 无显示屏，检查
USB-Serial-JTAG、RGB、IR、WiFi 和 BLE 标记，并以 `headless-ready` 表示；
该 ESP32 矩阵中的其余有屏设备均已进入 `reference-ready`。Tab5 的运行时已
进入 `reference-ready`，但外设整体仍是 `partial`；CardputerZero 仍按独立
Linux 后端单独验收。

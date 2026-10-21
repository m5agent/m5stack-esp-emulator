# UIFlow2 虚拟烧录与 UI 回归

设备参数在 `device_matrix.json` 中集中维护。统一流程：

1. 生成带测试 `boot.py`/`main.py` 的 merged flash；
2. ESP32-S3/C6/P4 通过 `esp-emu`、Core2 通过 QEMU ESP32 ROM 下载模式执行真实 `esptool write-flash`；
3. 将写后的虚拟 flash 与期望镜像逐字节校验；
4. QEMU 从同一份虚拟 flash 启动；
5. 校验目标分辨率首帧、非空画面、输入后像素变化；
6. 输出规范 `before.png`、`after.png`、串口和命令日志。

全量回归：

```bash
python3 tests/uiflow2/run_device_matrix.py \
  --out-dir /tmp/m5-uiflow2-device-matrix
```

单设备：

```bash
python3 tests/uiflow2/run_device_matrix.py --device nesso-n1
python3 tests/uiflow2/run_device_matrix.py --device core2
python3 tests/uiflow2/run_device_matrix.py --device tab5
```

外设 API 探测：

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/run_peripheral_matrix.py \
  --out-dir /tmp/m5-uiflow2-peripheral-matrix
```

覆盖 StickS3 的 IMU、A/B/P 按键和电源，以及 CoreS3 的 IMU、触摸、PWR、
电源、RTC 和摄像头初始化/取帧。结果和边界见
[`docs/uiflow2-peripheral-test-matrix.md`](../../docs/uiflow2-peripheral-test-matrix.md)。

Tab5 需要先构建仿真固件和 16 MiB merged image：

```bash
export UIFLOW_MICROPYTHON_DIR=/path/to/uiflow-micropython
python3 tests/uiflow2/build_tab5_emulator.py \
  --uiflow-repo "$UIFLOW_MICROPYTHON_DIR" \
  --clean
```

输出位于 `.work/uiflow2-tab5/`，包括 `micropython.elf` 和
`tab5-emulator-merged.bin`。Tab5 构建使用原生 M5GFX/UIFlow2 绘制路径，
仿真构建暂不启用 LVGL Python 绑定。

只生成可启动虚拟 flash：

```bash
python3 tests/uiflow2/flash_device.py \
  --device sticks3 \
  --firmware platform/.cache/firmware/sticks3/uiflow2.bin \
  --out-dir /tmp/m5-flash-sticks3
```

传输说明：

- `esp-emu-esptool`：ESP32-S3/C6/P4，真实 esptool `write-flash`，写入后逐字节校验；
- `qemu-esptool`：Core2，通过 QEMU ESP32 ROM UART 下载模式和 `esptool --no-stub` 写入，再逐字节校验；
- Tab5：`esp-emu` P4 下载模式的地址空间限制在 8 MiB，因此仿真专用分区表把
  应用、sys、vfs 和 storage 全部放在 8 MiB 以下；生产分区布局不变。写后的
  16 MiB 虚拟 Flash 与期望镜像逐字节一致后，再从同一份 Flash 启动。
- CardputerZero：Linux ARM64，不是 ESP32/UIFlow2 固件目标，保持独立后端。

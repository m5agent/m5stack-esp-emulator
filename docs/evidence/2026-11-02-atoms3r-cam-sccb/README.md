# AtomS3R-CAM（C126-CAM）相机数据面闭环

日期：`2026-11-02`。范围：虚拟设备（QEMU 原生 `m5atoms3rcam`）。物理光学/电气
`NOT RUN`。配套补丁：`patches/qemu-m5stack-peripherals/0115-atoms3r-cam-sccb.patch`
（基于 `0112`，QEMU 基线 `6961d82`）。

## 结果

官方 UIFlow2 v2.5.4 AtomS3R-CAM 固件（`1897200000000003117`，SHA-256
`1b29cc3d838834b3a4713130010815f952cff58619001c76183dd0b0a588f2c1`）在同一
guest 内跑通相机路径：

```
CAM_BOARD 144
CAM_I2C_SCAN ['0x8', '0x10', '0x18', '0x21', '0x30', '0x43', '0x68']
CAM_PID 9b00
CAM_INIT_RESULT True
CAM_CAPTURE_BYTES 153600
CAM_FRAME_FIRST64 f7bef7be...f7be
CAM_FRAME_DIGEST fnv1a 42521dc5
CAM_FRAME_SUM 24725536
CAM_STATUS ok
```

- `camera.init()`（模块默认 QVGA）返回真；
- `camera.capture()` 返回 153600 字节 = 320x240 RGB565 整帧；
- guest 计算的 FNV-1a 32 位摘要 `42521dc5`、字节和 `24725536` 与宿主侧按
  `m5_lcd_cam` 的 `camera_pattern_pixel()` 重建的确定性 DVP 波形完全一致
  （对应 sha256 `09c8ded08e8164eb6e6fe6a2a3f54fb2d6d1eed7930ab64e0802c1371c9a0696`），
  即帧内容来自真实 LCD_CAM + GDMA 数据面，不是宿主注入的假帧/PID/寄存器值；
- 三次独立运行摘要一致，串口标记稳定。

## 根因

原厂 `camera` 模块在 BOARD_ID 144 编译为 OMV `py_camera.c`，esp32-camera 使能
`CONFIG_SCCB_SOFTWARE_SUPPORT`：GC0308 探测走 **GPIO12(SDA)/GPIO9(SCL) 软件
bit-bang SCCB**（`driver/sccb.c` 的 `SCCB_Init/SCCB_Probe`），而不是硬件 I2C
控制器，也不是 LCD_CAM 内建 SCCB。

QEMU 侧 `M5.begin()` 先用硬件 I2C 控制器访问板载传感器（BMI270 等）。S3 控制器
模型在每次事务开始时调用 `m5stopwatch_soft_i2c_set_hardware_active_on_bus()`，
把共享 QEMU `I2CBus` 上的**所有**软 I2C 桥永久切换为“硬件已接管”，包括
GPIO12/GPIO9 这条相机 SCCB 桥。临时诊断（已从导出补丁移除）显示：相机 probe
期间 466 个 GPIO12/9 边沿被桥接模型解码，但全部带 `hw_active=1` 直接被丢弃，
`[gc0308]` 事务为 0，`SCCB_Probe(0x21)` 永远收不到 ACK，最终
`Detected camera not supported.` / `ESP_ERR_NOT_SUPPORTED (0x106)`。

## 修复（最小）

1. `esp32s3_soft_i2c.c`：新增 dedicated-pin 桥接变体
   `m5stopwatch_soft_i2c_init_dedicated_pins()`；当 bit-bang 引脚专属于该总线时，
   硬件控制器的事务不再关闭该桥。其他板卡的 `init_pins()` 语义不变（保留 M5GFX
   所需的单向 hand-off）。
2. `m5atoms3rcam.c`：相机 SCCB 桥改用 dedicated 变体；LCD_CAM/DVP 帧几何改为
   相机模块默认的 QVGA 320x240 RGB565。
3. `esp32s3.c`：`m5atoms3rcam` 机器建模 ESP32-S3-PICO-1-N8R8 的 8 MiB PSRAM
   （`default_ram_size = 8 MiB`）。esp32-camera 用 `MALLOC_CAP_SPIRAM` 分配帧缓冲，
   没有 PSRAM 模型时 `camera.init()` 仍会在 probe 之后失败。

## 复现

```bash
python3 platform/tools/fetch_firmware.py --firmware-id 1897200000000003117 --chip-id 0x0009
PYTHONPATH=platform/tools python3 tests/uiflow2/run_device_matrix.py \
  --device atoms3r-cam --flash-transport direct --out-dir /tmp/camsccb-matrix
```

期望：`[atoms3r-cam] PASS`，`summary.json` 中 `serial_expect` 含
`CAM_INIT_RESULT True`、`CAM_CAPTURE_BYTES 153600`、
`CAM_FRAME_DIGEST fnv1a 42521dc5`、`CAM_STATUS ok`。本目录
`matrix-summary.json` 是该命令的矩阵输出摘要，`summary.json` 是结构化结果摘要
（含串口标记、帧摘要/字节和、复现命令与未覆盖项）。原始串口转录（808 字节，
SHA-256 `384f29b0511f518234a31968dc6bb1ecf703652ae5a560fc57c0683fc0db2591`）
按证据策略留在本地 ignored 运行目录 `/tmp/camsccb-matrix/atoms3r-cam/serial.log`。

## 回归

同一构建产物上另跑 `--device stopwatch --device cores3`：两者均 PASS。
StopWatch 覆盖被修改文件原先服务的“M5GFX 先软 I2C 再交硬件控制器”单向 hand-off 路径；
CoreS3 覆盖相机走硬件 I2C 控制器的既有路径。

## 未覆盖

- 物理光学、曝光/白平衡、SCCB 电气时序与驱动力；
- 其他 framesize：LCD_CAM 模型的帧几何固定为板级 attach 的 QVGA，不跟随 GC0308
  window/subsample 寄存器；固件请求非 QVGA 尺寸时帧几何不会自动匹配（后续工作）；
- IR GPIO47、Grove G2/G1 Unit、USB CDC 控制台、任意第三方固件；
- 不向 AtomS3R、AtomS3 或其他 S3 主机转授本结论。

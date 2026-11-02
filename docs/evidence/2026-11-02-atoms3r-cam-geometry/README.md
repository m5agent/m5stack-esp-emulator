# AtomS3R-CAM 相机几何跟随与多帧流闭环

日期：`2026-11-02`。范围：虚拟设备（QEMU 原生 `m5atoms3rcam`）。物理光学/电气
`NOT RUN`。配套补丁：`patches/qemu-m5stack-peripherals/0118-camera-geometry-stream.patch`
（base = `0109` + `0110`/`0111`/`0112` + `0113` + `0114` + `0115` + `0116`，即 QEMU
树 `2f7cd67`；`0117-atomecho-board`/`0119-unit-i2c-batch2` 为并行层，`git apply
--check` 已在 `0116`、`0116+0117`、`0116+0119`、`0116+0117+0119` 上验证通过）。前置 `0115` 的记录见
[相机 SCCB/DVP 闭环](../2026-11-02-atoms3r-cam-sccb/README.md)。

## 结果

官方 UIFlow2 v2.5.4 AtomS3R-CAM 固件（`1897200000000003117`，SHA-256
`1b29cc3d838834b3a4713130010815f952cff58619001c76183dd0b0a588f2c1`）在同一
guest 内用 `camera.init(framesize=...)` 依次请求 5 个 framesize，每帧的字节数和
SHA-256 都与宿主按 `m5_lcd_cam` 确定性 DVP 波形重建的结果完全一致：

| framesize | enum | 输出 | 帧字节 | guest / 宿主重建 SHA-256 |
| --- | --- | --- | --- | --- |
| QQVGA | 1 | 160×120 | 38,400 | `94203cc2…bae69034` |
| 240X240 | 5 | 240×240 | 115,200 | `f1c92255…3945ec698` |
| QVGA（模块默认） | 6 | 320×240 | 153,600 | `09c8ded0…1371c9a0696` |
| CIF | 8 | 400×296 | 236,800 | `28cf4b4a…22efe508b6` |
| VGA | 10 | 640×480 | 614,400 | `94a147ff…6fa6e412` |

其中 QVGA 行沿用 `0115` 的单帧 oracle（`CAM_CAPTURE_BYTES 153600` +
`CAM_FRAME_SHA256`），保证基本 case 的向后兼容。

多帧流：宿主在看到 guest 的 `CAM_BASE_DONE` 标记后，通过 QMP 把
`/machine/m5-lcd-cam auto-increment` 置真（静态场景已在此之前取证），guest 连续
`capture()` 5 帧输出：

```
CAM_STREAM_FRAME 0 153600 09c8ded0…      (scene seed 0)
CAM_STREAM_FRAME 1 153600 8d801201…      (scene seed 1)
CAM_STREAM_FRAME 2 153600 90367124…      (scene seed 2)
CAM_STREAM_FRAME 3 153600 6ce34766…      (scene seed 3)
CAM_STREAM_FRAME 4 153600 16161b47…      (scene seed 4)
CAM_STREAM_CAPTURED 5
CAM_STREAM_BYTES_OK 5
CAM_STREAM_DISTINCT 5
CAM_STATUS ok
```

5 个 digest 互不相同（`CAM_STREAM_DISTINCT 5`），且逐一等于宿主重建的 QVGA
scene seed 0–4 帧；没有任何一帧匹配到撕裂/半帧缓冲。宿主 oracle 脚本
`tests/uiflow2/atoms3r_cam_console_test/frame_oracle.py` 对两次独立矩阵运行的串口日志都输出
`FRAME_ORACLE_OK geometry=5 stream=5`。

## 根因与修复

- 根因：`m5_lcd_cam` 的 DVP 帧几何此前固定为板级 attach 的 QVGA 320×240。
  esp32-camera 的 `camera.init(framesize=...)` 经 GC0308 `set_framesize()` 把输出
  尺寸编码在 **page 0 window 寄存器 0x09/0x0a（高+8）、0x0b/0x0c（宽+8）** 与
  **page 1 subsample 寄存器 0x54/0x56–0x59**（`CONFIG_GC_SENSOR_SUBSAMPLE_MODE`，
  输出 = window × ratio）。模型不解析这些寄存器时，非 QVGA 请求要么得到错误长度
  （QQVGA 只组装出 38,400 字节的 QVGA 流切片），要么等不到完整帧（CIF/VGA）。
- 修复（0118）：
  1. `m5sw_i2c_devs.c`：GC0308 模型解析 window/subsample 寄存器，按
     esp32-camera 的 8 组 subsample 配置做**精确整数反解**（非精确/瞬时混合状态
     不上报），把输出几何发布给绑定 LCD_CAM；
  2. `m5_lcd_cam.c`：在 `CAM_START` 上升沿锁存传感器几何，避免写寄存器过程中的
     中间态改变运行中的帧；合成场景每帧额外推进一行白格（`frame_seed=0` 保持
     原图案不变），使连续帧保持可区分；
  3. `m5atoms3rcam.c`：把板级 GC0308 设备绑定到 LCD_CAM。

未使用 host 端造帧、注入帧数据或伪造 digest：QOM 只切换模型的帧计数行为。

## 复现

```bash
python3 platform/tools/fetch_firmware.py --firmware-id 1897200000000003117 --chip-id 0x0009
PYTHONPATH=platform/tools python3 tests/uiflow2/run_device_matrix.py \
  --device atoms3r-cam --flash-transport direct --out-dir /tmp/geom-matrix
python3 tests/uiflow2/atoms3r_cam_console_test/frame_oracle.py \
  /tmp/geom-matrix/atoms3r-cam/serial.log
```

期望：`[atoms3r-cam] PASS` 与 `FRAME_ORACLE_OK geometry=5 stream=5`。
`matrix-summary.json` 为矩阵输出摘要，`summary.json` 为结构化结果摘要。

## 回归

同一二进制上：

- 外设矩阵 `cores3-camera` PASS（`CORES3_CAMERA_PASS 320x240 153600 bytes`、
  `CORES3_CAMERA_FRAMESTREAM PASS 1`）；
- 外设矩阵 `stackchan-camera` PASS；
- 设备矩阵 `cores3` / `stopwatch` PASS。

## 未覆盖

- 物理光学、曝光/白平衡、传感器噪声、DVP/SCCB 电气时序与驱动力；
- 运行中动态改 framesize（探针按尺寸重新 `camera.init()`；LCD_CAM 在
  `CAM_START` 锁存几何）；
- 超过 VGA 的尺寸（GC0308 驱动钳制到 VGA）与不在 esp32-camera resolution 表中
  的非 4:3 尺寸；
- IR GPIO47、Grove G2/G1 Unit、USB CDC 控制台、任意第三方固件；
- 合成场景是确定性 DVP 波形，不是真实光学的再现；不向其它 S3 主机转授。

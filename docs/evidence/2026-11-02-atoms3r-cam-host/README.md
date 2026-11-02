# AtomS3R-CAM（C126-CAM）虚拟主机接入（限定验证）

日期：`2026-11-02`。范围：把视觉库存中仅有外壳的 AtomS3R-CAM 接入为独立
原生 QEMU 主机；**摄像头数据面未闭环**，本记录只声明启动、板级识别、
显示初始化与传感器身份读取。物理光学/电气 `NOT RUN`。

## 结果

- 新增机器 `m5atoms3rcam`：AtomS3R 控制器初始化 + GC0308（0x21）挂到
  共享 I2C 总线 + LCD_CAM/DVP 控制器；SCCB 位翻转桥接在 GPIO12/GPIO9。
- 官方 UIFlow2 `v2.5.4`（`1897200000000003117`，SHA-256
  `1b29cc3d838834b3a4713130010815f952cff58619001c76183dd0b0a588f2c1`）
  在同一 guest 内输出：

  ```
  CAM_BOOT_FLAG / CAM_MAIN_START / CAM_M5_BEGIN_OK
  CAM_BOARD 144
  CAM_I2C_SCAN ['0x8', '0x10', '0x18', '0x21', '0x30', '0x43', '0x68']
  CAM_PID 9b00
  CAM_CAPTURE_BYTES 0
  CAM_STATUS blocked
  ```

- 设备矩阵 case `PASS` 的含义是“探针按预期执行到 blocked 状态”，
  **不是**相机通过。

## 未闭环与下一步

- 原厂 `camera.init()` 仍打印 `Detected camera not supported` /
  `ESP_ERR_NOT_SUPPORTED`，`camera.capture()` 返回空。共享 I2C 总线可扫描
  到 `0x21` 并读到 GC0308 `PID 0x9b`，说明器件模型和总线可达，缺的是
  esp32-camera 的 SCCB/初始化路径（或其对 PSRAM/时序的前置要求）。
- 下一步：对照 UIFlow2 esp32-camera 源码确认 SCCB 控制器与地址宽度，
  在 `m5_lcd_cam`/SCCB 路径上补齐后再要求真实帧 oracle。

## 复现

```bash
python3 platform/tools/fetch_firmware.py --firmware-id 1897200000000003117 --chip-id 0x0009
PYTHONPATH=platform/tools python3 tests/uiflow2/run_device_matrix.py \
  --device atoms3r-cam --flash-transport direct --out-dir /tmp/s3rcam-matrix
```

## 未覆盖

- 相机帧、IR GPIO47、Grove Unit、USB CDC、任意第三方固件与物理行为。
- 不转授 AtomS3R、AtomS3 或其它 S3 主机。

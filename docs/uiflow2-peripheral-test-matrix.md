# UIFlow2 外设 API 测试矩阵

日期：`2026-10-21`

本轮以 StickS3 和 CoreS3 为样本，验证 UIFlow2 API 是否可调用，以及 QEMU
是否产生了对应设备行为。测试只代表仿真结果，不是实机验收。

## 结果

| 设备 | 能力 | UIFlow2 API | 结果 | 观察 |
| --- | --- | --- | --- | --- |
| StickS3 | IMU 识别 | `Imu.getType()` / `isEnabled()` | PASS | 返回 BMI270 类型 `6`，enabled `1` |
| StickS3 | 加速度计/陀螺仪数值 | `Imu.getAccel()` / `getGyro()` | PARTIAL | QOM 注入后仍保持 `0,0,0`，BMI270 数据更新路径未闭环 |
| StickS3 | A/B/P 按键 | `BtnA/BtnB/BtnPWR` | PASS | 三个计数均从 `0` 变为 `1` |
| StickS3 | 电源 | `Power.getBatteryLevel/Voltage/isCharging` | PASS | `87%`、`4000mV`、charging `1` |
| CoreS3 | IMU 识别 | `Imu.getType()` | PASS | 返回 BMI270 类型 `6` |
| CoreS3 | 加速度计/陀螺仪数值 | `Imu.getAccel()` / `getGyro()` | PARTIAL | QOM 注入后仍为 `0,0,0` |
| CoreS3 | 磁力计 | `Imu.getMag()` | FAIL | BMM150 未建模，API 返回全零而不是真实磁场 |
| CoreS3 | 触摸 | `M5.Touch` | PASS | 触摸计数从 `0` 变为 `1` |
| CoreS3 | PWR 按键 | `BtnPWR` | PASS | 电源键事件被识别 |
| CoreS3 | 电源 | `Power.getBatteryLevel/Voltage/isCharging` | PASS | `87%`、`4000mV`、charging `1` |
| CoreS3 | RTC | `time.localtime()` / UIFlow2 RTC 初始化 | PASS | 输出有效日期时间 |
| CoreS3 | 摄像头初始化 | `camera.init(RGB565, QVGA)` | PASS | GC0308 SCCB 识别和初始化成功 |
| CoreS3 | 摄像头取帧 | `camera.snapshot()` | PARTIAL | 返回 `None`；LCD_CAM capture/DMA 未建模 |

## StickS3

![StickS3 peripheral probe](images/sticks3-peripheral-test.png)

按键与电源 API 已经可以用于自动测试。IMU 已能正确识别 BMI270，但传感器数值
没有随 QOM 注入变化，因此当前不能把 `getAccel()` 的全零结果判为有效传感器数据。

## CoreS3

![CoreS3 peripheral probe](images/cores3-peripheral-test.png)

触摸、PWR、电源和 RTC 已可用于自动测试。BMI270 与 BMM150 的数据通路仍需补齐，
其中磁力计当前会返回看似有效但实际不可信的全零值。

## CoreS3 摄像头

![CoreS3 camera probe](images/cores3-camera-probe.png)

`camera.init()` 已通过 GC0308 的 SCCB 识别，证明 UIFlow2 camera 模块和板级摄像头
初始化路径可以执行。`camera.snapshot()` 返回 `None`，说明缺少 ESP32-S3 LCD_CAM
采集、DMA 和帧缓冲模型。下一阶段应在 QEMU 中实现测试图样摄像头帧，而不是让
Python 层直接伪造 Image。

## 复现

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/run_peripheral_matrix.py \
  --out-dir /tmp/m5-uiflow2-peripheral-matrix
```

测试源码：

- `tests/uiflow2/sticks3_peripherals/`
- `tests/uiflow2/cores3_peripherals/`
- `tests/uiflow2/cores3_camera/`

## 未覆盖

- StickS3 IR 发射/接收
- StickS3 麦克风和扬声器采样链路
- CoreS3 麦克风、扬声器和音频编解码数据链路
- CoreS3 SD 卡、USB Host、摄像头真实帧
- 所有项目的真机复测

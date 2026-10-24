# Core2

- SKU：`K010-V11`
- 分组：`ESP32 LX6`
- 外壳：`核心主控`
- 运行时：`reference-ready`
- 外设仿真：`simulated`
- UIFlow2：`支持`，m5ui：`支持`
- UIFlow2 固件：v2.5.3 / `1897200000000003470`

## 硬件档案

| 项目 | 值 |
| --- | --- |
| SoC | ESP32-D0WDQ6-V3 |
| 架构 | xtensa-lx6 |
| Flash | 16 MB |
| PSRAM | 8 MB |
| 机身尺寸 | 54 × 54 × 16.5 mm |
| 重量 | 45.1 g |
| 显示 | 320×240 ips，2"，ILI9342C / ILI9342E，触摸 |
| 控制 | Touch, PWR |
| 外设 | imu:mpu6886, rtc:bm8563, microphone:spm1423, speaker:ns4168, power-monitor:ina3221 |

## 模拟状态

reference-ready：真实固件、画面和输入已打通。

- 验证：`display-input-peripherals-wifi-ble-pass` (2026-10-24)
- 详情：官方 UIFlow2 v2.5.3 在同一 m5core2 guest 内通过 320x240 显示/触摸、AXP2101、INA3221、MPU6886、PCF8563、NS4168 扬声器、SPM1423 麦克风、OpenMAC WiFi DHCP/HTTP、example.com IPv4 DNS/HTTP 和 stock firmware 外部 BLE GATT；确定性 TCG/icount 调度下 10/10 次无重试首轮启动通过，QOM 注入不暂停 guest，QEMU 仍使用 -m 0。规范 Device Service profile `core2-native-hci` 在五个独立 lease 中通过 HCI-4：frame、27 节点 QOM、WiFi/公网、外部 NUS GATT、pcap 和 evidence 同包，且 gdb_bridge=false。0005 恢复 nested guest call 的 caller-saved sregs，并把 HLI allocator/callback 注入限制在 halted/idle vCPU；两批独立 5×10 秒运行合计 10/10，3 个 60 秒 hold 为 3/3，2 个 120 秒 hold 为 2/2，另 2 个 active-BLE 600 秒 hold 为 2/2。3 个独立 lease 分别完成 20、30、60、120 轮 scan/connect/NUS GATT/disconnect；当前参数上限为 120 并拒绝 121。一百二十轮每 lease HLI 3377/3377、events 2297、ACLs 1080，HLI/meta/TX queue、错误和 panic 均为 0，连接/L2CAP/GATT 池回到 3/9/3，三次 frame SHA256 一致。600 秒 active-BLE hold 时 peer 未关闭，HLI 45/45，队列与错误为 0。旧 `core2-native-vhci` 的 repeated lease 为 1/2，仅保留为 GDB 诊断/兼容路径。超过一百二十轮、两小时 soak、物理 cache/PSRAM、coexistence 与 Espressif BT baseband/controller bit-exact 执行仍未完成。





## 文件

- `device.json`：设备中心与页面使用的完整档案
- `firmware.json`：UIFlow2 固件定位与缓存约定
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用

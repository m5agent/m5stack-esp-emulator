# 虚拟主机适配矩阵

日期：`2026-10-25`

本页只维护稳定的设备、SoC、后端和板级入口映射。动态 PASS 计数、最新验证
日期、运行边界和剩余缺口分别由
[自动项目快照](project-snapshot.md)、[项目当前状态](project-status.md)和
[项目 Backlog](project-backlog.md)维护，避免同一组数字在多个页面漂移。

## 后端划分

| 分组 | 主后端 | 产品定位 | 稳定边界 |
| --- | --- | --- | --- |
| ESP32-S3 | `qemu-esp32s3` | 单 guest 板级、WiFi（含 WPA2-PSK pairwise/unicast）和 HCI BLE | 功能级 MAC/DMA/网络模型，不是 WPA3/group multicast、PHY/RF、功耗或电气模型 |
| ESP32-C6 | `qemu-esp32c6` | 单 guest 板级、WiFi 和 HCI BLE | Zigbee/802.15.4 由 `RUNTIME-02` 单列 |
| ESP32 LX6 | `qemu-esp32lx6` | Core2 板级、OpenMAC WiFi、BLE controller boundary、8 MiB PSRAM QOM、DRAM1 MMU upper-bank remap 与周期联网 | canonical BLE 路径为 `core2-native-hci`；legacy VHCI 仅诊断；普通 4 MiB heap stress + upper-bank `3/3` 已覆盖；双实例 `8/8`、三实例 `6/6`、四实例 `8/8`、五实例 30 秒错峰 `10/10`；四实例原始 `1/4` 失败保留，五实例零错峰 `5/5 PASS`/`3/5 FAIL` 仍不稳定，`0010` 已把首个异常收敛到 HLI response readiness/delivery ordering；更多实例及物理 PSRAM/cache timing 不覆盖 |
| ESP32-P4 | `esp-emulator-native` | Tab5 烧录、M5GFX framebuffer、touch mailbox 和部分 I2C | 闭源 P4 后端，外设仍为 `partial` |
| Linux ARM64 | `external-linux-arm64` | CardputerZero 独立 Linux 设备 | 不是 ESP32/UIFlow2 固件目标，也不由当前 `/api/v1` 管理 |

设备登记和 QEMU profile 的机器可读源分别是
`devices/catalog.source.json` 和 `platform/qemu/profiles.json`。自动快照会把
两份源与 peripheral contract 合并；本页不重复维护运行结果。

## 设备映射

| 设备 | SoC | 后端 | 显示 / 输入 | service lease |
| --- | --- | --- | --- | --- |
| StopWatch | ESP32-S3R8 | `qemu-esp32s3` | CO5300 466x466 圆屏 / 触摸 | 是 |
| AtomS3R | ESP32-S3-PICO-1-N8R8 | `qemu-esp32s3` | GC9107 128x128 / GPIO | 是 |
| CoreS3 | ESP32-S3 | `qemu-esp32s3` | ILI9342 320x240 / 触摸 | 是 |
| StickS3 | ESP32-S3-PICO-1-N8R8 | `qemu-esp32s3` | ST7789 135x240 / GPIO | 是 |
| Cardputer-ADV | ESP32-S3FN8 | `qemu-esp32s3` | ST7789 240x135 / TCA8418 键盘 | 是 |
| StackChan | ESP32-S3 | `qemu-esp32s3` | ILI9342 320x240 / 触摸和舵机 | 是 |
| StamPLC | ESP32-S3FN8 | `qemu-esp32s3` | ST7789 240x135 / 面板按键 | 是 |
| PaperColor | ESP32-S3R8 | `qemu-esp32s3` | Spectra 6 400x600 / GPIO | 是 |
| PaperMono | ESP32-S3R8 | `qemu-esp32s3` | SSD1677 480x800 / 触摸和按键 | 是 |
| NanoC6 | ESP32-C6FH4 | `qemu-esp32c6` | 无屏 / GPIO、RGB、IR | 是 |
| Arduino Nesso N1 | ESP32-C6 | `qemu-esp32c6` | ST7789 135x240 / 触摸 | 是 |
| Core2 | ESP32-D0WDQ6-V3 | `qemu-esp32lx6` | ILI9342 320x240 / 触摸 | 是 |
| Tab5 | ESP32-P4NRW32 + C6 | `esp-emulator-native` | 1280x720 / 固件 touch mailbox | 是，外设 `partial` |
| CardputerZero | RP3A0 / BCM2837 | `external-linux-arm64` | ST7789v3 320x170 / TCA8418 | 独立后端 |

## 运行时优先级

| 层级 | 入口 | 用途 | 不能证明什么 |
| --- | --- | --- | --- |
| 产品验收 | `runtime=qemu-unified` + 对应 unified profile | 一个 lease、一个 QEMU guest、板级 + WiFi + BLE + evidence | 物理 RF、功耗、电气和真机行为 |
| 固件功能审查 | Device Service `/api/v1` session | 上传、烧录、串口、frame、输入、QOM、网络和 evidence | 未建模控制器或未执行的应用路径 |
| 网络诊断 | `runtime=network` / `network_lane.py` | WiFi/BLE blocker、SoftAP、DNS/TCP/UDP/HCI | 同 guest 的板级或整机 PASS |
| Core2 BLE 兼容 | `core2-native-vhci` | GDB 边界对照和历史诊断 | 稳定生产路径 |
| Tab5 例外 | `esp-emulator-native` | P4 烧录、framebuffer、touch mailbox、ESP-Hosted | 完整 P4 外设或任意生产镜像兼容 |
| Linux 设备 | `external-linux-arm64` | CardputerZero 系统、驱动和帧数据面 | ESP32/UIFlow2 结论 |

`qemu-ble` 仍作为兼容别名接受，新调用使用 `qemu-unified`。Core2 新调用使用
`profile=core2-native-hci`；`core2-native-vhci` 只用于显式诊断。
Core2 的长 BLE reconnect workload 使用按 cycles/delay 计算的 readiness
预算；首次 `121` 轮运行曾被固定 `180s` 预算误杀，失败保留为等待预算证据，
修复后 3 个独立 lease 均为 `121/121 PASS`。

## 板级接入步骤

1. 在 `devices/catalog.source.json` 登记真实 SoC、Flash、PSRAM、显示、控制和
   传感器能力。
2. 在 `platform/peripherals/catalog.json` 为每项非显示能力登记芯片模型、总线、
   地址、QOM/注入接口、数据面和设备级证据。
3. 在 `platform/peripherals/runtime-coverage.json` 绑定设备本地 matrix case
   或 external probe；不能用另一台设备的 PASS 继承。
4. 在 `platform/qemu/profiles.json` 登记 machine、backend、显示和 blocker。
5. 添加板级 QEMU profile、显示/输入路径和设备本地 UIFlow2 probe。
6. 通过 Device Service 执行目标 session，保存固件 SHA、runtime/profile、
   serial、frame、输入和对应数据面 evidence。
7. 同步生成目录、自动快照、当前状态、Backlog 和必要专题页。

新增设备若仍有 `partial`/`planned` 非显示外设，会触发 peripheral catalog
门禁；现有未完成设备必须进入有复查日期的 allowlist。

## 已有 bring-up 批次

早期按 S3 基础三台、输入/工业三台、电子纸两台、C6 两台和高风险三台推进的
五批 bring-up 均已完成。该分组只解释实现顺序，不再是待办或当前能力表：

- 第 1 批：StickS3、AtomS3R、CoreS3；
- 第 2 批：Cardputer-ADV、StamPLC、StackChan；
- 第 3 批：PaperMono、PaperColor；
- 第 4 批：Nesso N1、NanoC6；
- 第 5 批：Tab5、Core2、CardputerZero。

今天的未完成项只以 Backlog Task ID 为准；这些历史批次中已经完成的步骤不会
因为本页保留历史说明而重新进入待办。

## 注册表与校验

```bash
python3 platform/tools/qemu_profiles.py --list
python3 platform/tools/qemu_profiles.py --group esp32-s3
python3 platform/tools/qemu_profiles.py --device sticks3
python3 platform/tools/qemu_profiles.py --check
python3 platform/tools/peripheral_catalog.py --check
python3 platform/tools/runtime_coverage.py --check
python3 platform/tools/project_snapshot.py --check
```

设备级 PASS 至少要有固件 hash、runtime/profile、输入、串口、frame 和对应
数据面 evidence。进程启动、版本匹配或单条日志不能单独作为应用 PASS。

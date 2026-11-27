# esp32sim 后端迁移计划（草案）

日期：`2026-11-26`。状态：草案，未进入 Backlog。所有运行结果都是
virtual-device validation，不代表硬件结论。

## 目标

把 M5 设备的模拟内核逐步从 QEMU 9.2.2 补丁树（含闭源 esp-emu）迁到
[esp32sim](https://github.com/mikroverk/esp32sim)（MIT，Rust，同一套代码构建原生和 WASM）。
原 QEMU 后端封存，保留可重启能力，不删除。

迁移要解决的是我们改不动的内核和驱动层问题：

- P4/Tab5 闭源内核（#188 DSI、#226 USB-OTG）；
- QEMU-WASM 对 SharedArrayBuffer/跨源隔离的依赖（#242）和 TCI 复位类问题
  （RUNTIME-07/08/09）；
- TCG 墙钟时序导致的不可复现竞态；
- C6 802.15.4 缺失（RUNTIME-02）。

固件自身缺陷（#223、#216）和板级资源缺失不会因为换内核而消失。

## 参考来源

| 来源 | 用法 |
| --- | --- |
| mikroverk/esp32sim | 上游内核。SoC、外设、JIT、WASM 都以它为准 |
| zhuzhe1983/esp-online-tester | 已有若干 M5 板模型，只当线索。每个寄存器值、引脚和行为都要对照 M5GFX/M5Unified 源码或数据手册重新核对后再用 |
| 本仓库 QEMU 补丁 | 行为规格和回归用例来源。GPL 代码不复制，按手册和驱动源码在 Rust 中重写 |
| M5GFX / M5Unified 源码 | 引脚、I2C 地址、初始化序列的第一手依据 |

## 阶段

### 阶段 0：封存 QEMU 后端

- 给当前主线打标签（例如 `qemu-backend-freeze-20261126`），记录 QEMU、补丁、
  WASM、Device Service 的 hash 和重建命令；
- 原生 rollout 与浏览器 WASM 构建脚本保持可用，不删补丁目录；
- 新增工作只进 esp32sim 分支，QEMU 只接受阻断性修复。

### 阶段 1：CoreS3 完整板模型（判定门槛）

在 fork 分支 `m5/cores3` 上实现 `--board m5stack-cores3`：

| 组件 | 内容 |
| --- | --- |
| 显示 | ILI9342C，SPI2 三线（SCLK 36、MOSI 37、D/C 与 MISO 共用 35、CS 3），面板 ID `0xE3` 读回 |
| 触摸 | FT6336/FT5x06 `0x38`，INT 经 AW9523 P1_2 汇到 GPIO21 |
| 电源 | AXP2101 `0x34`：电池电压、电量、充电、VBUS、PWR 键 IRQ、DLDO1 背光 |
| IO 扩展 | AW9523 `0x58`：LCD 复位 P1_1、BUS_OUT_EN、触摸中断、读清中断 |
| 传感器 | BMI270 `0x69` + BMM150（经 AUX）、LTR553 `0x23`、BM8563 `0x51` |
| 音频 | AW88298 `0x36` + I2S1 扬声器、ES7210 `0x40` + I2S1 麦克风 |
| 相机 | GC0308 `0x21` SCCB + LCD_CAM DVP |
| 存储 | microSD（SPI，CS 4，与 LCD 共用总线） |

验收：产品文档 CoreS3 Arduino 例程（15 个，固件已由文档源码编译，
SHA 见 `.work/docs-examples-20261125.U1s7Lf/compile-cores3.ndjson`）在 esp32sim
与当前 QEMU 上各跑一次，逐项比较串口、首帧时间、画面、输入响应和确定性。
随后再跑 UIFlow2 v2.5.3 CoreS3 固件到主页。

不过门槛就停止全面迁移，只保留 P4 和浏览器两条线。

### 阶段 2：Tab5/P4

移植 GT911、ST7123、ES8388/ES7210、BMI270、RX8130、INA226，补 DSI、PPA、
DMA2D，用 #188、#226 原固件验证。

### 阶段 3：浏览器 lane

esp32sim WASM 替代 QEMU-WASM，从 CoreS3 和 Cardputer-Adv 开始，验收 #242
的无跨源隔离嵌入。

### 阶段 4：Device Service 适配

- 新增 `runtime=esp32sim`，用控制协议替代 QMP/QOM：输入注入、外设状态读写、
  按需取帧、串口、停止前证据 ZIP；
- 每台设备在同一固件上两个后端对等后再把默认值切过去。

### 阶段 5：其余设备

按 S3 设备（19 台）→ ESP32 classic（13 台，esp32sim 标记为 early）→ C6 的顺序推进，
Unit 运行时按使用频率重写。

## 风险

- esp32sim S3 上的 UIFlow2 在 MicroPython 启动前停在 `0x4038382e` 附近，根因未查；
- 没有 GDB stub 和快照；
- 上游节奏快，fork 需要定期 rebase，并尽量把通用改动回馈上游；
- 所有 QEMU 上的 PASS 都不能继承，需要重验。

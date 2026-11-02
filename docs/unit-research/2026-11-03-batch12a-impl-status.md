# Unit batch12a（7 款 driver-gap I2C/GPIO）实现状态

日期：`2026-11-03`。范围：把 batch-12a 7 款 driver-gap Unit 接入 QEMU 数据面并登记
planned 契约，依据 **batch11 driver-gap 协议研究**（PR #150 分支
`m5agent/unit-doc-research`，commit `a2accf79` 的
`docs/unit-research/2026-11-03-batch11-driver-gap-protocols.md`，逐款寄存器表与
协议 PDF 出处见该文 §4.1-§4.6、§5.1）。**本批无 guest/Device Service 证据，
7 款全部保持 planned，不升级 implemented。**

## 补丁与 base

- 补丁：`patches/qemu-m5stack-peripherals/0158-unit-batch12a.patch`
  （sha256 `f998539539a7934d8ed38d45af846516570eaaa11e9858f7d940b0f19fc97aff`）。
- base：canonical **36 层**链至 `0156`（canonical `75f1d24` + `0120`-`0156`）；
  本补丁是 0120 之后的第 37 层，在 pristine 36 层 baseline 上
  `git apply --check` 通过。next free：`0158`。
- 运行时二进制：删 build 重配后 ninja 构建，签名后 sha256
  `e1602217…`（离线 smoke 使用）。

## 7 款模型与边界

| Unit | SKU / 地址 | 0157 模型 | 显式边界 |
| --- | --- | --- | --- |
| `byteswitch` | U191 0x46 | `CONTROL_BYTEUNIT`：0x00 状态位图、0x60-0x67 单通道、0x10-0x18 亮度、0x19 模式、0x20-0x4F user RGB888（`base=0x20+(n//4)*0x10+(n%4)*4`）、0x70/0x90 sys RGB、0xF0 保存、0xF1 IRQ、0xFE FW、0xFF 地址 | **无 guest 证据 → planned；开关机械/拨动电气/WS2812 光学/级联双 Grove/IRQ 引脚电气 NOT RUN；位图物理极性 unresolved（驱动约定 0=按下/闭合）；0x46 无已登记冲突** |
| `bytebutton` | U192 0x47 | 与 byteswitch 共享 `CONTROL_BYTEUNIT`，默认 0x47 | **同上；按键机械/光学、9 灯串接方向 NOT RUN；0x47 无已登记冲突** |
| `step16` | U198 0x48 | `CONTROL_STEP16`：position 0-15、LED 配置/亮度、方向、RGB 电源/亮度/RGB、保存、FW、地址（可配 0x08-0x77） | **无 guest 证据 → planned；BCD 旋钮机械/弹跳、7 段显示光学、睡眠定时时间轴、真实 FLASH 持久化 NOT RUN；0x48 与 adc-v11/ameter/adc 冲突** |
| `timerpwr` | U189 0x56 | `CONTROL_TIMERPWR`：Grove 输出/背光/按键/trigger/定时开关/cycle、USB+Grove V&I（LE32 raw/100）、电池 V（mV/10）/I（mA/100）、充电、保存/FW/地址 | **无 guest 证据 → planned；真实 RTC 长定时、电池充放电、DC-DC 升压负载、OLED/按键、热/安全 NOT RUN；0x56 与 mini-bps-v11 冲突** |
| `mq` | U199 0x11 | `CONTROL_MQ`：mode/LED/加热时间、ADC8/ADC12、valid、NTC ADC/Ω、ref/MQ/NTC mV、FW/地址 | **valid 极性按驱动 `get_valid_tags()==1` 实现，协议 PDF 写 0=有效：冲突 unresolved；无 guest 证据 → planned；MQ-5 气体曲线/预热/加热热学 NOT RUN；0x11 无已登记冲突** |
| `8servos2-i2c` | U222 0x25-0x34 | `CONTROL_SERVOS8V2`：8 通道模式/上下拉/输入/输出/ADC/舵机/PWM、RGB 缓冲、定时器频率、UID、系统遥测、FW/地址；`rotary` fixture 选择地址 | **无 guest 证据 → planned；舵机/WS2812/PWM 电气与波形、INA199 电流精度、9-24V 供电、I2C 级联、MCU 型号冲突（STM32F030F4P6 vs STM32G031G8）NOT RUN；0x25 与 8servos、0x26 与 scales 系冲突** |
| `cardkb2` | U215 0x5F | `CONTROL_CARDKB2` legacy I2C 子集：0x00 raw key byte + 0xF1 firmware version | **UART AA03 帧模式、v2 report、BLE HID、ESP-NOW 是不同 attachment kind，不在本 I2C 模型内，NOT RUN；官方 v2 report 未与手册对齐；42 键机械/键码表/重复率 NOT RUN；Grove PORT.CUSTOM G26/G25 未准入（未来证据需 cores3 PORT.A harness）；0x5F 与 cardkb/cardkb-original 冲突** |

## 离线 QOM smoke（S3 `m5atoms3r`，无 guest）

一个 QEMU 构建 + 7 个 attachment，检查属性注册/fixture 读写/范围与时间格式拒绝/
rotary 地址映射：**20/20 PASS**。示例断言：byteswitch `state-bitmap=0xFF`、设置
`0x7E` 回读、`rgb-hex` 54 字符读写、`brightness` 范围拒绝；bytebutton 地址 0x47；
step16 `position=0/7`、`rgb=0x123456`、范围拒绝；timerpwr `schedule-on=12:34`、
`battery-mv=4000`、`25:99` 拒绝；mq `sensor-mv=1500 → adc12=4095/adc8=255`；
8servos2 `rotary=3 → i2c-address=0x28`；cardkb2 `key-code=65`、范围拒绝。

smoke **不覆盖** I2C 寄存器读写时序/字节语义、真实设备行为或 guest 路径；这些仍
需要 guest 证据才能升级 profile。

## 计数与索引

- catalog/profiles：7 条契约由 batch11 的「仅登记、runtime 属性为空」更新为
  **planned + 完整 runtime QOM 契约**；catalog 总数保持 **160**（这 7 款在 base
  `067db249` 已登记，任务预期的 160→167 与 base 实际不符，未重复添加）。
- visual mapping：7 条 audit 更新为 0157 模型 + 字段，marker 保持
  `all-160-products`；计数测试未变。
- 新增静态测试 `platform/tests/test_unit_batch12a_patch.py` 钉住补丁 token、
  7 条 planned 契约、runtime 属性非空与无 guest PASS 声明。

## 结论

7 款 driver-gap Unit 已具备 **controller-visible 的寄存器文件数据面 + planned
QOM 契约**，但没有 guest 证据、没有官方冻结驱动参与，全部保持 planned；
`cardkb2` 的 UART/BLE/ESP-NOW 子集与 `8servos2-i2c` 的 MCU 型号分歧是显式缺口，
不是已验证能力。

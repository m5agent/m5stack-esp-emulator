# Batch-9 剩余 9 款 Unit 实现/契约状态（2026-11-03）

本页记录 batch-9 剩余 9 款的落地状态，承接
[`2026-11-03-batch9-protocols.md`](2026-11-03-batch9-protocols.md) 与
`2026-11-03-batch9-catalog-draft.json`。所有 9 款**保持 planned**、profile
hosts 为空；本批**不做 guest/Device Service 证据**，只有 4 款的 UART 字节层
模型做了离线 QOM smoke，5 款无驱动/无寄存器表的 Unit 只登记 planned 契约。

## 结论

| Unit | 状态 | 证据/实现边界 |
| --- | --- | --- |
| `lorawan-as923` | 已实现 UART 字节层（planned） | 复用 UART TX 捕获 + idle fixture responder；只暴露 responses-hex/tx-hex/frames-sent/frames-injected；AS923 无驱动子类、STM32WLE5 vs ASR650x 错配 unresolved，OTAA/ABP/Join/RF/占空比 NOT RUN |
| `lorawan-eu868` | 已实现 UART 字节层（planned） | 同上；驱动有 LoRaWAN_868 但 unit 包装仍用 470；EU868 RF/Join/占空比 NOT RUN |
| `audioplayer` | 已实现 UART 字节层（planned） | U197 9600 8N1，只捕获 TX/注入 fixture；无官方 Unit 驱动/N9301 命令表，MP3/WAV/microSD/3.5mm 音频 NOT RUN |
| `fingerprint2` | 已实现 UART 字节层（planned） | U203 115200 8N1；A-K323CP 无 Unit 驱动/帧格式，且与 batch6 finger FPC1020A 不同芯片；指纹/匹配/RGB NOT RUN |
| `cardkb2` | **仅 planned 契约** | 不建模型、不猜寄存器；官方 driver coming soon、I2C 地址/UART 帧未知、PORT.CUSTOM G26/G25 未准入；键盘/RF NOT RUN |
| `8servos2-i2c` | **仅 planned 契约** | 只写 0x25-0x34 地址元数据；内部固件通道寄存器表不可读；0x25 与 8servos U165 冲突、0x26 与 scales 系冲突；servo/ADC/RGB/PWM/9-24V/INA199 NOT RUN |
| `bmm350` | **仅 planned 契约** | 只写 0x14 地址元数据；无 driver/寄存器表，Bosch datasheet/OTP 未钉；磁场/heading/校准 NOT RUN |
| `ina226-10a` | **仅 planned 契约** | 只写 0x41 地址元数据；无 driver/寄存器表，TI datasheet 未钉；隔离/0-30V/±10A/保险/精度 NOT RUN；0x41 与 ina226-1a 同地址 |
| `rollercan` | **仅 planned 契约** | 只写 0x64+CAN 元数据；内部固件/通信协议外部文档、无寄存器/帧表；电机/FOC/编码器/OLED/RGB/滑环/6-16V NOT RUN |

## QEMU 0151

`0151-unit-batch9b.patch`（base canonical 链 30 层 through 0149；0150 batch7
证据修复为并行层，reconciliation 6 纳入；本层是 0120 起第 31 层）：

- 在 `m5_unit_gpio_supported`、S3-only 校验、UART TX 捕获条件、
  通用 idle fixture responder 分支、realize 分支中登记 `lorawan-as923`、
  `lorawan-eu868`、`audioplayer`、`fingerprint2` 四个 id；
- 复用现有 `responses-hex`/`tx-hex`/`frames-sent`/`frames-injected`
  QOM 接口，不新增协议解码；
- 不注册 cardkb2/8servos2-i2c/bmm350/ina226-10a/rollercan 模型。

离线 QOM smoke（S3 `m5cores3`，无 guest firmware）：4 款 attach 成功，属性
列表含 responses-hex/tx-hex/frames-sent/frames-injected；设置
`responses-hex=4f4b0d0a;4f4b0d0a` 后属性回读一致，tx/frames 保持 0（无 guest
TX）。该 smoke **不是** functional PASS，不产生 guest 证据。

## 计数与边界

- catalog/profile **133→142**（9 条 planned，hosts 空）。
- visual audit 9 条 + marker `all-142-products`。
- 全部 9 款 catalog `model_status=planned`；4 款 UART 模型存在但**不**因此
  升级 profile/catalog 状态；无 guest/Device Service 证据。
- 地址冲突与 driver-gap 已写入 catalog blocker/limitations：0x14/0x25-0x34/
  0x41/0x64/0x5F?/自定义 PORT.CUSTOM；UART 三款共用 PORT.C；无 RF/蜂窝/
  LoRaWAN stack/GNSS/音频/生物特征/电机语义声明。
- 下一阶段若实现/证据这 9 款，需先补驱动/寄存器表/帧格式或 datasheet，
  并按 batch1-8 的证据 gate 采集 guest/Device Service 证据；不得把本页
  QOM smoke 当作 PASS。

## 验证

- `0151-unit-batch9b.patch`：`git apply --check` + reverse OK。
- 离线 QOM smoke：4/4 attach/property 回读。
- 全量测试 + 四 check 结果见 PR/commit 报告。

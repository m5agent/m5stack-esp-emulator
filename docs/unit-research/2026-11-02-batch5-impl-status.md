# Unit 第五批首批 5 款实现状态（补丁 0137）

日期：`2026-11-02`。归属任务 `task-32`，worktree `esp-emulator-units6`，分支
`m5agent/units6`（初始 base `origin/main 326114cc`，已 rebase 到含 batch5 协议研究的
`origin/main b07b1ef4`，Unit 82 款）。

**说明**：任务 base（`326114cc`）建立时 `docs/unit-research/2026-11-02-batch5-protocols.md`
尚未合入；实现过程中该研究文档已随 PR #112 合入 main（commit `57bcc714`），因此本页
与其交叉引用：协议/寄存器证据见协议研究 §4.2（pbhub-v11）、§4.3（8angle）、§4.4
（kmeter-iso-v11）、§4.7（rgb-led-10cm）、§4.9（op90）与 §5 unresolved 汇总；本页
只记录 QEMU 实现状态、QOM fixture、smoke 与实现层边界。

本页是**实现状态**，不是运行时或硬件 PASS。没有运行固件或 Device Service；没有
guest 证据，因此 catalog 与 runtime-profiles 的 5 条记录全部保持 `planned`、
hosts 为空。离线 QOM smoke（S3 board、无 guest）只验证属性注册、fixture 读写、
范围/只读拒绝与数组形状（19/19 PASS）。

## 补丁与 base

- 补丁：`patches/qemu-m5stack-peripherals/0137-unit-batch5a.patch`（388 行，
  sha256 `05698a1a…`，canonical 链上 `git apply --check` 通过）。
- canonical 链（reconciliation 后，见 `patches/qemu-m5stack-peripherals/README.md`）：
  `75f1d24` → `0120`-`0129` → `0131` → `0134` → `0136` → `0130` → `0133` → `0135` → `0132` → `0137` → `0138` → `0139`；
  `0140` 是下一个可用补丁号。本页的 `0137` 已由 patch-chain reconciliation 重导出，并在该 canonical 链上验证 `git apply --check`。
- 实现历史：源锁树 `839f634`（canonical + 已合入的 0120–0129 + 0131 + 0134 + 0136，reconciliation 前）与实现 commit `b991dd7` 仅作当时构建记录；
  `0130/0132/0133/0135` 已并入 canonical 链，不再是并行层。

## 5 款实现与边界

| Unit | 官方证据锚点 | 0137 模型 | QOM fixtures/观测 | unresolved / NOT RUN |
| --- | --- | --- | --- | --- |
| `pbhub-v11` U041-B | 页面 `pbhub_1.1`：STM32F030F4P6、I2C 0x61、firmware v1/v2（v2 增 SK6812 + IAP）；驱动 `unit/pbhub.py`（PBHUBUnit，快照=`7838aaa2…`，master 语义不同） | 复用 0131 `CONTROL_PBHUB` 单 0x61 命令空间（base 0x40/0x50/0x60/0x70/0x80/0xA0 × offset 0x00..0x0B，0xFA RGB mode）；unit id `pbhub-v11` 只把 fw-version fixture 设为 2 | digital-inputs/analog-inputs[6]、digital-outputs/pwm-outputs/rgb-frames[6]、rgb-mode、fw-version、i2c-address | **v1/v2 除版本字节外的行为差异 unresolved；0x61 与 pbhub 冲突；通道基址与 encoder/scroll/nfc/acssr/dac/env-iii 命令空间重叠；hub 嵌套/PWM/servo/RGB 电气/IAP NOT RUN** |
| `op90` U057 | 页面 `OP.90`：90° 红外对射限位开关，PORT.B 黄线 NC、白线 Digital Output；无官方 UIFlow2 unit 驱动 wrapper | 新增 GPIO id `op90`：白线数字输入观测 `input-level` + active-low `blocked` fixture | digital-level(bool rw)、blocked(bool ro)、input-events | **输出极性文档未给出 → unresolved（模型按 active-low）；PORT.B 主机限制（cores3/core2/stackchan 才有，atoms3r/sticks3/stopwatch 无）写死；IR 光学/遮挡物理 NOT RUN** |
| `rgb-led-10cm` A035 | 页面 `neopixel`：A035 10cm=15 颗 SK6812，PORT.B 黄线 LED Signal、白线 NC；无官方 UIFlow2 unit 驱动 wrapper | 新增 GPIO id `rgb-led-10cm`：黄线 RMT 捕获取 15 灯帧 | led-rgb[15]、led-frames、incomplete-frames、output-transitions | **PORT.B 主机限制写死；LED 光学/功耗/级联扩展 NOT RUN；无 UIFlow2 wrapper，15 灯数来自 A035 页面** |
| `8angle` U154 | 驱动 `unit/angle8.py`（快照=`9917a2a2…`，master 语义不同）：0x43、ADC12 0x00..0x0F、ADC8 0x10..0x17、BUTTON 0x20、RGB 0x30..0x53（9×4B R,G,B,bright）、FW 0xFE/ADDR 0xFF；页面 `8Angle`：STM32F030F4P6、SK6812-3535、8 电位器 + 8 RGB + 拨动开关 | 新增 `US_ANGLE8`：ADC12 int16le 读取、ADC8、switch、9 通道 RGB 写入/回读、fw/地址迁移 | adc12-raw[8]、adc8-raw[8]、switch-pressed、led-rgb[9]、fw-version、i2c-address | **电位器硬件/ADC 参考/开关机械 NOT RUN；0x43 无已登记冲突；SK6812 光学/功耗 NOT RUN** |
| `kmeter-iso-v11` U133-V11 | 驱动 `unit/kmeter_iso.py`（快照=master 逐字节相同 `59adfb9f…`）：0x66、温度 int32le/100（0x00/0x04/0x10/0x14）、ready 0x20、ASCII 字符串视图 0x30/0x40/0x50/0x60（1B 符号 + 8B 文本）、FW/ADDR；页面：STM32F030F4P6 + MAX31855KASA + CA-IS3641HW、-200..1350°C、14-bit 0.25°C | 新增 `US_KMETER`：int32le/100 C/F、内部温度、ready（0=就绪）、9 字节 ASCII 视图、fw/地址迁移 | thermocouple-temperature-c(-200..1350)、internal-temperature-c(-40..125)、data-ready、fw-version、i2c-address | **热电偶物理/冷端补偿/隔离/故障检测 NOT RUN；±2°C 精度与 -200..1350°C 量程 NOT RUN；0x66 无已登记冲突** |

## 离线 QOM smoke（S3 `m5atoms3r`，无 guest 固件）

```bash
cat > /tmp/unit-smoke-config6.json <<'JSON'
{"schema_version":1,"attachments":[
 {"id":"pbh1","unit_id":"pbhub-v11","pins":{"yellow":15,"white":16}},
 {"id":"op901","unit_id":"op90","pins":{"yellow":9,"white":10}},
 {"id":"rgb1","unit_id":"rgb-led-10cm","pins":{"yellow":21,"white":38}},
 {"id":"ang1","unit_id":"8angle","pins":{"yellow":17,"white":18}},
 {"id":"km1","unit_id":"kmeter-iso-v11","pins":{"yellow":5,"white":6}}]}
JSON
M5_UNIT_CONFIG=/tmp/unit-smoke-config6.json qemu-system-xtensa -M m5atoms3r \
  -L .work/M5StopWatch-QEMU/build/qemu/pc-bios -display none \
  -serial null -serial null -serial null \
  -qmp unix:/tmp/unit-smoke6.sock,server=on,wait=off
```

19 项检查全部 PASS：pbhub-v11 2（fw=2/地址/6 通道结构、输入写入）、op90 3（默认/
遮挡/释放 active-low）、rgb-led-10cm 2（15 灯、帧计数）、8angle 7（默认数组与身份、
ADC12/ADC8 写入、switch、范围/长度/只读拒绝）、kmeter 5（默认/温度写入/双向范围
拒绝/ready）。smoke **不**覆盖 I2C send/recv 字节语义（PbHub 通道命令、8Angle
ADC/RGB、KMeter int32/ASCII 视图）、RMT 帧、GPIO 输入时序；这些仍需 guest 证据。

## 计数

catalog 82 → **87** 款，runtime-profiles 82 → 87；visual mapping audit 5 条 +
`all-87-products` 标记；计数测试（test_unit_runtime / test_serve_api units /
visual mapping / batch3 A+B static marker）与 snapshot 已同步。

## 共同边界

5 款都是控制器可见的事务/时序模型，不是电气/光学/射频/热学物理模型；PORT.B
主机限制、0x61/0x43/0x66 冲突或空闲状态、firmware v1/v2 差异与极性 unresolved
必须随 catalog 一起读。没有 guest 与 Device Service 证据前不得升级为
`implemented`/`simulated`。

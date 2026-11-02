# Unit 第二批后 6 款（env/ameter/extencoder/ain4-20ma/acssr/gesture）虚拟设备证据

日期：`2026-11-02`。范围：把
[Unit 第二批协议研究](../../unit-research/2026-11-02-batch2-protocols.md) 中
`env`/`ameter`/`extencoder`/`ain4-20ma`/`acssr`/`gesture` 六款的 QEMU 数据面
（0126，含 0128/0129 两个必要修复）接入独立 Device Service，并记录
**虚拟设备**证据。物理硬件、市电、光学、机械与电流环语义全部 `NOT RUN`。

本页是验证证据，不定义当前能力；当前能力以
[项目当前状态](../../project-status.md) 为准，工作队列以
[项目 Backlog](../../project-backlog.md) 为准。所有结果只覆盖表内记录的主机、
固件 SHA、QEMU 二进制 SHA 和检查项，不转授未列组合。

## 安全边界（ACSSR）

`acssr` 证据**只覆盖 I2C 事务数据面**：继电器寄存器电平与 3 字节 RGB 写入
被模型观测。**它不是 AC 市电开关模型，不得据此宣称可切换市电负载**；
24–480V/10A 负载、过零检测、漏电流、隔离、寿命与任何市电安全结论都是
`NOT RUN`，无法从本证据推断。

## 结论

6 款各建 1 个可见 session，均在 guest 内运行参考固件自带的**原始冻结
UIFlow2 Unit 驱动**，经真实 SoC I2C 控制器读写，没有 host 端直写驱动返回值：

| Unit | 主机 / 端口 | 原始驱动类 | 会话 | 结果 |
| --- | --- | --- | --- | --- |
| `env` | atoms3r `custom` | `unit.ENVUnit(ENV_I)` | `c49a6e5b36954f83a37b7cd53689e29f` | PASS |
| `ameter` | sticks3 `custom` | `unit.AMeterUnit` | `df21d9cdeb4143ac85eca94914e3d1c4` | PASS |
| `extencoder` | cores3 `port-a` | `unit.ExtEncoderUnit` | `a729e8616f3b48ff8d3059afb130e2b5` | PASS |
| `ain4-20ma` | stopwatch `port-a` | `unit.AIN4_20MAUnit` | `95798c067826404a9e2f85063d3b9645` | PASS |
| `acssr` | atoms3r `custom` | `unit.ACSSRUnit` | `080e835212c24cd68de5a492a666ce04` | PASS |
| `gesture` | sticks3 `custom` | `unit.GestureUnit` | `267e96e699d044a3869f1631da4332ff` | PASS |

关键 controller-backed 观测（完整值见 `summary.json` 与 `report-<unit>.json`）：

- `env`（U001，双从机 0x5C DHT12 + 0x76 BMP280）：注入
  `temperature-c=25.5`/`humidity-pct=60.5`/`pressure-pa=100000` 后 guest
  `read_temperature()/read_humidity()/read_pressure()` 读回
  `25.5 / 60.5 / 1000.0`，QOM fixture 同步，双 slave 均产生事务。
- `ameter`（U086，ADS1115 0x48 + EEPROM 0x51）：注入 `current-a=1.0` 后 guest
  `get_current()`=0.9376（PGA-256 0.15626 A/LSB 量化，符合驱动）、
  `get_adc_raw()`=-6；EEPROM 校准记录可读，**写入被模型拒绝并计数**
  （`eeprom-writes=1`），产品页警告的“不要写校准 EEPROM”边界被保留。
- `extencoder`（U161，0x59）：注入 `counter=1234` 后 guest
  `get_rotary_value()`/`get_rotary_increments()`=1234；`set_perimeter(500)`、
  `set_pulse(20)`、`set_zero_mode(1)`、`set_zero_pulse_value(10)` 写入后
  `get_*` 读回 `500/20/1/10`；`reset_rotary_value()` 清零且 `reset-writes=1`；
  fw fixture=2、地址 0x59。
- `ain4-20ma`（U162，0x55）：注入 `adc-raw=2500`/`current-ma=12.5` 后 guest
  `get_adc_raw_value()=2500`、`get_current_value()=12.5`、fw=1、地址
  `0x55`；`set_cal_current(15)` 写入被接受。
- `acssr`（U139，0x50）：`on()/off()` 的继电器寄存器写入被
  `relay-level/relay-transitions` 观测（A→B 跳变 ≥2）；
  `fill_color(0x112233)` 写入被 `led-rgb=0x112233` 观测；fw=1、地址 0x50。
  **仅 I2C 事务数据面，不是市电开关模型。**
- `gesture`（U127，0x73 PAJ7620）：`GestureUnit` 构造期完成官方 219 项初始化
  写（`init-writes≥219`，part-id 校验通过）；注入 `gesture=64` 后
  `get_hand_gestures()`=64，注入 `gesture=256`（wave bit8）后=256，QOM
  `gesture` fixture 同步。

每个会话在停止前取得 evidence ZIP，停止使用 `purge=0` 并回读保留 history；
`manifest.json`、`serial.log`、`units/runtime.json`、`units/state.json`、
`units/contract.json` 均存在，帧为非空应用画面。

## 0128 / 0129 修复（0126 的两个真实模型 bug）

1. **0128 AMeter 校准 EEPROM 布局**：已合入 `0126` 用 `208 + gain*16` 填 6 条
   8 字节校准记录，但官方驱动按 `208 + gain*8`（`PAG_*_CAL_ADDR`）读取；
   PGA_256 记录因此为全零、CRC 仍自洽，驱动 `set_gain()` 在
   `expect/real = 0/0` 处 `ZeroDivisionError`，guest 无法构造 `AMeterUnit`。
   [`0128-unit-ameter-eeprom-layout.patch`](../../../patches/qemu-m5stack-peripherals/0128-unit-ameter-eeprom-layout.patch)
   改为驱动实际使用的 8 字节跨距（合成 factor 1.0 记录不变）。
2. **0129 batch-2b 写偏移 off-by-one**：`0126` 的 EXTENCODER/ACSSR 写解码用
   `write_pos - 1` 作为数据字节偏移，但 `control_send` 已为当前字节自增
   `write_pos`，导致首个数据字节被当作 offset 1：EXTENCODER 的 32-bit 写左移
   8 位（perimeter 500 变 128000）、`0x30` reset 被 NACK；ACSSR 的继电器/RGB
   写全部 NACK。 [`0129-unit-batch2b-write-offset.patch`](../../../patches/qemu-m5stack-peripherals/0129-unit-batch2b-write-offset.patch)
   改用 `write_pos - 2`。
   本目录证据都使用 0128/0129 修复后的运行时二进制。

## 固件与运行时来源

- 参考固件缓存（service 只读，不入 Git）：
  - atoms3r `…/atoms3r/uiflow2.bin` SHA-256
    `91c0f97c904271d4c47d240165fbf5589d44aa0d753ca17d685bfdce5bff199a`
  - sticks3 `…/sticks3/uiflow2.bin` SHA-256
    `c08196024019273ccadee9b4b3da303567f7ab206fa14edd1af283f04f6e98d8`
  - cores3 `…/cores3/uiflow2.bin` SHA-256
    `1324f12d3ddd5392f47a9eff537f9ce0b01a8e6e36d829b6bd22cdf82d2c1264`
  - stopwatch `…/stopwatch/uiflow2.bin` SHA-256
    `99d6482befe094de47bf68ce43618d3868bd62fb1fc72f0b55c0d0c2ea4e7f8d`
- 每个 case 的合并镜像 SHA-256 与探针 SHA-256 记录在
  [`summary.json`](summary.json) 和对应 `report-<unit>.json`。
- QEMU：canonical native layer `75f1d24`（`0109+0110…0119`）+ 已合入
  `0120/0121/0122/0123` + `0125` + `0126` + `0127` + `0128` + `0129`
  （`0124` StickT2 预留、本批不需要）；本批实际服务使用的
  `qemu-system-xtensa` SHA-256 见 `summary.json` 的
  `qemu.runtime_binary_sha256`。
- Device Service：独立端口 `127.0.0.1:8799`、独立 state dir 与 Bearer token；
  用户 `8787` 服务未被触碰。会话使用 `M5_SERVICE_FLASH_MODE=host-image`。

## 复现

```bash
# 1) QEMU 树：canonical + 0120/0121/0122/0123/0125/0126/0127/0128/0129，重建
#    （详见 patches README）；随后独立启动 Device Service：
M5_SERVICE_FLASH_MODE=host-image PYTHONPATH=platform/tools \
  python3.12 platform/tools/serve.py 8799 --bind 127.0.0.1 \
  --state-dir .work/unit-batch2b-service --api-token "$(cat .work/unit-batch2b-service.token)"

# 2) 逐款执行（每款一个可见 session）
export M5_SERVICE_API_TOKEN="$(cat .work/unit-batch2b-service.token)"
for pair in "atoms3r env" "sticks3 ameter" "cores3 extencoder" \
            "stopwatch ain4-20ma" "atoms3r acssr" "sticks3 gesture"; do
  set -- $pair
  PYTHONPATH=platform/tools python3.12 tests/units/run_batch2b_cases.py \
    --api-url http://127.0.0.1:8799 --device "$1" --case "$2" \
    --out-dir .work/unit-batch2b-evidence
done

# 3) 停止服务，保留历史（本批不提交 raw ZIP/帧）
```

## 未覆盖

- `env`：只建模 ENV-I；ENV-II/III/IV、传感器精度/自热、产品页 ±0.2/±0.5°C
  矛盾、DHT12 上电/校验细节与 BMP280 校准真实性 NOT RUN/unresolved。
- `ameter`：出厂校准为合成 factor 1.0；1% 精度/0.3mA 分辨率、增益/速率误差、
  EEPROM 保持、真实电流测量 NOT RUN；EEPROM 写入按产品页警告被拒绝并计数；
  guest 电流受 PGA-256 量化（1.0A→0.9376A）是驱动行为而非测量值。
- `extencoder`：meter 为合成且等于 counter；机械编码器运动、ABZ 脉冲时序、
  perimeter/zero 校准物理与掉电保持 NOT RUN；fw fixture 非真实 MCU。
- `ain4-20ma`：4-20mA 环电气/供电/负载/隔离/校准精度 NOT RUN；产品页
  0xF0 vs 0xFE/0xFF、12-bit vs raw16、STM32F030 vs STM32G030F 分歧 unresolved。
- `acssr`：**只验证 I2C 寄存器事务；不是 AC 市电开关模型**；24–480V/10A、
  过零、漏电流、隔离、寿命、Button/Modbus 模式与真实继电器触点行为 NOT RUN。
- `gesture`：IR 光学、手势识别、环境光免疫、距离、120/240Hz 时序 NOT RUN；
  产品页无寄存器表、datasheet 未读、驱动 low-rate bug；flags 为合成 fixture。
- 每款只回放表中主机；其它主机/固件、Web bridge、真机全部 NOT RUN，不转授
  未列组合。
- Raw `result.json`、`serial.log`、`frame.png` 与 evidence ZIP 保存在本地
  git-ignored `.work/unit-batch2b-evidence/`；提交内容仅为
  [`summary.json`](summary.json) 与本目录 `report-*.json` 摘要。

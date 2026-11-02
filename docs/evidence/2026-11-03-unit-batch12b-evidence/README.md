# Unit batch-12b 7 款 I2C driver-gap Unit guest 证据

日期：`2026-11-03`。范围：`bmm350`、`ina226-10a`、`ina226-1a`、`roller485`、
`roller485-lite`、`rollercan`、`rollercan-lite`——7 款已有 QEMU 模型但仍是
planned 的 driver-gap Unit。本批 **7/7 PASS**，不做硬件验证。

本页是验证证据，不定义当前能力；当前能力以
[项目当前状态](../../project-status.md) 为准。

## 关键点

| 项 | 值 |
| --- | --- |
| QEMU 源码状态 | canonical `75f1d24` native 层 + reconciled **39 层 Unit 链**（`0120`–`0159`，含 `0156`/`0157`/`0158`/`0159`；`0155` 未用） |
| 运行时二进制 SHA-256 | `69ebd3cb213750918869b1aa29d19fcac1fe004dba4022bccda6a2ba6610847d` |
| 参考固件 | cores3 `platform/.cache/firmware/cores3/uiflow2.bin`（SHA-256 `1324f12d…2c1264`） |
| Device Service | 独立 `127.0.0.1:8805`（独立 state/token，`M5_SERVICE_FLASH_MODE=host-image`）；未使用 8799/8801/8802/8803，未触碰 8787 |
| guest 路径 | **无官方 Unit 驱动（driver-gap）→ 参考固件 `machine.I2C` 原始寄存器探针** |
| 模型修复 | **本批未发现模型 bug，未创建 0160 补丁** |
| 结果 | 7 PASS / 0 BLOCKED；catalog `model_status=partial`，profile 升 `implemented` + `hosts:["cores3"]` |

**driver-gap caveat**：这 7 款产品没有官方 UIFlow2 Unit 驱动（batch-11 研究已记录），
因此 guest 证据是参考固件里的 raw `machine.I2C` 事务探针，不是官方驱动路径。
PASS 只覆盖模型寄存器语义与 QOM fixture 一致性；磁力/heading/OTP、隔离/精度/
保险/热、FOC 电机/编码器物理、RS485/CAN 帧层与全部电气行为 **NOT RUN**。

## 结论（7/7 PASS）

| Unit | 地址 | guest 路径 | 独立 session 原因 | 结果 |
| --- | --- | --- | --- | --- |
| `bmm350` | 0x14 | raw I2C 读 CHIP_ID/PMU/MAG+TEMP，按 datasheet §9.2.3 读 `size+2` 并丢弃前 2 个 dummy 字节 | — | PASS |
| `ina226-10a` | 0x41 | raw I2C 读 ID/config/calibration/shunt/bus/current/power + cal 写回读 | 与 1A 同地址 | PASS |
| `ina226-1a` | 0x41 | 同上（1A 80 mΩ / cal 0x0800） | 与 10A 同地址 | PASS |
| `roller485` | 0x64 | raw I2C 读 product id/FW/addr/状态/编码器/速度/位置/电流/VIN/温度；写 mode/目标速度/目标位置/save | 与另外 3 款同地址 | PASS |
| `roller485-lite` | 0x64 | 同上（product id 0x01） | 0x64 互斥 | PASS |
| `rollercan` | 0x64 | 同上（product id 0x02） | 0x64 互斥 | PASS |
| `rollercan-lite` | 0x64 | 同上（product id 0x02） | 0x64 互斥 | PASS |

每个 case 一个独立 host/session：0x41 两款、0x64 四款在同一总线上互斥，
不会同 session 挂载；每例先取 evidence ZIP，再 `purge=0` 停止并验证 history。

## 关键观测

### bmm350（0x14，Bosch BST-BMM350-DS001-27 Table 8 / §9.2.3）

guest 先 `readfrom_mem(0x14, reg, n+2)` 再切片 `[2:]`：

- CHIP_ID `raw=000033` → `0x33`；
- MAG X/Y/Z 24-bit raw = `14144 / -7072 / 3484`，与 QOM fixture
  `magnetic-x=100.0 / magnetic-y=-50.0 / magnetic-z=25.0 µT` 按驱动系数
  `0.007069979 / 0.007174964` 反算完全一致；
- TEMP raw `51453` ↔ QOM `temperature-c=25.0`（`raw*0.000981282-25.49`）；
- `0x55` OTP_STATUS 读回 1（otp_cmd_done fixture）。
- **两个 dummy 字节语义被真实 guest 读事务验证**：若偏移错位，payload raw 会与
  QOM 反算值不一致，本 case 会失败。

### ina226-10a / ina226-1a（0x41，TI SBOS547C Table 7-1）

10A（5 mΩ，cal `0x0C80`，bus=12.0 V，current=2.0 A）：

- manufacturer `0x5449`、die `0x2260`、config `0x4127`、cal `3200`；
- shunt raw `4000`（2.0 A × 5 mΩ / 2.5 µV）、bus raw `9600`（12 V / 1.25 mV）、
  current raw `6250`（current_lsb=3.2e-4 A）、power raw `3000`（power_lsb=8 mW）；
- cal 写回读 `3200`；QOM `power-w=24.0` 与 fixture 乘积一致。

1A（80 mΩ，cal `0x0800`，bus=5.0 V，current=0.5 A）：

- calibration `2048`；shunt raw `16000`、bus raw `4000`、current raw `16000`
  （current_lsb=3.125e-5 A）、power raw `3200`；cal 写回读 `2048`。
- frozen 驱动注释写 `0x811` 而代码写 `0x0800`；本模型按代码路径实现，guest
  读到的 cal 与代码/文档默认值一致（该注释冲突已在 catalog blocker 记录）。

### roller485 / roller485-lite / rollercan / rollercan-lite（0x64）

guest 读：product id（0x01/0x02）、FW=3、I2C addr=0x64、state=0、error=0、
encoder=0、VIN raw=1200、temp raw=30、actual speed/position/current raw=0、
target speed raw=0（初始模式 1 = speed）。

guest 写：`0x01=2`（位置模式）、`0x40=150000`（1500.00 rpm）、
`0x80=9000`（90.00° legacy position）、`0xF0=1`（保存）后：

- 读回 `mode=2`、`target speed=150000`、`target pos=9000`；
- QOM `mode=2`、`target-speed-rpm=1500.0`、`target-position-deg=90.0`、
  `save-count=1` 与 guest 写一致；QOM 默认值（encoder/vin/temp/actual/
  current/fault/address）与 guest 读一致。
- product id 区分家族：Roller485 系列 `0x01`，RollerCAN 系列 `0x02`。
- RS485/CAN 帧层与 FOC 电机/编码器闭环物理 **NOT RUN**。

## 边界

- 全部为 virtual-device validation，不是硬件 PASS；无光学/磁力/电气/机械测量。
- 无官方 Unit 驱动：guest 是 raw `machine.I2C` 寄存器探针，PASS 不能外推到
  官方驱动 API 行为；产品物理量（µT、A、rpm、°、温度）仅 fixture 映射。
- 0x41 与 0x64 地址互斥：每个 case 使用独立 session，模型只验证单节点总线行为。
- 磁力/heading/OTP 校准、隔离/精度/自恢复保险/热、FOC 电流/速度/位置环、
  RS485/CAN 电气/帧层/仲裁、6–16V 供电全部 `NOT RUN`。
- 原始 ZIP/帧/串口日志留在本地 ignored `.work`；仓库只提交摘要、哈希、
  session sha256 和复现命令。

## 复现

```bash
M5_SERVICE_FLASH_MODE=host-image \
M5_QEMU_XTENSA="$PWD/.work/native-lock-source/qemu/build/qemu-system-xtensa" \
M5_QEMU_XTENSA_ROM_DIR="$PWD/.work/native-lock-source/qemu/build/pc-bios" \
  PYTHONPATH=platform/tools python3.12 platform/tools/serve.py 8805 \
  --bind 127.0.0.1 --state-dir .work/unit-batch12b-service \
  --api-token "$(cat .work/unit-batch12b-service.token)"

export M5_SERVICE_API_TOKEN="$(cat .work/unit-batch12b-service.token)"
PYTHONPATH=platform/tools python3.12 tests/units/run_batch12b_cases.py \
  --api-url http://127.0.0.1:8805 --case <unit> --out-dir .work/unit-batch12b-evidence
```

每 session：构建含 probe 的 cores3 参考固件 → 创建可见会话（单 Unit attachment
port-a；0x41/0x64 每例独立）→ 等 `BATCH12B_PROBE_READY` 与 case END 标记 →
读 QOM/串口/frame → 取 evidence ZIP → `purge=0` 停止并核对 history。
raw 产物在 `.work/unit-batch12b-evidence/<unit>/`（ignored），提交的
`report-*.json` 只含摘要、哈希与有界样本。

# Unit batch-12b 实现状态：10 款 driver-gap 模型层（0158）

日期：`2026-11-03`。范围：batch-11 官方协议研究中 10 款 driver-gap Unit 的
**最小 QEMU 数据面模型**，作为 patch `0159-unit-batch12b.patch` 落地
（reconcile11 后的 canonical 39 层链，`0159` 为第 39 层）：

`bmm350`、`ina226-10a`、`ina226-1a`、`roller485`、`roller485-lite`、`rollercan`、
`rollercan-lite`、`8servos2-chain`、`chainbus`、`cat1-cn`。

本批**只实现文档已公开的寄存器/帧子集**；模型初落地时 10 款 catalog 为
`partial`、runtime profile 全部 `planned` + `hosts: []`。后续 batch12b guest 证据
任务为其中 7 款 I2C Unit（bmm350/ina226×2/roller×4）采集了 raw `machine.I2C`
probe PASS 并升 `implemented`（见 §8 与
[evidence](../evidence/2026-11-03-unit-batch12b-evidence/README.md)）；Chain/Cat1
3 款仍保持 planned。**本页主体不是 functional PASS，也不是 I2C/UART 事务级验证。**

> **历史时点页**：本页记录 batch-12b 模型初落地时点（canonical 39 层、Chain/Cat1
> 仍 planned、7 款 I2C 待证据）。后续 batch-12b 证据已升 7 款 I2C、batch-12c
> 证据已升 Chain/Cat1；最终 canonical 为 **41 层**（0120–0161）。当前能力以
> [项目状态](../project-status.md)和[战役汇总](../evidence/2026-11-03-visual-campaign-summary/README.md)
> 为准，正文保留初落地时点的设计/边界记录。


## 1. 环境与构建

- worktree：`/Users/m5agent/Documents/ChatGPT/esp-emulator-units29`
  （分支 `m5agent/units29`，base `origin/main` `067db249`）。
- QEMU 源：本 worktree 的本地忽略目录 `.work/native-lock-source/qemu`
  （pinned `espressif/qemu` 基础 + canonical native 层 + Unit 层到 `0156`；
  `0157` 留给并行 batch-12a，本分支没有 `0157`）。
- `0159` 是 0120 之后的第 **39** 层（`0158` 为第 38 层；本层 base 是含
  `0156`/`0157`/`0158` 的 38 层链）。三文件变更：
  `hw/m5stopwatch/m5_unit_i2c_sensors.c`、`hw/m5stopwatch/m5_unit_i2c_controls.c`、
  `hw/m5stopwatch/m5_unit_gpio.c`。
- 补丁 SHA-256：`084f34e20cf3ffdb94935e165ed5cd4462e28dbb3490f29a1853e692a1a0f547`；
  `git apply --check` 在 38 层链末端验证通过，应用后 3 个文件与生成树逐字节一致。
- 删除 `build/` 后重新 configure（`--target-list=xtensa-softmmu --enable-gcrypt
  --enable-slirp --disable-docs --disable-werror ...`，使用
  `esp-emulator/.work/unit-runtime-build` 的 venv 与静态 deps），
  `ninja -j8 qemu-system-xtensa`；构建后 `xattr -c` + `codesign -s - --force`。
- 二进制：`qemu-system-xtensa`（QEMU 9.2.2），SHA-256
  `69ebd3cb213750918869b1aa29d19fcac1fe004dba4022bccda6a2ba6610847d`
  （39 层链 + 本批证据任务重建；模型层本身的单元测试见 §7）。
- 本页模型层工作时未启动 Device Service；后续 guest 证据任务使用独立 `127.0.0.1:8805`（见 §8），未涉及 8787/8799/8801/8802/8803/8831。

## 2. 模型实现内容

### 2.1 I2C 传感器层（`m5_unit_i2c_sensors.c`）

| Unit | 地址 | 实现 |
| --- | --- | --- |
| `bmm350` (U231) | `0x14` | Bosch BST-BMM350-DS001-27 Table 8 寄存器文件：`0x00` CHIP_ID=0x33、`0x04/0x05/0x06` PMU、`0x31-0x3C` MAG X/Y/Z + TEMP 24-bit、`0x50/0x52/0x53/0x55` OTP、`0x7E` CMD。**读事务严格按 §9.2.3 返回 2 个 dummy 字节再给数据**（镜像 frozen 驱动 `readfrom_mem(reg, size+2)[2:]`）。 |
| `ina226-10a` (U200) | `0x41` | TI SBOS547C Table 7-1 16-bit big-endian 寄存器文件：`0x00` config（POR 0x4127）、`0x01` shunt、`0x02` bus、`0x03` power、`0x04` current、`0x05` calibration、`0x06` mask、`0x07` alert、`0xFE/0xFF` ID。Bus/shunt/current/power 由 `bus-voltage-v`/`current-a` fixture 与 guest 写入的 calibration 反算；10A 参数 shunt=5 mΩ、默认 cal=0x0C80。 |
| `ina226-1a` (U200-1A) | `0x41` | 同一寄存器文件，1A 参数 shunt=80 mΩ、默认 cal=0x0800。frozen 驱动注释写 `0x811` 而代码写 `0x0800`，本模型按**代码路径**实现并在 catalog blocker 标冲突。 |

fixtures：`magnetic-x/y/z`、`temperature-c`、`whoami`、`bus-voltage-v`、`current-a`、
`power-w`、`manufacturer-id`、`die-id`、`i2c-address`（power 由 fixture 派生，只读）。

### 2.2 Roller 家族 I2C 子集（`m5_unit_i2c_controls.c`）

`roller485` / `roller485-lite` / `rollercan` / `rollercan-lite`：I2C `0x64`
寄存器文件子集（按 M5Unit-Roller485-Internal-FW V2.2 / RollerCAN V3.1）：

- `0x00` 电机输出、`0x01` 模式 1–4、`0x0A` 位置范围保护、`0x0B` 解除堵转、
  `0x0C` 系统状态、`0x0D` 错误位、`0x0E` 按键切换、`0x0F` 堵转保护；
- `0x10-0x12` 家族配置（Roller485: RS485 ID/波特率；RollerCAN: CAN ID/波特率；
  两者都含 RGB 亮度）、`0x20-0x23` 位置环最大电流、`0x30-0x33` RGB(B/G/R+mode)；
- `0x34-0x3F` VIN/温度/编码器计数；`0x40-0x43` 速度目标；`0x50-0x53` 速度环电流；
  `0x60-0x63` 实际速度；`0x70-0x7B` 速度 PID；`0x80-0x9D` 旧/扩展位置；
  `0xA0-0xAB` 位置 PID；`0xB0-0xC3` 电流目标/实际电流；
- `0xE0-0xEB` UID（固定 fixture）、`0xF0` 保存、`0xF1-0xF3` 编码器校准、
  `0xF4` 产品设备 ID（Roller485=0x01 / RollerCAN=0x02）、`0xFE` 固件版本=3、
  `0xFF` I2C 地址（写后 `i2c_slave_set_address`，0x08–0x77，冲突则 NACK）。

QOM fixtures：`motor-output`、`mode`、`system-state`、`fault`、`encoder-pos`、
`target-speed-rpm`、`actual-speed-rpm`、`target-position-deg`、`actual-position-deg`、
`current-ma`、`vin-v`、`mcu-temp-c`、`i2c-address`、`save-count`。
RS485/CAN 帧层、FOC 电机/编码器闭环物理 NOT RUN。

### 2.3 UART Chain / AT responder（`m5_unit_gpio.c`）

- `8servos2-chain` (U223，设备类型 `0x000C`)：AA55 帧级 responder
  （`AA 55 len index cmd data crc 55 AA`，CRC=(index+cmd+data)&0xFF），实现
  docs U223 协议页的 `0x10-0xFE` 子集：模式/上下拉/输入输出电平/ADC(8×u16)/
  舵机角/PWM/TIM 频率/RGB 配置与缓冲/参考-Grove-DC 电压/系统电流/UID/版本/
  设备类型/枚举/心跳/数量。QOM：`channel-modes`、`servo-angles`、`adc-values`、
  `rgb-leds`、`current-ma`、`frames-sent`、`frames-injected`。
- `chainbus` (U212，设备类型 `0x0006`)：同一 AA55 帧层；实现 GPIO 输出/输入、
  ADC、RGB、工作状态、设备信息/枚举/心跳/数量。**I2C 转发命令（0x10–0x15）在
  没有下游设备时 fail-closed**（0x10 初始化成功，0x11–0x14 返回
  Operation_status=0，0x15 返回成功+0 地址），不伪造转发字节。
  QOM：`chain-uid`、`version`、`link-devices`、`heartbeat`、`i2c-address`、
  `gpio-levels`、`adc-values`、`frames-sent`、`frames-injected`。
- `cat1-cn` (U204)：ML307R-DL 最小 AT 命令/响应字节 responder，覆盖
  `AT`/`ATE0`/`AT+CPIN?`/`AT+CREG?`/`AT+CEREG?`/`AT+CSQ`/`AT+CGATT?`/
  `AT+CGMM`/`AT+CGMI`/`AT+CGSN`/`AT+CIMI`/`AT+MIPCALL`/`AT+MIPOPEN`/
  `AT+MIPSEND`/`AT+MIPCLOSE`/`AT+MIPRD`/`AT+MDNSGIP`，未知命令回 `ERROR`；
  身份值为合成 fixture。QOM：`responses-hex`（通用 override）、`tx-hex`、
  `frames-sent`、`frames-injected`。
- 级联拓扑、舵机/PWM/WS2812 波形、9–24V/INA199、蜂窝 RF/SIM/PDP/网络/TLS/
  MQTT、真实 socket 语义 NOT RUN。

## 3. 离线 QOM smoke（非 functional PASS）

在 `m5cores3` machine（无 guest 固件）用 `M5_UNIT_CONFIG` attach 10 个 Unit，
通过 QMP `qom-list`/`qom-get`/`qom-set` 检查：

- 10/10 attach；`runtime.properties` 中全部属性可 `qom-get`；
- 可写 fixture 写入后读回一致（magnetic-x/temperature-c/ina bus+current/
  roller mode+target/chain channel-modes+adc/chainbus uid+gpio+adc/cat1
  responses-hex）；
- 只读属性写入被拒绝（roller `fault`、bmm350 `whoami`）；
- 派生读回：`power-w=bus*current`、`i2c-address`（0x14/0x41/0x64）、
  chainbus `version`/`link-devices`、8servos2-chain `servo-angles`、cat1 `tx-hex`；
- 结果：**152/152 property checks PASS**。

该 smoke **不驱动 I2C/UART 控制器**，因此不证明寄存器读事务、dummy 字节、
Chain CRC/命令响应或 AT 字节流；这些仍待 guest 证据。

## 4. 每款状态（实现 vs 仅登记）与边界

| Unit | 状态 | 模型内容 | 仍 NOT RUN / 边界 |
| --- | --- | --- | --- |
| `bmm350` | partial model / **implemented profile（guest PASS）** | I2C 0x14 寄存器文件 + 2 dummy 字节读 + MAG/TEMP fixture | 磁场/航向/OTP 校准/温度补偿/量程噪声；0x14 与 DoF9/DoF10 冲突 |
| `ina226-10a` | partial / **implemented（guest PASS）** | I2C 0x41 8 寄存器 + 10A 校准 | 隔离/0-30V/±10A/精度/保险/热；0x41 与 1A 版冲突 |
| `ina226-1a` | partial / **implemented（guest PASS）** | 同上 + 1A 校准（注释 0x811 vs 代码 0x0800 已记录） | 隔离/精度/保险/热；0x41 共用 |
| `roller485` | partial / **implemented（guest PASS）** | I2C 0x64 寄存器子集（0x00-0xFF 关键块） | RS485 帧层、FOC 电机/编码器物理、6-16V/滑环/OLED/RGB/热；0x64 四款互斥 |
| `roller485-lite` | partial / **implemented（guest PASS）** | 同族寄存器子集 | RS485/Lite 硬件差异/电机物理；0x64 互斥 |
| `rollercan` | partial / **implemented（guest PASS）** | I2C 0x64 寄存器子集（设备 ID 0x02） | CAN 帧层/电气、FOC 电机物理、6-16V/OLED/RGB/热；0x64 互斥 |
| `rollercan-lite` | partial / **implemented（guest PASS）** | 同族寄存器子集（设备 ID 0x02） | CAN/Lite 差异/电机物理；0x64 互斥 |
| `8servos2-chain` | partial / planned | AA55 帧级 responder（0x000C 子集） | 级联拓扑、舵机/PWM/WS2812 波形、9-24V/INA199/热 |
| `chainbus` | partial / planned | AA55 帧级 responder（0x0006 子集），I2C 转发 fail-closed | 拓扑、真实转发时延/下游设备、GPIO/NVIC 电气时序 |
| `cat1-cn` | partial / planned | 最小 AT 命令/响应字节 responder | 蜂窝 RF/频段/天线、SIM 鉴权、网络注册/PDP、TLS/HTTP/MQTT、真实 socket、URC 逐条核对 |

> 7 款 I2C Unit 已有 guest raw `machine.I2C` 证据并升 implemented（§8）；
> `8servos2-chain`/`chainbus`/`cat1-cn` 3 款仍无 guest 证据，profile 保持
> planned + 无 hosts。catalog 全部保持 `partial`（只表示有最小模型，不是硬件 PASS）。

## 5. 已知模型策略/未确认点

- **BMM350 dummy bytes**：读事务先回 2 个 0x00 再回寄存器数据，模拟 datasheet
  §9.2.3 与 frozen `readfrom_mem(reg, size+2)[2:]`；OTP 字全 0（sensitivity 1.0、
  offset 0），不声称真实校准。
- **INA226**：`calibration` 由 guest 写入后参与 `current_lsb=0.00512/(cal*shunt)`、
  `power_lsb=25*current_lsb` 的换算；1A 版注释/代码冲突按代码路径建模，未用注释值。
- **Roller**：写入按协议块逐字节接受；多字节小端字段在写完后由寄存器镜像解码，
  不做“未写字节”的猜测；读地址映射按协议文档。RS485/CAN 帧未实现，因此
  `RS485/CAN 模式互斥` 只作为寄存器配置位存在。
- **Chain**：CRC 帧级解析；非法头/CRC/长度帧丢弃且不响应；`0xFC` 枚举不响应；
  `0xFE` 只返回 1 个设备（单节点模型）；ChainBus I2C 转发 fail-closed。
- **Cat1-CN**：ATE 回显关闭/身份/注册/信号均为合成固定值；`AT+MIPSEND` 的
  `>` 提示与数据阶段未建模，真实 socket 数据不流动。
- 物理/电气/光学/RF/机械/热/电机/FOC/蜂窝语义不因本层改变。

## 6. 复现

```bash
# 1) 源树：.work/native-lock-source/qemu（base 含 0156/0157/0158 的 38 层链），应用 0159
git apply --check patches/qemu-m5stack-peripherals/0159-unit-batch12b.patch
# 2) 重建（本 worktree）
V=../esp-emulator/.work/unit-runtime-build/venv
D=../esp-emulator/.work/unit-runtime-build/deps
rm -rf .work/native-lock-source/qemu/build && mkdir -p .work/native-lock-source/qemu/build
# 见 §1 的 configure flags；ninja -j8 qemu-system-xtensa
# 3) 离线 QOM smoke（无 guest）
M5_UNIT_CONFIG=/tmp/unit-smoke12b.json .work/native-lock-source/qemu/build/qemu-system-xtensa \
  -M m5cores3 -L .work/native-lock-source/qemu/build/pc-bios -display none \
  -serial null -serial null -serial null \
  -qmp unix:/tmp/unit-smoke12b.sock,server=on,wait=off
```

smoke 配置包含 10 个 attachments（BMM350/INA226×2 用不同引脚对避免 0x41 冲突；
四款 Roller 各用独立引脚对避免 0x64 冲突；UART 三款用独立 UART/GPIO 引脚对）。
原始日志/脚本留在本地忽略目录，不提交。

## 7. 验证

- patch `git apply --check` 通过（reconcile11 后 38 层链末端）；应用后三文件逐字节一致。
- 离线 QOM smoke 152/152 property checks PASS（非 guest、非事务级）。
- 全量测试：`Ran 1902 tests ... OK (skipped=10)`；四 check：`RUNTIME_COVERAGE_OK` /
  `PERIPHERAL_CATALOG_OK` / `QEMU_PROFILES_OK` / `PROJECT_SNAPSHOT_OK`；
  `check_pr_scope.py --base origin/main --head HEAD` 结果见同 commit 报告（本页
  不重复动态计数，以 `project-snapshot.md` 为准）。

## 8. 后续：batch12b guest 证据更新（2026-11-03）

后续证据任务在 `m5agent/units31`（base `7af78317`，reconciled 39 层链）上用
独立 Device Service（`127.0.0.1:8805`，host-image，未触碰 8787/8799/8801/
8802/8803）为 **7 款 I2C Unit** 采集 guest 证据：`bmm350`、`ina226-10a`、
`ina226-1a`、`roller485`、`roller485-lite`、`rollercan`、`rollercan-lite`。

- **无官方 Unit 驱动（driver-gap）→ guest 使用 raw `machine.I2C` 寄存器探针**；
  BMM350 按 datasheet §9.2.3 读 `n+2` 字节并丢弃前 2 个 dummy 字节；
- 0x41 两款、0x64 四款地址互斥 → 每款一个独立可见 session；
- **7/7 PASS**：寄存器 raw 与 QOM fixture 精确一致，Roller 写路径（mode/
  target speed/position/save）QOM 回读一致；未发现模型 bug，**没有创建 0160
  修复补丁**；
- 通过后 7 款 profile 升 `implemented` + `hosts:["cores3"]` +
  `virtual_device_evidence`（report/evidence/firmware/runtime hashes、
  session sha256、39 层 patch 列表）；catalog 保持 `partial`（只升模型验证，
  不是硬件 PASS）；
- 仍 NOT RUN：磁力/heading/OTP 校准、隔离/精度/保险/热、FOC 电机/编码器物理、
  RS485/CAN 帧层与电气、6–16V 供电；`8servos2-chain`/`chainbus`/`cat1-cn`
  3 款仍保持 planned（UART 链/AT 未在本批取证）。

证据与复现见
[Unit batch-12b 7 款 I2C driver-gap Unit guest 证据](../evidence/2026-11-03-unit-batch12b-evidence/README.md)。

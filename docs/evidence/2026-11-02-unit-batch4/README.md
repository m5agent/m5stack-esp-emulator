# Unit 第四批 12 款（A+B 6 款 / C 6 款）虚拟设备证据

日期：`2026-11-02`。范围：把
[Unit 第四批协议研究](../../unit-research/2026-11-02-batch4-protocols.md) 的全部
12 款 Unit 数据面通过**独立 Device Service**的可见 `/api/v1` 会话记录为
**虚拟设备**证据。物理硬件、机械、光学、声学、电气、射频与市电语义全部
`NOT RUN`。

本页是验证证据，不定义当前能力；当前能力以
[项目当前状态](../../project-status.md) 为准，工作队列以
[项目 Backlog](../../project-backlog.md) 为准。所有结果只覆盖表内记录的
主机、固件 SHA、QEMU 二进制 SHA 和检查项，不转授未列组合。

## 关键点：单一 QEMU 构建

`0134`（A+B 6 款）与 `0136`（C 6 款）都基于同一棵
`canonical 75f1d24 + 0120…0129 + 0131` 树，可顺序 apply，因此本批只需要
**一个** QEMU 构建；不需要 batch3 的 A+B/C 双树并行层。

| 项 | 值 |
| --- | --- |
| QEMU 源码状态 | canonical `75f1d24` + 0120/0121/0122/0123 + 0125/0126/0127/0128/0129 + **0131 + 0134 + 0136 + 0137（本轮证据修复）** |
| QEMU 树 | `.work/native-lock-source/qemu` |
| 运行时二进制 SHA-256（签名部署副本） | `a06eb87ce1bb6f1171a18144e6db9c769b63a6b026e3ed680a25eaaa4f9421d2` |
| 构建产物 SHA-256（unsigned 构建） | `1ae4d2cea473421dfc527e77a727caa51ddcc9d39ff1902bb924e8c41e99cb82` |
| 参考固件 | cores3 `platform/.cache/firmware/cores3/uiflow2.bin`，SHA-256 `1324f12d…` |
| Device Service | 独立 `127.0.0.1:8799`、独立 state/token、`M5_SERVICE_FLASH_MODE=host-image`；用户 `8787` 未触碰 |

## 证据修复（本轮发现）

`0138-unit-batch4-evidence-fixes.patch` 是本轮证据发现的模型修复，base 为
`canonical + 0120…0129 + 0131 + 0134 + 0136` 树：

| 根因 | 影响 | 修复 |
| --- | --- | --- |
| `0136` AC Measure：6 个 fixture 只写入 `values[]`，从未同步到 `ac_voltage/ac_current/...` 视图字段；ASCII 视图还用 `reg & 0x0f` 当读偏移（0x00/0x40 都变成 0），每个字节都返回首字符 | 修复前 guest 的 ASCII 读数全是空格/`1111`、byte 视图全 0；ac-measure 证据失败 | `sensor_update()` 每次访问从 `values[]` 派生视图；ASCII 读取改用读事务内 `pos`；提供无需浮点 printf 的定点格式化 |
| `0136` Weight：HX711 pad observer 在 pad dispatch 内调用 `esp32_gpio_set_input()`，触发 GPIO 控制器 `!g_pad_dispatch_depth` 断言，QEMU exit `-6` | 修复前 weight 证据进程直接 abort | 新增 `esp32_gpio_set_input_deferred()`（只更新外部输入电平、不重入 pad 派发）；Weight 位脉冲在 observer 内改用 deferred API，`hx_finish_conversion()` 同步调整 |
| `0136` DDS：`set_freq_phase()/quick_output()` 的 6 字节连续 burst 在 0x30 只接受前 4 字节，phase 字节被 NACK；读快照 0x34 频点/相位布局重叠 | 组合 API 路径不可用 | **不在本轮修复**：证据改用驱动公开的 `set_freq()/set_phase()/set_mode()/set_ctrl()` 分段路径；burst 与快照布局作为 unresolved 记录（见下） |

修复后的二进制用于**全部 12 个 session**（不只重跑受影响的两款），因此所有
report 的 `runtime_binary_sha256` 一致。

## 结论

12 款各建 1 个可见 session，均在 guest 内运行参考固件自带的**原始冻结
UIFlow2 Unit 驱动**，经真实 SoC GPIO/ADC/RMT/UART 或 I2C 控制器读写，没有
host 端直写驱动返回值：

| Unit | 批次/主机/端口 | 原始驱动类 | 结果 |
| --- | --- | --- | --- |
| `rs485-iso` | A+B / cores3 port-a | `RS485Unit(uSerial/Modbus master)` | PASS |
| `laser-tx` | A+B / cores3 port-a | `LaserTXUnit`（GPIO DIN） | PASS |
| `co2l` | A+B / cores3 port-a | `CO2LUnit(CO2Unit/SCD41)` | PASS |
| `neco` | A+B / cores3 port-a | `NECOUnit(WS2812+Button)` | PASS |
| `midi` | A+B / cores3 port-a | `MIDIUnit(SAM2695)` | PASS |
| `tof4m` | A+B / cores3 port-a | `TOF4MUnit(VL53L1X)` | PASS |
| `weight` | C / cores3 port-a | `WeightUnit`（HX711 位脉冲） | PASS |
| `bldc-driver` | C / cores3 port-a | `BLDCDriverUnit` | PASS |
| `ac-measure` | C / cores3 port-a | `AC_MEASUREUnit` | PASS |
| `dds` | C / cores3 port-a | `DDSUnit(AD9833)` | PASS |
| `gps` | C / cores3 port-a | `GPSUnit`（NMEA） | PASS |
| `uhf-rfid` | C / cores3 port-a | `UHFRFIDUnit(JRD4035)` | PASS |

**端口替换说明**：官方 PinMap 把 GPIO/RMT 单元放在 PORT.B、UART 单元放在
PORT.C，但当前 host-port 注册表只把 `cores3/PORT.A` 作为 main-device 端口
准入（PORT.B/PORT.C 均标记为 accessory-or-configuration-dependent 或限定
8Servos），因此全部 session 使用 `cores3 PORT.A` 的 GPIO 2/1 作为 harness
接线。guest 驱动的 SoC GPIO/RMT/UART 控制器路径仍真实执行，但**产品连接器
的 PORT.B/C 物理接线本身未被验证**；每个 report 的
`official_port`/`runtime_port_substitution` 字段记录此差异。

关键 controller-backed 观测（完整值见 `summary.json` 与 `report-<unit>.json`）：

- `rs485-iso`：guest `write(b"HELLO")` → QOM `tx-hex=48454c4c4f`；注入
  `rx-hex=4d4f44425553` 后 guest `any()/read()` 收到 `MODBUS`；
  `read/written-bytes` 增长、无 I2C 事务。**冻结 `RS485Unit` 包装器构造函数
  不兼容固件 `uSerial` 签名（TypeError）**，证据回退到同一官方 `uSerial`
  驱动的 `_mdbus_uart` 数据面并记录 fallback。
- `laser-tx`：guest `on/off/on/off` → QOM `output-level` 最终 0、
  `output-transitions≥3`；**只有 GPIO DIN 电平**，不宣称任何光学输出。
- `co2l`：注入 1234 ppm/60.5 %RH → guest `co2=1234`、`humidity=60.5`；
  QOM `chip-id=0x41`、`serial-number=0x12345678`；温度解码 bug 如实记录，
  `get_serial_number()` 因缺少 0132 三字序列号修复而报错，作为 boundary。
- `neco`：`NECOUnit(...,35)` 写入 5 灯 0x112233 → QOM 35 灯帧逐灯一致、
  `led-frames≥1`、无 incomplete；驱动默认 70 灯 vs 页面 35 灯冲突保留。
- `midi`：`set_note_on/off + set_instrument` → QOM `tx-hex`
  `903c64803c00b00000c005`；SAM2695 音频合成 NOT RUN。
- `tof4m`：初始化序列通过；guest `get_model_info=(234,204,16)`、
  `get_data_ready=1`、`get_distance=1000`；QOM range-status=9、
  clear-writes≥1；4m/激光/光学 NOT RUN。
- `weight`：QOM `adc-raw=123456` → guest `get_raw_weight=8635520`
  （驱动 `(raw<<1)^0x800000` 变换）、QOM conversions≥1、ready-level 恢复；
  HX711 电气/10SPS/称重力学 NOT RUN。
- `bldc-driver`：guest 写 mode/direction/model/pole-pairs/pwm/rpm/pid 并读回；
  QOM mode=1、direction=1、poles=11、pwm=1000、rpm=1500、frequency=25Hz、
  flash-writes≥1、fw=1/addr=0x65；电机电气/失速保护 NOT RUN。
- `ac-measure`：guest ASCII 视图 `  230.0 / 1.00 / 230 / 230 / 1.00 / 0.00`
  与 byte 视图 `23000/1000/23000/23000/100/0` 全部一致；系数写
  12/34 + save 计数；**AC 100–240V@10A 只是测量输入，绝不是可切换负载**，
  市电/隔离/过流/计量精度 NOT RUN。
- `dds`：分段写 1000 Hz/90° → guest 读回 `81`/`800068db`/`8200`/`80`；
  QOM frequency≈1000、phase≈90°、waveform=1、ctrl-word=0x80；AD9833 模拟
  波形/幅度/相位精度 NOT RUN；组合 burst 与读快照布局 unresolved。
- `gps`：注入 GGA/RMC/VTG 三行 fixture → guest `gps_time=02:44:23`、
  纬度 `2242.10772N`、经度 `11348.64472E`、海拔 52.1、卫星 14、日期
  `03/11/24`、VTG course/speed；真实 GNSS/射频/天线 NOT RUN，驱动不校验
  NMEA checksum 未决。
- `uhf-rfid`：JRD4035 inventory 两帧 → guest EPC
  `e200001234567890` ×2；QOM frames-sent/injected≥2；**RF/Gen2/真实标签
  能力 NOT RUN，绝不宣称真实标签读取或安全能力**。

每个会话在停止前取得 evidence ZIP，停止使用 `purge=0` 并回读保留 history；
`manifest.json`、`serial.log`、`units/runtime.json`、`units/state.json`、
`units/contract.json` 均存在，帧为非空应用画面。

## 未覆盖（明确边界）

- 端口：PORT.B/PORT.C 的物理接线未被验证（runtime 只在 cores3 PORT.A 准入）；
  官方连接器映射来自产品页面，harness 为替代接线。
- `ac-measure`：市电通断/隔离耐压/过流/计量精度/HLW8032 NOT RUN；页面
  STM32G030 vs 官方 I2C 总表 STM32F030 冲突。
- `uhf-rfid`：840–960MHz RF/天线/Gen2 空口/读取距离/区域限制 NOT RUN；
  kill/lock/密码只做帧层。
- `laser-tx`：人眼安全/光功率/波长/调制带宽 NOT RUN；不宣称光学输出。
- `weight`：HX711 电气/10SPS/称重力学/载荷/温漂/量程 NOT RUN；页面 FAQ
  的 I2C 描述与 GPIO 位脉冲 PinMap/驱动冲突；与 weight-i2c（U180, 0x26）
  是不同协议。
- `co2l`：SCD40/SCD41 身份、5s 周期/CRC/精度 NOT RUN；温度驱动解码 bug；
  序列号路径 blocked；0x62 与 co2 冲突。
- `tof4m`：VL53L1CXV0FY/1 命名、4m 量程/分辨率/激光安全/光学 NOT RUN；
  0x29 与 tof/color 冲突。
- `bldc-driver`：电机电气/转速/失速保护/DRV11873 状态/5V 输出 NOT RUN；
  0xF0 flash 持久化语义未决。
- `dds`：AD9833 模拟波形/幅度/相位精度/输出阻抗/0-0.6V NOT RUN；组合
  `set_freq_phase/quick_output` 6 字节 burst 与读快照布局仍未修复。
- `gps`：真实 GNSS 卫星/射频/天线/定位精度 NOT RUN；NMEA checksum 不校验；
  PORT.C 与 midi/uhf-rfid/rs485-iso 端口冲突；页面 EOL。
- `midi`：SAM2695 音频合成/音色/复调 NOT RUN；31520 vs 31250 vs 驱动默认
  波特率未决；PORT.C 冲突。
- `neco`：35 vs 70 灯冲突；WS2812 时序/亮度/光学/功耗/级联 NOT RUN。
- `rs485-iso`：隔离耐压/ESD/fail-safe/500Kbps/256 节点 NOT RUN；包装器
  构造缺陷已记录。
- 所有 12 款：仅 cores3 + 本固件 SHA + 本 QEMU 二进制组合；不转授其他主机。

## 固件与运行时来源

- 参考固件缓存（service 只读，不入 Git）：cores3
  `platform/.cache/firmware/cores3/uiflow2.bin` SHA-256
  `1324f12d3ddd5392f47a9eff537f9ce0b01a8e6e36d829b6bd22cdf82d2c1264`。
- 每个 case 的合并镜像 SHA-256、探针 SHA-256 与 runtime 二进制 SHA-256 记录在
  [`summary.json`](summary.json) 与 `report-<unit>.json`。
- Device Service：独立端口 `127.0.0.1:8799`、独立 state/token、
  `M5_SERVICE_FLASH_MODE=host-image`；用户 `8787` 未触碰。

## 复现

```bash
# 树：canonical + 0120..0129 + 0131 + 0134 + 0136 + 0137；构建后签名部署
# 到 .work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa
M5_SERVICE_FLASH_MODE=host-image \
M5_QEMU_XTENSA="$PWD/.work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa" \
M5_QEMU_XTENSA_ROM_DIR="$PWD/.work/M5StopWatch-QEMU/build/qemu/pc-bios" \
  PYTHONPATH=platform/tools python3.12 platform/tools/serve.py 8799 \
  --bind 127.0.0.1 --state-dir .work/unit-batch4-service \
  --api-token "$(cat .work/unit-batch4-service.token)"

export M5_SERVICE_API_TOKEN="$(cat .work/unit-batch4-service.token)"
PYTHONPATH=platform/tools python3.12 tests/units/run_batch4_cases.py \
  --api-url http://127.0.0.1:8799 --case <unit> --out-dir .work/unit-batch4-evidence
```

未使用 `8787`，未修改用户服务；每个 session 停止时 `purge=0` 保留 history，
原始 ZIP/帧/串口日志留在本地忽略的 `.work`，仓库只提交摘要、哈希与复现命令。

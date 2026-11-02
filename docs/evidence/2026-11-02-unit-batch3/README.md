# Unit 第三批 12 款（A+B 8 款 / C 4 款）虚拟设备证据

日期：`2026-11-02`。范围：把
[Unit 第三批协议研究](../../unit-research/2026-11-02-batch3-protocols.md) 的全部
12 款 Unit 数据面通过**独立 Device Service**的可见 `/api/v1` 会话记录为
**虚拟设备**证据。物理硬件、机械、光学、声学、电气与市电语义全部 `NOT RUN`。

本页是验证证据，不定义当前能力；当前能力以
[项目当前状态](../../project-status.md) 为准，工作队列以
[项目 Backlog](../../project-backlog.md) 为准。所有结果只覆盖表内记录的主机、
固件 SHA、QEMU 二进制 SHA 和检查项，不转授未列组合。

## 关键点：两棵并行 QEMU 树

`0130`（A+B 8 款）与 `0131`（C 4 款）是**并行补丁**，无法顺序 `git apply`。
本证据用两棵独立 QEMU 树/两个构建：

| 批次 | Unit | QEMU 源码状态 | 运行时二进制 SHA-256 |
| --- | --- | --- | --- |
| A+B | rfid/tube-pressure/laser-rx/extio/dac2/scales/vmeter/adc | canonical `75f1d24` + 0120/0121/0122/0123 + 0125/0126/0127/0128/0129 + **0130 + 0133 + 0135** | `f71ae85c21944431a3ab6334b624ac1f6a63a751eb285259daa10caf98f061d9` |
| C | env-iv/co2/pbhub/ultrasonic-io | canonical `75f1d24` + 0120/0121/0122/0123 + 0125/0126/0127/0128/0129 + **0131 + 0132** | `d56e7b47befc18396cca5cb42011a956b9fdd12117f66e77e189b11cfaf08d63` |

证据发现并修复了 4 个真实模型 bug（见下节）；本目录全部 session 均使用修复后的
二进制。`0134` 是 host-basic27 batch4 的预留号，未占用。

## 证据修复（本轮发现）

| 补丁 | 根因 | 影响与重跑 |
| --- | --- | --- |
| `0132-unit-batch3c-fixes.patch`（sha256 `6be4c121…`） | C 树 0131：①PbHub 0x09/0x0A 颜色写提交晚 1 字节（offset 5/7 而非 4/6），驱动 5/7 字节载荷永不提交；②Ultrasonic-IO 在 GPIO pad observer 内直接 `esp32_gpio_set_input()`，触发 QEMU `!g_pad_dispatch_depth` 断言 abort（exit -6）；③SCD40 序列号响应只有 2 个数据字（6B），驱动读 3 字（9B）CRC 失败必抛 OSError | C 4 款全部重跑：pbhub RGB/ultrasonic echo/co2 序列号从 blocked 变 PASS |
| `0133-unit-vmeter-default-config.patch`（sha256 `4915d757…`） | A+B 树 0130：VMeter 驱动构造函数假定 PGA_2048/RATE_128 但从不写配置，模型沿用 AMeter 默认 gain 5，导致默认路径与 guest 自己的分辨率表不一致 | vmeter 证据使用默认路径即可自洽（读数 11.78 V 是 3.93 V/LSB 量化） |
| `0135-unit-batch3ab-fixes.patch`（sha256 `252eaf12…`） | A+B 树 0130：①PCA9554 输入口读取的 config 掩码反了（input 位当成 output），output latch 永不可观测；②Scales 0x50..0x52 RGB 只接受首字节，第二/三字节被 NACK，`led-rgb` 只到 0x110000 且后续校准写被跳过 | extio 读回 165、scales led-rgb 0x112233/校准写计数从 FAIL 变 PASS（A+B 8 款重跑） |

这些修复不改变任何 `planned`→`partial` 之外的目录语义；catalog 记录保持
`model_status=partial`。

## 结论

12 款各建 1 个可见 session，均在 guest 内运行参考固件自带的**原始冻结
UIFlow2 Unit 驱动**，经真实 SoC GPIO/ADC/RMT 或 I2C 控制器读写，没有 host 端
直写驱动返回值：

| Unit | 批次/主机 | 原始驱动类 | 结果 |
| --- | --- | --- | --- |
| `rfid` | A+B / cores3 port-a | `RFIDUnit(MFRC522)` | PASS |
| `tube-pressure` | A+B / atoms3r custom | `TubePressureUnit` | PASS |
| `laser-rx` | A+B / atoms3r custom | `LaserRXUnit` | PASS |
| `extio` | A+B / sticks3 custom | `EXTIOUnit(PCA9554)` | PASS |
| `dac2` | A+B / cores3 port-a | `DAC2Unit(GP8413)` | PASS |
| `scales` | A+B / sticks3 custom | `ScalesUnit` | PASS |
| `vmeter` | A+B / cores3 port-a | `VoltmeterUnit(ADS1115)` | PASS |
| `adc` | A+B / stopwatch port-a | `ADCUnit(ADS1100)` | PASS |
| `env-iv` | C / atoms3r custom | `ENVUnit(ENV_IV)` | PASS |
| `co2` | C / sticks3 custom | `CO2Unit(SCD40)` | PASS |
| `pbhub` | C / cores3 port-a | `PBHUBUnit` | PASS |
| `ultrasonic-io` | C / stopwatch port-a | `ULTRASONIC_IOUnit` | PASS |

关键 controller-backed 观测（完整值见 `summary.json` 与 `report-<unit>.json`）：

- `rfid`：注入 `card-present=True` 后 guest `is_new_card_present()=1`、
  `read_card_uid()` 前缀 `04010203`（10 字节 UID buffer），MIFARE 块读事务；
  QOM card-present/selected/transactions 一致。
- `tube-pressure`：注入 `analog-mv=1600` → `get_analog_value(16)=33832`、
  `(12)=2114`（12-bit ADC→read_u16 预期一致）；`get_pressure()/get_voltage()`
  因无 ADC 校准 fixture 抛 `OSError(95)`，如实记录为 boundary。
- `laser-rx`：`digital-level` 先 false 后 true，guest `value()` 出现 0→1 序列；
  `input-events=2`，无 I2C 事务。
- `extio`：注入 8 位输入 fixture，`set_port_mode(OUT)` 后 `digit_write_port(0xA5)`
  读回 165，写 0 并切回 IN 后输入读到 0x55；QOM output-levels/config/polarity 一致。
- `dac2`：用驱动自己的 `CHANNEL_*` 常量完成 CH1/CH0/BOTH 与量程切换；最终
  `range=1`、两通道 `dac-raw=0xFFFF`、`voltage-*=10.0`。（驱动 int/tuple
  比较缺陷写入 boundary：普通 int 调用会静默不写。）
- `scales`：注入 `weight-g=543.21`/`adc-raw=123456`/`button-status=2` →
  `get_scale_value(0)=123456`、`(1)=543`；RGB 读回 `[17,34,51]`、sync=1；
  校准零/负载写计数 2；QOM led-rgb=0x112233、offset-adc=123、fw=2。
- `vmeter`：注入 `voltage-v=12.0` → guest 11.7784 V / raw=-3（PGA_2048
  3.93 V/LSB 量化，driver 公式一致）；EEPROM 校准读成功、写被拒并计数；
  显式 `set_gain(5)/set_data_rate(4)/set_operating_mode(1)` 后 config=0x8B80。
- `adc`：注入 `voltage-v=3.3` → `get_value()=8192`、`get_voltage()=3.3`；
  默认 gain1/rate8/mode0，配置写后 QOM config-word=0x99；`get_raw_value()`
  返回 2 字节切片（快照驱动行为）。
- `env-iv`：SHT40 帧 CRC 由驱动校验通过，T/RH=`25.5/60.5`；BMP280 半边
  压力 `1000.0 hPa`；serial-number=0x12345678；双从机事务计数增长。
- `co2`：注入 1234 ppm/60.5 %RH 后 guest `co2=1234`、`humidity=60.5`；
  SCD40 三字序列号可读；**温度解码 bug**（`buf[1]` 而非 `buf[4]`）被如实记录，
  未断言为 fixture 匹配。
- `pbhub`：6 通道 fixture 读回；`digital_write`/`pwm_write(50%→128)`/
  `set_rgb_led_num`+`set_rgb_color(0xFF0000)`→QOM rgb-frames=0xFF0000、
  rgb-mode=1、fw=1/地址 0x61；IO0/IO1 位置在 0131 契约中折叠为单布尔（boundary）。
- `ultrasonic-io`：注入 `distance-mm=1000` → guest 距离约 1000–1200 mm、
  echo 宽约 5.8–7 ms；QOM echo-pulse-us=5820、trigger-count≥8；第二个实例用
  `echo_timeout_us=1000` 走 guest timeout（负值/异常）路径。

每个会话在停止前取得 evidence ZIP，停止使用 `purge=0` 并回读保留 history；
`manifest.json`、`serial.log`、`units/runtime.json`、`units/state.json`、
`units/contract.json` 均存在，帧为非空应用画面。

## 固件与运行时来源

- 参考固件缓存（service 只读，不入 Git）：
  - cores3 `…/cores3/uiflow2.bin` SHA-256
    `1324f12d3ddd5392f47a9eff537f9ce0b01a8e6e36d829b6bd22cdf82d2c1264`
  - atoms3r `…/atoms3r/uiflow2.bin` SHA-256
    `91c0f97c904271d4c47d240165fbf5589d44aa0d753ca17d685bfdce5bff199a`
  - sticks3 `…/sticks3/uiflow2.bin` SHA-256
    `c08196024019273ccadee9b4b3da303567f7ab206fa14edd1af283f04f6e98d8`
  - stopwatch `…/stopwatch/uiflow2.bin` SHA-256
    `99d6482befe094de47bf68ce43618d3868bd62fb1fc72f0b55c0d0c2ea4e7f8d`
- 每个 case 的合并镜像 SHA-256、探针 SHA-256 与 runtime 二进制 SHA-256 记录在
  [`summary.json`](summary.json) 与 `report-<unit>.json`。
- Device Service：独立端口 `127.0.0.1:8799`、独立 state/token、
  `M5_SERVICE_FLASH_MODE=host-image`；A+B 与 C 批次分别重启同一 8799 服务并
  指向各自 `M5_QEMU_XTENSA` 二进制。用户 `8787` 未触碰。

## 复现

```bash
# A+B 树：canonical + 0120..0129 + 0130 + 0133 + 0135，构建后指向
#   .work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa
# C 树：  canonical + 0120..0129 + 0131 + 0132，构建后指向
#   .work/M5StopWatch-QEMU-c/build/qemu/build/qemu-system-xtensa
M5_SERVICE_FLASH_MODE=host-image M5_QEMU_XTENSA=<batch-binary> \
  PYTHONPATH=platform/tools python3.12 platform/tools/serve.py 8799 \
  --bind 127.0.0.1 --state-dir .work/unit-batch3-<batch>-service \
  --api-token "$(cat .work/unit-batch3-<batch>-service.token)"

export M5_SERVICE_API_TOKEN="$(cat .work/unit-batch3-<batch>-service.token)"
PYTHONPATH=platform/tools python3.12 tests/units/run_batch3_cases.py \
  --api-url http://127.0.0.1:8799 --case <unit> --out-dir .work/unit-batch3-evidence
```

先跑 A+B 8 款（A 服务），再重启 C 服务跑 C 4 款。

## 未覆盖

- `rfid`：RF 场/天线/距离/真实卡片与密钥 NOT RUN；0x28 与 rfid2 冲突。
- `tube-pressure`：ADC 校准（read_uv/get_pressure/get_voltage）NOT RUN；线性度/
  温补/±1.5 kPa NOT RUN。
- `laser-rx`：UART 模式、光学链路/140–205 kHz/900 nm NOT RUN。
- `extio`：INT、A0–A2 焊盘、上下拉/开漏电气 NOT RUN；EOL。
- `dac2`：15-bit vs 16-bit、模拟输出/短路保护/线性度 NOT RUN；驱动 int/tuple
  通道 API 缺陷已记录；0x59 与 extencoder 冲突。
- `scales`：HX711 采样/称重力学/去皮/20 kg/10 SPS NOT RUN；0x26 三方冲突。
- `vmeter`：真实校准/±36 V/隔离/保险丝/1% 精度 NOT RUN；默认分辨率量化明确
  记录；0x53 与 accel 冲突。
- `adc`：ADS1100 vs ADS1110、内部参考/PGA 精度、snapshot/master 长度差异
  unresolved；0x48 三方冲突；EOL。
- `env-iv`：ENV-II/III、SHT40 精度/自热/真实校准、BMP280 校准真实性 NOT RUN；
  EOL；0x44/0x76 冲突。
- `co2`：温度解码为已知驱动 bug（不可断言）；SCD40/SCD41、5 s 周期/上电时序/
  精度 NOT RUN。
- `pbhub`：IO0/IO1 位置折叠、MCU 身份、RGB 字节序、嵌套 hub、servo/RGB 电气
  NOT RUN；EOL。
- `ultrasonic-io`：声学/40 kHz/±2%/周期 NOT RUN；PORT.A PinMap 标签冲突；
  timeout 通过 guest 小 timeout 实例验证。
- 每款只回放表中主机；其它主机/固件、Web bridge、真机全部 NOT RUN，不转授
  未列组合。
- Raw `result.json`、`serial.log`、`frame.png` 与 evidence ZIP 保存在本地
  git-ignored `.work/unit-batch3-evidence/`；提交内容仅为
  [`summary.json`](summary.json) 与本目录 `report-*.json` 摘要。

# Unit 第七批 8 款虚拟设备证据（batch7 guest / Device Service）

日期：`2026-11-03`。范围：batch7 全部 8 款可实现 Unit 的 guest/Device Service
证据：`mini-tof-90`、`hbridge-v11`、`cardkb-original`、`env-ii`、`hex`、
`catm`、`catm-gnss`、`lorawan-cn470`。`can` 因已知 CAN attachment/帧注入
gap 记为 **BLOCKED**（无 session、无 PASS）；`mini-bps-v11` 与 `mini-pdm`
已 **DEFER**（不在本批测试）；`mini-imu-pro` 不在本批 8 款范围，保持 planned。

本页是验证证据，不定义当前能力；当前能力以
[项目当前状态](../../project-status.md) 为准，工作队列以
[项目 Backlog](../../project-backlog.md) 为准。

## 关键点：单一 QEMU 构建 + 0149 证据修复

| 项 | 值 |
| --- | --- |
| QEMU 源码状态 | canonical `75f1d24` + canonical 链 28 层（0120–0147，含 **0143** batch7 A、**0145** batch7 B）+ **0149（本轮证据修复）** |
| QEMU 树 | `.work/native-lock-source/qemu`（删除 build 后重新 configure） |
| 运行时二进制 SHA-256（签名部署副本） | `beb95e4c9dad67571b1a18b70021a89c321fa76ec42ef752489dc9ac885ab432` |
| 构建产物 SHA-256（unsigned） | `a0ea6a287b0bd1379ca3517a8ebfbae8f223aad6bff5b5f9fabef0648185829f` |
| 参考固件 | cores3 `platform/.cache/firmware/cores3/uiflow2.bin`，SHA-256 `1324f12d…` |
| Device Service | 独立 `127.0.0.1:8799`、独立 state/token、`M5_SERVICE_FLASH_MODE=host-image`；用户 `8787` 未触碰 |

## 0149 证据修复

`0150-unit-batch7-evidence-fixes.patch`（base canonical 链到 0147）：

| 根因 | 影响 | 修复 |
| --- | --- | --- |
| `0145` 把 catm/catm-gnss/lorawan-cn470 加入 UART TX 捕获条件，但**未加入通用 idle 响应体** | 捕获到 TX 后不 arm fixture timer，`frames-sent/frames-injected` 恒 0，SIM7080G/LoRaWAN 驱动每条 AT 都超时 | 把三个 id 加入通用 idle fixture responder 分支 |
| `gpio_uart_rx_device_for_white()` 只按 guest GPIO matrix RX 路由找 UART；冻结 ASR650x wrapper 的 UART(1,tx,rx)+init 路径未被命中 | 注入 fixture 字节进不了 guest RX FIFO，`frames-injected=0`，guest 读不到响应 | 增加 fallback：复用 TX signal 路由到 yellow 的同一 UART 设备，仍注入真实 UART RX FIFO |

此外 lorawan-cn470 的冻结驱动在构造前需要 baud-configured UART 实例才能让
模型 TX matrix 观测到；探针在官方驱动前用同 pins/baud 预初始化一次（**guest
侧 model-ordering workaround，已在 report/README 明确记录**），官方
`LoRaWANUnit` 仍执行 CWORKMODE/DTRX 字节帧。该 workaround 不改变“只断言字节
层、不宣称 LoRaWAN/RF”的边界。

## 结论

8 款各建 1 个可见 session，均运行参考固件自带的冻结 UIFlow2 驱动；通过后
profile 升 implemented，catalog 保持 partial。`can` 无 session，记为 BLOCKED。

| Unit | 主机/端口 | 原始驱动 | 结果 |
| --- | --- | --- | --- |
| `mini-tof-90` | cores3 port-a (官方 PORT.A) | `ToFUnit` (VL53L0X 0x29) | PASS |
| `hbridge-v11` | cores3 port-a (官方 PORT.A) | `HbridgeUnit` (0x20) | PASS |
| `cardkb-original` | cores3 port-a (官方 PORT.A) | `CardKBUnit` (0x5F) | PASS |
| `env-ii` | cores3 port-a (官方 PORT.A) | `ENVUnit(ENV_II)` SHT30+BMP280 | PASS |
| `hex` | cores3 port-a（官方 PORT.B） | `RGBUnit`/SK6812 37 LEDs（driver-gap） | PASS |
| `catm` | cores3 port-a（官方 PORT.C） | `CATMUnit` (SIM7080G fixture) | PASS（字节层） |
| `catm-gnss` | cores3 port-a（官方 PORT.C） | `CATMGNSSUnit` (fixture) | PASS（字节层） |
| `lorawan-cn470` | cores3 port-a（官方 PORT.C） | `LoRaWANUnit` (ASR650x wrapper) | PASS（字节层） |
| `can` | — | — | **BLOCKED**（无 session；CAN attachment/帧注入 gap） |

**端口替换**：官方 PinMap 把 hex 放 PORT.B、catm/catm-gnss/lorawan-cn470
放 PORT.C，但 host-port 只准入 cores3 PORT.A；这些 session 使用 PORT.A 的
GPIO 2/1 harness，report 记录 `official_port`/`runtime_port_substitution`。

关键观测（完整在 report/summary）：

- `mini-tof-90`：guest `get_range()`=500（fixture distance-mm=500）；
  `get_data_ready()` 记录为 observation（0）；QOM distance-mm=500、I2C
  transactions>0。连续模式 `read_range()` 在模型无新样本时会阻塞，未断言。
- `hbridge-v11`：guest ADC16=2048/ADC8=128、VIN current=0.5A；写
  direction=1/16-bit PWM=32768/freq=1000 后 QOM direction=1、duty≈50%、
  frequency=1000；guest 读 0xFE/0xFF status=1/32；QOM fixtures 一致。
- `cardkb-original`：READY 后注入 `keycode=0x71`，guest `get_key()`=113；
  QOM input-events≥1、key-overflows=0；U035 original 与 v1.1 差异保留
  unresolved。
- `env-ii`：guest T/RH/P = 31.5°C / 45.5% / 1005.0 hPa；QOM 双从机
  fixtures 31.5/45.5/100500 一致；I2C transactions>0。
- `hex`：generic RGBUnit/SK6812 写 `fill_color(0x112233)` → QOM 37 灯全
  0x112233、led-frames≥1、incomplete=0；driver-gap 明确记录。
- `catm`：官方驱动 AT/ATE0/GSN 字节帧被捕获，fixture responder 返回
  `OK`/IMEI；QOM tx-hex 含 `AT`/`ATE0`/`AT+GSN`，frames-sent/injected≥2；
  **不宣称蜂窝/RF**。
- `catm-gnss`：官方驱动 AT/ATE0/CGNSPWR 字节帧 + fixture 响应；GNSS
  解析不建模、不断言；蜂窝+GNSS 不能并发（页面 FAQ）写 blocker。
- `lorawan-cn470`：官方驱动 CWORKMODE=2（构造）/CWORKMODE=1/DTRX 字节帧
  被捕获，fixture responder 返回 OK/OK+SENT；只断言字节层；STM32WLE5 vs
  ASR650x 驱动/产品错配 unresolved；pre-init workaround 已在 report 记录。

每个会话先取 evidence ZIP，`purge=0` 停止并回读 history；evidence ZIP 含
manifest/serial/units runtime+state+contract，帧为非空应用画面。

## 未覆盖（明确边界）

- `can`：**BLOCKED**。0145 模型仅暴露 CanBusClient 的 QOM
  frames-observed/inject-hex；guest TWAI/CAN framing、方向/过滤/位定时、
  外部收发器/隔离/终端/仲裁均未建模；不伪造 CAN session/PASS。
- `mini-bps-v11`：DEFER（QMP6988 地址 0x56 vs 0x70 unresolved）。
- `mini-pdm`：DEFER（无官方 Unit PDM 驱动；PDM RX 是板级 I2S，不是 Unit
  attachment；不伪造 PCM）。
- `mini-imu-pro`：不在本批 8 款范围；保持 planned。
- `mini-tof-90`：激光光学/940nm/FoV/3-200cm 物理 NOT RUN；0x29 与
  tof/tof4m/color 冲突。
- `hbridge-v11`：电机/RZ7899/INA199/真实负载/3A 保护 NOT RUN；0x20 与
  hbridge U160 冲突。
- `cardkb-original`：U035 original vs v1.1 MCU/键值差异 unresolved；
  键盘矩阵/键程/RGB LED NOT RUN；0x5F 与 cardkb 冲突。
- `env-ii`：SHT30/BMP280 真实温湿度/气压/自加热/精度 NOT RUN；0x44/0x76
  与 env 系冲突。
- `hex`：无 unit/hex.py；SK6812 vs WS2812C 时序/字节序 unresolved；LED
  光学/功率/级联 NOT RUN；PORT.B 用 PORT.A harness 替换。
- `catm`/`catm-gnss`/`lorawan-cn470`：**无 RF/蜂窝/SIM/运营商认证/网络/
  GNSS 定位/LoRaWAN stack 声明**；仅 UART fixture 字节层；SIM7080G
  AT/URC 顺序、CGNSINF 解析、CN470 频段/占空比均 unresolved/NOT RUN。
- 所有 8 款仅 cores3 + 本固件 SHA + 本 QEMU 二进制组合；不转授其他主机。

## 复现

```bash
# 树：canonical + 0120..0147 + 0149；删除 build 后重新 configure
M5_SERVICE_FLASH_MODE=host-image \
M5_QEMU_XTENSA="$PWD/.work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa" \
M5_QEMU_XTENSA_ROM_DIR="$PWD/.work/M5StopWatch-QEMU/build/qemu/pc-bios" \
  PYTHONPATH=platform/tools python3.12 platform/tools/serve.py 8799 \
  --bind 127.0.0.1 --state-dir .work/unit-batch7-service \
  --api-token "$(cat .work/unit-batch7-service.token)"

export M5_SERVICE_API_TOKEN="$(cat .work/unit-batch7-service.token)"
PYTHONPATH=platform/tools python3.12 tests/units/run_batch7_cases.py \
  --api-url http://127.0.0.1:8799 --case <unit> --out-dir .work/unit-batch7-evidence
```

未使用 `8787`；每个 session 停止时 `purge=0`；原始 ZIP/帧/串口日志留在本地
忽略的 `.work`，仓库只提交摘要、哈希与复现命令。

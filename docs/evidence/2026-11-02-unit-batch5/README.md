# Unit 第五批 12 款（A 5 款 / B 7 款）虚拟设备证据

日期：`2026-11-02`。范围：把
[Unit 第五批协议研究](../../unit-research/2026-11-02-batch5-protocols.md) 的全部
12 款 Unit 数据面通过**独立 Device Service**的可见 `/api/v1` 会话记录为
**虚拟设备**证据。物理硬件、光学、热学、射频、蜂窝、Mesh 与市电语义全部
`NOT RUN`。

本页是验证证据，不定义当前能力；当前能力以
[项目当前状态](../../project-status.md) 为准，工作队列以
[项目 Backlog](../../project-backlog.md) 为准。所有结果只覆盖表内记录的
主机、固件 SHA、QEMU 二进制 SHA 和检查项，不转授未列组合。

## 关键点：单一 QEMU 构建

`0137`（batch5 A 5 款）与 `0139`（batch5 B 7 款）都位于同一条 canonical 链，
因此本批只需要**一个** QEMU 构建；`0141` 是本轮证据发现的模型修复。

| 项 | 值 |
| --- | --- |
| QEMU 源码状态 | canonical `75f1d24` + canonical 链 20 层（0120–0139，含 **0137** batch5 A 与 **0139** batch5 B）+ **0141（本轮证据修复）** |
| QEMU 树 | `.work/native-lock-source/qemu` |
| 运行时二进制 SHA-256（签名部署副本） | `0962a76a864ab12d20dcfa84b6b6b5a0c59ff4d75b9089098f67c5b59145a4b9` |
| 构建产物 SHA-256（unsigned 构建） | `06723b6bd32f18a2c6296bb5d051dea56a34b89ff2a4f205bf9109f5507919ad` |
| 参考固件 | cores3 `platform/.cache/firmware/cores3/uiflow2.bin`，SHA-256 `1324f12d…` |
| Device Service | 独立 `127.0.0.1:8799`、独立 state/token、`M5_SERVICE_FLASH_MODE=host-image`；用户 `8787` 未触碰 |

## 证据修复（本轮发现）

`0141-unit-batch5-evidence-fixes.patch` 是本轮证据发现并修复的模型 bug，base 为
canonical 链到 `0139` 的树：

| 根因 | 影响 | 修复 |
| --- | --- | --- |
| `0137` op90：只暴露派生 active-low `blocked` 与只读 `input-level`，`digital-level` 输入没有可写 QOM 属性 | Device Service 会话 state 不可用，无法注入电平 | 新增可写 `digital-level`，直接驱动白线；`blocked` 保持镜像 |
| `0139` rtc：`sensor_recv()` 每次读都用虚拟时钟刷新 BCD 寄存器，即使 running=false 也覆盖 guest 写入 | guest `set_date_time` 后读回仍是注入的基准时间 | 仅 running=true 时刷新；停止时保留 guest 写入的 BCD |
| `0139` tmos-pir：fixture 存 `values[]` 而刷新用独立 `tmos_*` 字段；FUNC_STATUS bit0/bit2 的 shock/presence 与驱动 `refresh_state()` 解析相反；主数据寄存器从 embedded page 读 | guest presence/shock 错位、host fixture 不可见 | 同步 `values[0]/[1]`；FUNC_STATUS 改为 bit0 shock / bit1 motion / bit2 presence；主数据寄存器固定 page 0，仅 0x09 走 embedded page |
| `0139` kmeter-iso-v11：`add_number()` fixture 与 `kmeter_*` 视图字段分离 | host 温度 fixture 对 guest 不可见（guest 读到默认 25.0） | `sensor_update()` 同步 `values[0]/[1]` 到 `kmeter_tc_c/kmeter_internal_c` |

修复后的二进制用于**全部 12 个 session**（不只重跑受影响款），因此所有 report 的
`runtime_binary_sha256` 一致。

## 结论

12 款各建 1 个可见 session，均在 guest 内运行参考固件自带的**原始冻结 UIFlow2
驱动**，经真实 SoC I2C/GPIO/RMT/UART 控制器读写，没有 host 端直写驱动返回值：

| Unit | 批次 | 主机/端口 | 原始驱动类 | 结果 |
| --- | --- | --- | --- | --- |
| `pbhub-v11` | A | cores3 port-a | `PBHUBUnit` v1.1 (0x61) | PASS |
| `op90` | A | cores3 port-a（官方 PORT.B） | `OPUnit` | PASS |
| `rgb-led-10cm` | A | cores3 port-a（官方 PORT.B） | `RGBUnit`(SK6812, 15) | PASS |
| `8angle` | A | cores3 port-a | `Angle8Unit` | PASS |
| `kmeter-iso-v11` | A | cores3 port-a | `KMeterISOUnit` | PASS |
| `pahub-v20` | B | cores3 port-a | `PAHUBUnit` | PASS |
| `rtc` | B | cores3 port-a | `RTC8563Unit` | PASS |
| `tmos-pir` | B | cores3 port-a | `TMOSUnit`(STHS34PF80) | PASS |
| `neohex` | B | cores3 port-a（官方 PORT.B） | `driver.neopixel.ws2812.WS2812`（unit 驱动 gap） | PASS |
| `lora-e220-433` | B | cores3 port-a（官方 PORT.C） | `LoRaE220433Unit` | PASS |
| `zigbee` | B | cores3 port-a（官方 PORT.C） | `ZigbeeUnit`(DRF1609H) | PASS |
| `nbiot2` | B | cores3 port-a（官方 PORT.C） | `NBIOT2Unit`(SIM7028) | PASS |

**端口替换说明**：官方 PinMap 把 op90/rgb-led-10cm/neohex 放在 PORT.B、把
lora/zigbee/nbiot2 放在 PORT.C，但当前 host-port 注册表只把 `cores3/PORT.A`
作为 main-device 端口准入，因此这些 session 使用 cores3 PORT.A 的 GPIO 2/1
作为 harness 接线；guest 的 SoC GPIO/RMT/UART 控制器路径仍真实执行，但
**官方连接器物理接线本身未被验证**。每个 report 的
`official_port`/`runtime_port_substitution` 字段记录替换。

关键 controller-backed 观测（完整值见 `summary.json` 与 `report-<unit>.json`）：

- `pbhub-v11`：v2 固件读回；6 通道 digital/analog fixture（1/1/512，IO0/IO1
  在 0137 中折叠为单布尔）；`digital_write`/`pwm_write(50→128)`/
  `set_rgb_color(0xFF0000)` → QOM digital-outputs/pwm-outputs/rgb-frames 一致。
- `op90`：注入 `digital-level=true→false→true`，guest `Pin.value()` 序列
  1→0→1；QOM digital-level/blocked 一致、input-events≥2；无 I2C 事务。
- `rgb-led-10cm`：`fill_color(0x112233)` → QOM 15 灯全 0x112233、led-frames≥1。
- `8angle`：注入 ADC12/ADC8/开关 fixture，guest 读回 100/800、10/80、1；
  `set_led_rgb(1/2)` → QOM 9 灯数组前两项 0x112233/0x445566（驱动 channel-1
  API 语义已记录）。
- `kmeter-iso-v11`：注入 123.45/26.5°C，guest 热电偶/内部温度一致、ready=1、
  fw=1；QOM fixture 精确。
- `pahub-v20`：guest select 0→3→5、release 3→0/5，QOM mask 序列
  `1→9→41→33→0`、channel-writes≥5；**下游 bus/嵌套 hub NOT modeled，仅 mask**。
- `rtc`：QOM `unix-time=1767225600`（2026-01-01）注入，guest 读回基准；
  虚拟时钟推进 1s+；切 running=false 后 guest `set_date_time(2026-03-02 12:00:00)`
  写入成功，QOM `unix-time=1772452800`、guest 读回一致。
- `tmos-pir`：注入 tobject=31.5/tambient=22.25/presence/motion，guest
  presence=1/motion=1/shock=0、raw `3150/2225`、temperature_data=1.575。
- `neohex`：generic WS2812 驱动写 37 灯 0x445566 → QOM 37 灯一致；**记录
  public 源无 unit/neohex.py 的 driver gap**。
- `lora-e220-433`：guest `setup(own_address=0x1234, channel=5)` 返回 True、
  `read_command_format()` 解析一致；QOM tx-hex 含 `c00008…1234…` 配置帧与
  `43210748454c4c4f` 发送帧，config-hex 镜像、frames≥2。
- `zigbee`：guest `p2p_transmission(0x1234, b"HELLO")` → QOM tx-hex
  `ed05123448454c4c4f`；fixture 响应 `a1a2a3a4` 经 guest UART RX 读回；
  constructor 的 connect/param/restart 由合成 0xFA 帧应答。
- `nbiot2`：constructor AT/AT+CFUN=1 由 fixture 应答成功；QOM tx-hex 含
  `41540d0a`/`41542b4346554e3d310d0a`，frames-sent/injected≥2；**只断言字节层**。

每个会话在停止前取得 evidence ZIP，停止使用 `purge=0` 并回读保留 history；
`manifest.json`、`serial.log`、`units/runtime.json`、`units/state.json`、
`units/contract.json` 均存在，帧为非空应用画面。

## 未覆盖（明确边界）

- 端口：PORT.B/PORT.C 的物理接线未被验证（runtime 只在 cores3 PORT.A 准入）；
  官方连接器映射来自产品页面，harness 为替代接线。
- `op90`/`op180`：90°/180° IR 光学对准、遮挡几何、响应速度 NOT RUN。
- `rgb-led-10cm`/`neohex`：LED 光学/颜色/功率/RMT 时序容差 NOT RUN；NeoHEX
  public 源无 unit 驱动，使用 generic WS2812 路径且记录 gap。
- `8angle`：电位器机械/线性度/零点、ADC 参考/滤波、SK6812 光学 NOT RUN；
  RGB 4B 的 brightness 字节未在 QOM 中还原。
- `kmeter-iso-v11`：MAX31855 fault、热电偶冷端/隔离/10Hz NOT RUN。
- `pbhub-v11`：v2 SK6812/IAP IAP 路径未建模、IO0/IO1 折叠、servo/电气 NOT RUN；
  0x61 与 pbhub 冲突。
- `pahub-v20`：下游 bus 转发/嵌套 hub 未建模、A0–A2 改址、PCA9548A 8 vs 6
  通道、电气 NOT RUN；0x70 与 env-iii 冲突。
- `rtc`：晶振/电池/掉电保持/时区 NTP/alarm IRQ/世纪闰年 NOT RUN；0x51 与
  ameter EEPROM 冲突。
- `tmos-pir`：IR 光学/热模型/FOV/增益饱和/embedded 阈值与中断/NOT RUN；
  0x5A 与 ncir/ncir2 冲突。
- `lora-e220-433`：RF 433MHz/天线/距离/空速/功率、DIP M0/M1、页面 115200
  vs 驱动 9600 冲突 NOT RUN。
- `zigbee`：Mesh/路由/2.4GHz RF/加密/天线距离 NOT RUN；DRF1609H 参数帧解析
  最小化。
- `nbiot2`：NB-IoT 网络/SIM/运营商认证/TLS/DTLS/CoAP/SSL NOT RUN；SIM7028
  AT 固件/URC 时序未钉；冻结驱动实际发送 AT+CFUN=1（公开源 Modem 未体现）。
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
# 树：canonical + 0120..0139 + 0141；构建后签名部署到
#   .work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa
M5_SERVICE_FLASH_MODE=host-image \
M5_QEMU_XTENSA="$PWD/.work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa" \
M5_QEMU_XTENSA_ROM_DIR="$PWD/.work/M5StopWatch-QEMU/build/qemu/pc-bios" \
  PYTHONPATH=platform/tools python3.12 platform/tools/serve.py 8799 \
  --bind 127.0.0.1 --state-dir .work/unit-batch5-service \
  --api-token "$(cat .work/unit-batch5-service.token)"

export M5_SERVICE_API_TOKEN="$(cat .work/unit-batch5-service.token)"
PYTHONPATH=platform/tools python3.12 tests/units/run_batch5_cases.py \
  --api-url http://127.0.0.1:8799 --case <unit> --out-dir .work/unit-batch5-evidence
```

未使用 `8787`，未修改用户服务；每个 session 停止时 `purge=0` 保留 history，
原始 ZIP/帧/串口日志留在本地忽略的 `.work`，仓库只提交摘要、哈希与复现命令。

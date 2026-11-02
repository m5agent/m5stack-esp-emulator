# Unit 第六批首批 6 款虚拟设备证据

日期：`2026-11-02`。范围：把 batch6 首批 6 款 Unit（`mini-scales`、
`rgb-led-strip-50cm`、`op180`、`synth`、`mini-imu`、`env-pro`）的数据面通过
**独立 Device Service** 的可见 `/api/v1` 会话记录为**虚拟设备**证据。物理
称重/光学/音频/热学/气体语义全部 `NOT RUN`。

本页是验证证据，不定义当前能力；当前能力以
[项目当前状态](../../project-status.md) 为准，工作队列以
[项目 Backlog](../../project-backlog.md) 为准。所有结果只覆盖表内记录的
主机、固件 SHA、QEMU 二进制 SHA 和检查项，不转授未列组合。

## 关键点：单一 QEMU 构建 + 0144 证据修复

batch6 首批 6 款都在 `0140`（batch6 A）层，本批只需**一个** QEMU 构建；
`0144` 是本轮证据发现的模型修复。

| 项 | 值 |
| --- | --- |
| QEMU 源码状态 | canonical `75f1d24` + canonical 链 22 层（0120–0141，含 **0140** batch6 A）+ **0144（本轮证据修复）** |
| QEMU 树 | `.work/native-lock-source/qemu`（重新 `configure` 后构建，未复用 shellsim 旧 build.ninja） |
| 运行时二进制 SHA-256（签名部署副本） | `0bf77bf1cf7d2a58559576ce55495dc592ea099cd6124b0f732160ced9306906` |
| 构建产物 SHA-256（unsigned） | `945225c8a6f0529fa6e4869b3c736bb56bde82c06fcd69adba7b63563d48ecb4` |
| 参考固件 | cores3 `platform/.cache/firmware/cores3/uiflow2.bin`，SHA-256 `1324f12d…` |
| Device Service | 独立 `127.0.0.1:8799`、独立 state/token、`M5_SERVICE_FLASH_MODE=host-image`；用户 `8787` 未触碰 |

## 证据修复（本轮发现）

`0144-unit-batch6-evidence-fixes.patch`，base 为 canonical 链到 `0141` 的树：

| 根因 | 影响 | 修复 |
| --- | --- | --- |
| `0140` mini-scales 写路径忘记推进 `write_pos`，寄存器指针字节从未被识别 | `i2c.readfrom_mem` 的指针阶段被 NACK，guest 读 ADC/weight/button/filter 直接 `OSError 259`，整个 mini-scales 数据面无法工作 | 对齐通用 control pointer phase（`write_pos++` / `memory_request`） |
| `0140` mini-scales 只暴露原始 `button` 字节（0=按下），catalog/profile 输入却叫 `button-pressed` | session-initial/unit-input 无法注入按钮 fixture，类型/极性不一致 | 增加 `button-pressed` bool alias（反极性映射到固件字节） |
| `0140` mini-imu guest 写 `ACCEL_CONFIG`/`GYRO_CONFIG` 只更新寄存器，QOM `accel-range`/`gyro-range` 仍停在旧 fixture 值 | state 可能报告一个 guest 已经覆盖的量程 | guest 写 0x1B/0x1C 时同步 QOM range 字段 |

修复后的二进制用于**全部 6 个 session**，所有 report 的
`runtime_binary_sha256` 一致。

## 结论

6 款各建 1 个可见 session，均在 guest 内运行参考固件自带的**原始冻结 UIFlow2
驱动**，经真实 SoC I2C/GPIO/RMT/UART 控制器读写，没有 host 端直写驱动返回值：

| Unit | 主机/端口 | 原始驱动类 | 结果 |
| --- | --- | --- | --- |
| `mini-scales` | cores3 port-a | `MiniScaleUnit` (0x26) | PASS |
| `rgb-led-strip-50cm` | cores3 port-a（官方 PORT.B） | `RGBUnit`(SK6812, 30) | PASS |
| `op180` | cores3 port-a（官方 PORT.B） | `OPUnit` | PASS |
| `synth` | cores3 port-a（官方 PORT.C） | `SynthUnit`(SAM2695) | PASS |
| `mini-imu` | cores3 port-a | `IMUUnit` (MPU6886, 0x68) | PASS |
| `env-pro` | cores3 port-a | `ENVPROUnit` (BME688, 0x77) | PASS（仅寄存器/raw field；guest 解码不判定） |

**端口替换说明**：官方 PinMap 把 rgb-led-strip-50cm/op180 放在 PORT.B、把
synth 放在 PORT.C，但当前 host-port 注册表只准入 `cores3/PORT.A`，因此这些
session 使用 cores3 PORT.A 的 GPIO 2/1 作为 harness 接线；guest 的 SoC 控制器
路径真实执行，**官方连接器物理接线未被验证**。每个 report 的
`official_port`/`runtime_port_substitution` 记录替换。

关键 controller-backed 观测（完整值见 `summary.json` 与 `report-<unit>.json`）：

- `mini-scales`：guest 读 ADC=123456、weight=123.5、button=1；`tare()` 后
  guest weight=0.0；`calibration(100,1000,200,2000)` 写入 QOM gap=10.0、
  calibration-writes≥1；`reset()`/LPF/avg/EMA 写后 guest 读回 1/7/42；
  QOM adc-raw/weight-g/button=0/i2c-address=0x26 一致。**0140 无 QOM led-rgb，
  set_led 只执行不断言。**
- `rgb-led-strip-50cm`：`fill_color(0x112233)` + `set_color(5,0x445566)` →
  QOM 30 灯 = 29×0x112233 + index5=0x445566，led-frames≥2、incomplete=0。
- `op180`：注入 `digital-level=true→false→true`，guest `Pin.value()` 序列包含
  1/0/1；QOM digital-level=true、blocked=false、input-events≥2；无 I2C 事务。
- `synth`：guest note on/off + instrument + master volume → QOM tx-hex 精确等于
  `903c64803c00b00000c028f07f7f0401007ff7`，written-bytes=19；**TX-only
  (white=NC)，无 RX 注入，也不宣称 RX**。
- `mini-imu`：guest whoami=25(0x19)、accel=(1.5,-0.5,1.0) g、gyro=(12.5,-25,50)
  deg/s、temp=31.25°C；guest 默认 2g/250dps，切到 8g/1000dps 后 QOM
  accel-range=8/gyro-range=1000（0144 同步），再读 accel 仍为 1.5 g。
- `env-pro`：guest chip-id=0x61、variant=1、status=0x80；raw field 10B =
  `8001188940000478747a`（模型合成编码）与 QOM fixture（T=31.5°C、RH=45.5%、
  P=100500 Pa、gas=500000Ω）一致。**guest 解码 T/RH/P 不判定**：0140 未实现
  BME68x 补偿逆运算，解码值仅作为 observation 记录（本轮为 0/0/0/102400）。

每个会话在停止前取得 evidence ZIP，停止使用 `purge=0` 并回读保留 history；
`manifest.json`、`serial.log`、`units/runtime.json`、`units/state.json`、
`units/contract.json` 均存在，帧为非空应用画面。

## 未覆盖（明确边界）

- 端口：PORT.B/PORT.C 物理接线未被验证（runtime 只在 cores3 PORT.A 准入）。
- `mini-scales`：HX711 5kg 载荷/温漂/线性度、去皮漂移、滤波内部实现 NOT RUN；
  页面 FAQ “I2C OR UART” 与冻结驱动 I2C-only 冲突；0x26 与
  4relay/weight-i2c/scales 四方冲突；固件 v3/v4 差异未钉；无 QOM led-rgb。
- `rgb-led-strip-50cm`：SK6812 光学/功率/IP65/时序容差 NOT RUN；页面灯带侧
  VCC/GND/DATA 线色与 Grove 转换线映射 unresolved；30 灯结果不转授
  A093-B/C/D 或 A035/A045-B。
- `op180`：180° 对射光学/遮挡几何/响应速度/机械安装 NOT RUN；OP90 结果不转授。
- `synth`：SAM2695 合成音频/音色/复调/NS4150B/扬声器 NOT RUN；TX-only；
  31250 来自驱动而非页面；PORT.C 与其它 UART Unit 冲突。
- `mini-imu`：真实运动/振动/温度/DMP/FIFO/校准 NOT RUN；0x68 与 Mini IMU-Pro
  (U171) 冲突；默认驱动单位是 m/s²/rad/s，探针显式切到 g/deg/s。
- `env-pro`：**guest 温/湿/压/气阻解码 NOT ASSERTED**（BME68x 补偿逆运算未建模）；
  gas/IAQ/heater/10.8s 扫描/校准系数/物理 T/RH/P NOT RUN；0x77 空闲但 0x76
  备选与 env/bps/env-ii/env-iv 冲突。
- 所有 6 款：仅 cores3 + 本固件 SHA + 本 QEMU 二进制组合；不转授其他主机。

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
# 树：canonical + 0120..0141 + 0144；删除 build 后重新 configure 构建
#   （不要复用其它 worktree 的 build.ninja；本次首个 binary 曾指向 shellsim 源码，
#    表现为 "Unit model is unavailable"）
M5_SERVICE_FLASH_MODE=host-image \
M5_QEMU_XTENSA="$PWD/.work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa" \
M5_QEMU_XTENSA_ROM_DIR="$PWD/.work/M5StopWatch-QEMU/build/qemu/pc-bios" \
  PYTHONPATH=platform/tools python3.12 platform/tools/serve.py 8799 \
  --bind 127.0.0.1 --state-dir .work/unit-batch6-service \
  --api-token "$(cat .work/unit-batch6-service.token)"

export M5_SERVICE_API_TOKEN="$(cat .work/unit-batch6-service.token)"
PYTHONPATH=platform/tools python3.12 tests/units/run_batch6_cases.py \
  --api-url http://127.0.0.1:8799 --case <unit> --out-dir .work/unit-batch6-evidence
```

未使用 `8787`，未修改用户服务；每个 session 停止时 `purge=0` 保留 history，
原始 ZIP/帧/串口日志留在本地忽略的 `.work`，仓库只提交摘要、哈希与复现命令。

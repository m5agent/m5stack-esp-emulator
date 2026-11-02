# Unit 第二批前 6 款（joystick/watering/fader/dac/bps/adc-v11）虚拟设备证据

日期：`2026-11-02`。范围：把
[Unit 第二批协议研究](../../unit-research/2026-11-02-batch2-protocols.md) §4.1–4.5/4.7 的
前 6 款 Unit 接入 QEMU 数据面（0125，含 0127 DAC 修复），并通过
**独立 Device Service** 的可见 `/api/v1` 会话记录 **虚拟设备**证据。物理硬件、
机械、光学、电气与水泵/称重语义全部 `NOT RUN`。

本页是验证证据，不定义当前能力；当前能力以
[项目当前状态](../../project-status.md) 为准，工作队列以
[项目 Backlog](../../project-backlog.md) 为准。所有结果只覆盖表内记录的
主机、固件 SHA、QEMU 二进制 SHA 和检查项，不能转授未列出的主机或固件。

## 结论

6 款各建 1 个可见 session，均在 guest 内运行参考固件自带的**原始冻结
UIFlow2 Unit 驱动**，经真实 SoC GPIO/ADC/RMT 或 I2C 控制器读写，没有 host 端
直写驱动返回值：

| Unit | 主机 / 端口 | 原始驱动类 | 会话 | 结果 |
| --- | --- | --- | --- | --- |
| `joystick` | cores3 `port-a` | `unit.JoystickUnit` | `55dc15d00004475b84e69231cc42945f` | PASS |
| `watering` | atoms3r `custom` | `unit.WateringUnit` | `b27a64ff05954c4db2109e59c25b0c1e` | PASS |
| `fader` | atoms3r `custom` | `unit.FaderUnit` | `8209d486e534458fa6258a9ed8a765dc` | PASS |
| `dac` | cores3 `port-a` | `unit.DACUnit`(MCP4725) | `486539ed6b344322906f9d1cdc3ab27e` | PASS |
| `bps` | sticks3 `custom` | `unit.BPSUnit` | `314b3b3cb242436d815a5b267da426d7` | PASS |
| `adc-v11` | stopwatch `port-a` | `unit.ADCV11Unit`(ADS1110) | `389e56c2584c49bf818088e7f136541a` | PASS |

关键 controller-backed 观测：

- `joystick`（U024 0x52）：注入 `x-raw=37`/`y-raw=201`/`button-raw=1` 后 guest
  `get_x_raw()/get_y_raw()/get_button_status()` 读回 `37/201/1`，QOM 同步；
  `transactions=13`，无输出型 transition。
- `watering`（U101 双端点 GPIO）：注入 `analog-mv=1600` 后 guest `get_raw()`=
  `33832`（与 12-bit ADC→read_u16 预期一致）；`on()/off()/set_pump()` 的
  PUMP_EN pad 写入被 `pump-level/pump-transitions` 观测到 5 次跳变，I2C
  计数保持 0。
- `fader`（U123 双端点 GPIO）：注入 `analog-mv=2500` 后 guest `get_raw()`=`52844`；
  `update_color()`/`update_brightness()` 的 SK6812 帧被捕获为 14 灯 G,R,B，
  `led-frames=7`、`incomplete-frames=0`，QOM `led-rgb` 与 guest buffer 逐项一致。
- `dac`（U012 MCP4725 0x60）：guest `set_raw_value(2048)→get_raw_value()=2048`、
  `set_voltage(1.0)→819`（`get_voltage()=1.0`）、`save_to_eeprom()` 后
  `eeprom-value=819`/`eeprom-writes=1`，再 `set_raw_value(1024)` 后 QOM
  `dac-raw=1024`、`dac-voltage-v≈1.2503`。
- `bps`（U090 BMP280 0x76）：注入 `temperature-c=25.0`/`pressure-pa=101325`
  后 guest `get_temperature()=25.0`、`get_pressure()=1013.25`；再注入
  `10.5 / 95000` 后读回 `10.5 / 950.0`，`get_altitude()` 与驱动 101325 Pa
  海平面公式一致（误差 <0.5 m）。
- `adc-v11`（0x48 ADS1110）：注入 `voltage-mv=1000` 后 guest `get_voltage()=1.0`，
  `get_adc_raw_value()=2623`（与默认配置公式一致）；`set_gain/set_sample_rate/
  set_mode/start_single_conversion` 后 QOM `config-word=0x95`，最终
  `get_voltage()=1.0`。

每个会话在停止前取得 evidence ZIP，停止使用 `purge=0` 并回读保留 history；
`manifest.json`、`serial.log`、`units/runtime.json`、`units/state.json`、
`units/contract.json` 均存在，帧为非空应用画面。

## 0127 修复（0125 的 MCP4725 fast-mode bug）

DAC 证据首次运行暴露了已合入 `0125` 的一个真实模型 bug：官方 `mcp4725`
驱动的 `_write_fast_mode()` 会发送**完整 3 字节 `_BUFFER`**（第 3 字节为陈旧
值），而 `0125` 的 DAC 解码只接受 2 字节、第三字节直接 NACK，冻结 guest 驱动
因此在第一次 `set_raw_value()` 就抛 `OSError(259)`。新增
[`0127-unit-dac-fast-mode-write.patch`](../../../patches/qemu-m5stack-peripherals/0127-unit-dac-fast-mode-write.patch)
接受并忽略 fast-mode 事务的尾字节（`0x60` EEPROM 命令语义不变），**本目录
全部证据都使用 0127 修复后的运行时二进制**。

## 固件与运行时来源

- 参考固件缓存（service 只读、不入 Git）：
  - cores3 `platform/.cache/firmware/cores3/uiflow2.bin` SHA-256
    `1324f12d3ddd5392f47a9eff537f9ce0b01a8e6e36d829b6bd22cdf82d2c1264`
  - atoms3r `…/atoms3r/uiflow2.bin` SHA-256
    `91c0f97c904271d4c47d240165fbf5589d44aa0d753ca17d685bfdce5bff199a`
  - sticks3 `…/sticks3/uiflow2.bin` SHA-256
    `c08196024019273ccadee9b4b3da303567f7ab206fa14edd1af283f04f6e98d8`
  - stopwatch `…/stopwatch/uiflow2.bin` SHA-256
    `99d6482befe094de47bf68ce43618d3868bd62fb1fc72f0b55c0d0c2ea4e7f8d`
- 每个 case 的合并镜像 SHA-256 与探针 SHA-256 记录在
  [`summary.json`](summary.json) 和对应 `report-<unit>.json`。
- QEMU：canonical native layer `75f1d24`（`0109+0110…0119`）+ 已合入
  `0120/0121/0122/0123` + `0125` + 本轮 `0127` DAC 修复；本批实际服务使用的
  `qemu-system-xtensa` SHA-256 为
  `34ca685b745c61b6e90cccd5f83ead2980fd2a36ad7ebd62efecd33c0a4751c9`。
- Device Service：独立端口 `127.0.0.1:8799`、独立 state dir 与 Bearer token；
  用户 `8787` 服务未被触碰。会话使用 `M5_SERVICE_FLASH_MODE=host-image`。

## 复现

```bash
# 1) 启动隔离 Device Service（独立端口/state/token；不要用 8787）
M5_SERVICE_FLASH_MODE=host-image PYTHONPATH=platform/tools \
  python3.12 platform/tools/serve.py 8799 --bind 127.0.0.1 \
  --state-dir .work/unit-batch2-service --api-token "$(cat .work/unit-batch2-service.token)"

# 2) 逐款执行（每款一个可见 session）
export M5_SERVICE_API_TOKEN="$(cat .work/unit-batch2-service.token)"
for pair in "cores3 joystick" "atoms3r watering" "atoms3r fader" \
            "cores3 dac" "sticks3 bps" "stopwatch adc-v11"; do
  set -- $pair
  PYTHONPATH=platform/tools python3.12 tests/units/run_batch2_cases.py \
    --api-url http://127.0.0.1:8799 --device "$1" --case "$2" \
    --out-dir .work/unit-batch2-evidence
done

# 3) 停止服务，保留历史（本批不提交 raw ZIP/帧）
```

## 未覆盖

- `joystick`：U024 原始按键字节的极性/完整 0..255 范围 unresolved（共享模型
  只暴露 0/1）；0x52 与 joystick-v11 冲突；机械行程/电位器线性度 NOT RUN。
- `watering`：水泵电气/扬程/流量与土壤湿度物理 NOT RUN；`read_uv()/get_voltage()`
  需要 S3 ADC 校准 fixture（NOT RUN），本批覆盖的是 `read_u16()` 路径。
- `fader`：LED 光学/调色板感知/RMT 容差/机械手感 NOT RUN；冻结 neopixel
  `set_brightness()` 的 buffer 缩放行为被原样捕获（高 raw 的亮度帧会 wrap/归零），
  换驱动 SHA 可能不同。
- `dac`：EEPROM 保持/耐久与物理 0..3.3V 输出 NOT modeled；`dac-voltage-v` 用
  驱动默认 vdd=5.0V，输出参考 unresolved；本证据需要 0127 修复。
- `bps`：QMP6988/U090-B 变体与 `scan()[0]` 探测顺序不建模；24B 校准为合成值；
  海拔是驱动 101325 Pa 海平面假设；物理气压精度/datasheet 补偿复核 NOT RUN。
- `adc-v11`：ADS1100 vs ADS1110、SPS 集合、2.048V vs VDD 参考 unresolved；
  0x48 与下一批 ameter 冲突；物理电压精度/PGA/分压容差 NOT RUN。
- 每款只回放了表中主机；其它主机/固件、Web bridge、真机全部 NOT RUN，不转授
  未列组合。
- Raw `result.json`、`serial.log`、`frame.png` 与 evidence ZIP 保存在本地
  git-ignored `.work/unit-batch2-evidence/`；提交内容仅为
  [`summary.json`](summary.json) 与本目录 `report-*.json` 摘要。

# Unit 第十一批 7 款已有模型 guest 证据（batch11）

日期：`2026-11-03`。范围：已有 QEMU 模型但仍是 planned 的 7 款：
`glass`、`lorawan-as923`、`lorawan-eu868`、`rf433t`、`rf433r`、
`audioplayer`、`fingerprint2`。本批 **6 PASS + 1 BLOCKED**；不做硬件验证。

本页是验证证据，不定义当前能力；当前能力以
[项目当前状态](../../project-status.md) 为准。

## 关键点

| 项 | 值 |
| --- | --- |
| QEMU 源码状态 | canonical `75f1d24` + canonical 35 层链（0120–0154）；本批未发现需修复的模型 bug，**无 0155 补丁** |
| 运行时二进制 SHA-256 | `9232cb1e64195d1deee72281552676dafd15665fe47335ea16f62930957e99bd` |
| 参考固件 | cores3 `platform/.cache/firmware/cores3/uiflow2.bin` |
| Device Service | 独立 `127.0.0.1:8803`（`.work/unit-batch11-service.port`）、独立 state/token、host-image；未使用 8799/8801，未触碰 8787 |

## 结论

6 款 PASS、1 款 BLOCKED：

| Unit | 主机/端口 | guest 路径 | 结果 |
| --- | --- | --- | --- |
| `lorawan-as923` | cores3 port-a（官方 PORT.C） | 官方 `LoRaWANUnit`（ASR650x wrapper） | PASS（UART 字节层） |
| `lorawan-eu868` | cores3 port-a（官方 PORT.C） | 官方 `LoRaWANUnit` | PASS（UART 字节层） |
| `rf433t` | cores3 port-a（官方 PORT.B） | `machine.Pin` 输出 bitbang（driver-gap） | PASS |
| `rf433r` | cores3 port-a（官方 PORT.B） | `machine.Pin` 输入采样（driver-gap） | PASS |
| `audioplayer` | cores3 port-a（官方 PORT.C） | raw UART 9600 字节（driver-gap） | PASS（字节层） |
| `fingerprint2` | cores3 port-a（官方 PORT.C） | raw UART 115200 字节（driver-gap） | PASS（字节层） |
| `glass` | cores3 port-a（官方 PORT.A） | 官方 `GlassUnit`/M5.addDisplay | **BLOCKED** |

**端口替换**：lorawan/audio/fingerprint 官方 PORT.C、rf433t/r 官方 PORT.B，
host 只准入 cores3 PORT.A；report 记录 `official_port`/替换。

关键观测：

- `lorawan-as923/eu868`：官方驱动构造后 `set_work_mode(1)`/`send_data("HELLO")`；
  QOM tx-hex 含 `AT+CWORKMODE=2`、`AT+CWORKMODE=1`、`AT+DTRX=`，frames-sent/
  injected≥1；只断言 UART 字节层。产品 STM32WLE5/RAK3172 vs ASR650x wrapper
  错配 unresolved；OTAA/ABP/Join/RF/regulatory NOT RUN；guest 预初始化 UART
  的 model-ordering workaround 已记录。
- `rf433t`：8-bit `10101010` GPIO bitbang → QOM bitstream 含该序列、
  bit-count/edge-count≥8；无 Unit 驱动/ASK 表，RF/天线/10dBm NOT RUN。
- `rf433r`：初始 input-level=1，guest 采样后注入 0；guest levels 同时含 1/0，
  QOM samples≥1、input-level=false；无驱动/解码，ASK/-109dBm NOT RUN。
- `audioplayer`：raw UART 9600 发 `7e03010203`，fixture `4f4b0d0a` 回读；
  QOM tx-hex/frames 匹配；无 N9301 命令表，音频/存储 NOT RUN。
- `fingerprint2`：raw UART 115200 发已知 13B 帧，fixture `ef0107` 回读；
  QOM tx-hex/frames 匹配；A-K323CP 无驱动/帧表，指纹/安全 NOT RUN。

## BLOCKED：glass

- 官方 `unit/glass.py` 的 `GlassUnit(port)` 在本参考固件中返回 `Display`
  （`M5.addDisplay` 组合结果），而不是带 `.display` 的包装对象；I2C scan 可
  看到 `0x3D`，但 `Display.fillScreen/fillRect/print` 后 QOM
  `commands=0`、`data-bytes=0`、`command-hex=''`，模型没有看到任何 I2C
  事务。直接 `M5.addDisplay(i2c, 0x3D, {"unit_glass": True})` 也返回
  `Display`，同样无模型可见事务。
- 这是 frozen driver/display-composition 与模型之间的 unresolved 路径；本批
  **没有伪造 PASS**。glass 保持 planned；按键/蜂鸣器静态 fixture 与透明
  OLED 光学均不断言/NOT RUN，0x3D 与 lcd/oled/mini-oled/glass2 冲突。
- 后续若要重开：需要找到该参考固件实际执行 I2C 的 Glass 显示 API（或换用
  明确可用的固件/驱动），再断言 commands/data-bytes/framebuffer-crc/pages。

## 边界

- 全部为 virtual-device validation，不是硬件/光学/射频/音频/生物特征 PASS。
- UART 只断言字节层；RF/蜂窝/LoRaWAN stack/GNSS/音频/指纹语义 NOT RUN。
- PORT.B/C 使用 cores3 PORT.A harness，不能视为产品 PinMap 等价。
- 光学、SSR/LED 电气、IMU 运动、磁力/气压、语音/声学、指纹安全全部 NOT RUN。

## 复现

```bash
M5_SERVICE_FLASH_MODE=host-image \
M5_QEMU_XTENSA="$PWD/.work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa" \
M5_QEMU_XTENSA_ROM_DIR="$PWD/.work/M5StopWatch-QEMU/build/qemu/pc-bios" \
  PYTHONPATH=platform/tools python3.12 platform/tools/serve.py 8803 \
  --bind 127.0.0.1 --state-dir .work/unit-batch11-service \
  --api-token "$(cat .work/unit-batch11-service.token)"

export M5_SERVICE_API_TOKEN="$(cat .work/unit-batch11-service.token)"
PYTHONPATH=platform/tools python3.12 tests/units/run_batch11_cases.py \
  --api-url http://127.0.0.1:8803 --case <unit> --out-dir .work/unit-batch11-evidence
```

未使用 8787；每 session 先 ZIP 后 `purge=0`；原始执行产物留在本地 ignored
`.work`，仓库只提交摘要、哈希与复现命令。

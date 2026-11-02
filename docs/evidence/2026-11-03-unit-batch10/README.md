# Unit 第十批 a 类 6 款虚拟设备证据（batch10 guest / Device Service）

日期：`2026-11-03`。范围：batch10 a 类 6 款建模型 Unit 的 guest/Device Service
证据：`dcssr`、`puzzle`、`dof6`、`dof9`、`dof10`、`asr`。`ina226-1a` 与 b 类
11 款仅登记 planned 契约、无模型，不在本批证据范围。

本页是验证证据，不定义当前能力；当前能力以
[项目当前状态](../../project-status.md) 为准，工作队列以
[项目 Backlog](../../project-backlog.md) 为准。

## 关键点：单一 QEMU 构建 + 0154 证据修复

| 项 | 值 |
| --- | --- |
| QEMU 源码状态 | canonical `75f1d24` + canonical 链 33 层（0120–0152，含 **0152** batch10 模型）+ **0154（本轮证据修复）** |
| 运行时二进制 SHA-256（签名部署副本） | `7e6082330197fc6eaeadc62bbf1dec49045c246412c270564258e8ef74f524f5` |
| 参考固件 | cores3 `platform/.cache/firmware/cores3/uiflow2.bin`，SHA-256 `1324f12d…` |
| Device Service | 独立 state/token/`M5_SERVICE_FLASH_MODE=host-image`；**8799 被另一 agent 服务占用，本轮使用下一个空闲隔离端口**（记录在 `.work/unit-batch10-service.port`）；未触碰 8787 或其他服务 |

## 0154 证据修复：BMI270 模型 fixture

`0154-unit-batch10-evidence-fixes.patch`（base canonical 33 层 through 0152）：

| 根因 | 影响 | 修复 |
| --- | --- | --- |
| 冻结通用 `BMI270` 驱动加载 CONFIG_DATA 后 poll `INTERNAL_STATUS` bit0；模型接受 init burst 但不执行，且从未置 init-complete 位 | guest `BMI270(...)` 初始化超时，dof6/dof9/dof10 无法读数 | 在 `bmi270_refresh` 中把 0x21 置 0x01（**状态 fixture，不宣称 blob 执行**） |
| 驱动从 0x22 以 little-endian int16 读 TEMP；模型只在 0x20 写 big-endian 温度 | guest 温度读到 0/错误值 | 在 0x22 用 **little-endian** 别名同一 synthetic 温度；保留 0x20 旧布局给 batch-7 mini-imu-pro |

修复后通用 BMI270 驱动可初始化并读取 accel/gyro/temp fixture；dof9/dof10 的
BMM350/SPA06 仍未建模，相关路径如实 BLOCKED。

## 结论

6 款各建 1 个可见 session，均运行 guest 侧冻结驱动或明确记录的通用/原始
字节路径；通过后 profile 升 implemented，catalog 保持 partial。

| Unit | 主机/端口 | guest 路径 | 结果 |
| --- | --- | --- | --- |
| `dcssr` | cores3 port-a (官方 PORT.A) | 官方 `DCSSRUnit`（`unit/acssr.py` 别名，I2C 0x50） | PASS |
| `puzzle` | cores3 port-a（官方 PORT.B） | generic `RGBUnit`/SK6812 64 灯（**driver-gap**） | PASS（driver-gap 记录） |
| `dof6` | cores3 port-a (官方 PORT.A) | generic frozen `BMI270` 驱动（无 Unit DoF 驱动） | PASS（仅 BMI270 子集） |
| `dof9` | cores3 port-a (官方 PORT.A) | generic frozen `BMI270` 驱动 | PASS（仅 BMI270；BMM350 BLOCKED） |
| `dof10` | cores3 port-a (官方 PORT.A) | generic frozen `BMI270` 驱动 | PASS（仅 BMI270；BMM350/SPA06 BLOCKED） |
| `asr` | cores3 port-a（官方 PORT.C） | raw UART 115200 AA55 帧（**无 unit/asr.py**） | PASS（字节层） |

**端口替换**：puzzle 官方 PORT.B、asr 官方 PORT.C，host-port 只准入 cores3
PORT.A；两个 session 用 PORT.A GPIO 2/1 harness，report 记录
`official_port`/`runtime_port_substitution`。dcssr/dof 官方 PORT.A 无需替换。

关键观测（完整在 report/summary）：

- `dcssr`：guest on/off/on=1/0/1，`get_firmware_version()`=1；
  QOM relay-level=true、relay-transitions≥3、led-rgb=0x112233、i2c-address=0x50。
- `puzzle`：generic `RGBUnit(...,64)` + `fill_color(0x112233)` → QOM 64 灯全
  0x112233、led-frames≥1、incomplete=0；driver-gap 明确记录。
- `dof6/dof9/dof10`：fixtures accel=(0.5,-0.25,0.125)g、gyro=(100,-50,25)dps、
  temp=27°C；guest 通用 BMI270 驱动读到 accel=(0.125,-0.0625,0.03125)、
  gyro≈(100.09765,-50.048824,25.024412)、temp=25.0；QOM fixtures 与
  whoami=0x24 一致，I2C transactions>0。数值是驱动自身 4g/2000dps scale 与
  23°C offset 下的确定性 fixture readback，**不是物理单位**。
- `asr`：guest 发 `aa 55 45 55 aa`（版本命令）并收到 fixture `aa55…`；QOM
  tx-hex 含该帧、command-id=0x45、frames-sent/injected≥1；语音/声学 NOT RUN。

每个会话先取 evidence ZIP，`purge=0` 停止并回读 history；ZIP 含
manifest/serial/units runtime+state+contract，帧为非空应用画面。

## BLOCKED / 未覆盖

- `dof9`：**BMM350 0x14 未建模**（无 driver/寄存器表）→ magnetic/heading
  路径 BLOCKED，不伪造磁力 fixture。
- `dof10`：**BMM350 0x14 + SPA06-003 0x76 未建模** → magnetic/pressure/
  heading/altitude BLOCKED；不用 BMP280 替代 SPA06，不伪造气压。
- `puzzle`：无 `unit/puzzle.py`；generic SK6812 路径只断言 RMT LED 帧，
  WS2812E vs WS2812C 时序/字节序、光学/亮度/热/功率、级联 IN/OUT 方向 NOT RUN。
- `asr`：无 `unit/asr.py`；raw AA55 字节帧只断言 TX/RX 字节与 command-id，
  语音识别/AEC/麦克风/扬声器、CI-03T 自定义固件命令表 NOT RUN。
- `dcssr`：Modbus/RS485 模式不在 Unit attachment；SSR 10A/DC24-220V/隔离/
  开关寿命/热/真实负载 NOT RUN。
- `dof6/dof9/dof10`：BMI270 init blob 接受但不执行；量程/运动检测/真实运动/
  振动/温度物理 NOT RUN；0x68 与 mini-imu 系冲突，0x14 与 bmm350，0x76 与
  env 系冲突。
- 所有 6 款仅 cores3 + 本固件 SHA + 本 QEMU 二进制组合；不转授其他主机。

## 复现

```bash
# 树：canonical + 0120..0152 + 0153；删除 build 后重新 configure
M5_SERVICE_FLASH_MODE=host-image \
M5_QEMU_XTENSA="$PWD/.work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa" \
M5_QEMU_XTENSA_ROM_DIR="$PWD/.work/M5StopWatch-QEMU/build/qemu/pc-bios" \
  PYTHONPATH=platform/tools python3.12 platform/tools/serve.py <free-port> \
  --bind 127.0.0.1 --state-dir .work/unit-batch10-service \
  --api-token "$(cat .work/unit-batch10-service.token)"

export M5_SERVICE_API_TOKEN="$(cat .work/unit-batch10-service.token)"
PYTHONPATH=platform/tools python3.12 tests/units/run_batch10_cases.py \
  --api-url http://127.0.0.1:<free-port> --case <unit> --out-dir .work/unit-batch10-evidence
```

未使用 `8787`；每个 session 停止时 `purge=0`；原始 ZIP/帧/串口日志留在本地
忽略的 `.work`，仓库只提交摘要、哈希与复现命令。

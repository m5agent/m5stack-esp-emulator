# Unit 第一批 B 类 4 款（dlight/accel/4relay/weight-i2c）虚拟设备证据

日期：`2026-11-02`。范围：把
[Unit 第一批协议研究](../../unit-research/2026-11-02-batch1-protocols.md) §4.6–4.9 的
B 类 4 款 I2C Unit 接入 QEMU I2C 事务数据面（0119，含 0120 修复），并通过
**独立 Device Service** 的可见 `/api/v1` 会话记录 **虚拟设备**证据。物理硬件、
电气、光学、机械与称重语义全部 `NOT RUN`。

本页是验证证据，不定义当前能力；当前能力以
[项目当前状态](../../project-status.md) 为准，工作队列以
[项目 Backlog](../../project-backlog.md) 为准。所有结果只覆盖表内记录的
主机、固件 SHA、QEMU 二进制 SHA 和检查项，不能转授未列出的主机或固件。

## 结论

4 款各建 1 个可见 session，均在 guest 内运行参考固件自带的**原始冻结
UIFlow2 I2C Unit 驱动**，经真实 SoC I2C 控制器与板级接线产生或读取寄存器，
没有 host 端直写驱动返回值：

| Unit | 主机 / 端口 | 原始驱动类 | 会话 | 结果 |
| --- | --- | --- | --- | --- |
| `dlight` | atoms3r `custom` | `unit.DLightUnit` | `7fb1b36c27494b799482fabf673688b9` | PASS |
| `accel` | sticks3 `custom` | `unit.AccelUnit` | `1500ee0beeee48cc935b8420c234a313` | PASS |
| `4relay` | cores3 `port-a` | `unit.Relay4Unit` | `78d80e1497f84bf298176f014f3f5049` | PASS |
| `weight-i2c` | stopwatch `port-a` | `unit.WeightI2CUnit` | `3a022424ecac44c7803191596103f001` | PASS |

关键 controller-backed 观测：

- `dlight`（BH1750 0x23）：注入 `illuminance-lx` 400→1000 后，guest 冻结
  `driver/bh1750.py` 的 `get_lux()` 输出 `400.0→999.9999`（转换窗口内按
  `raw=lux*1.2*sensitivity` 反算、1 LSB≈0.42lx 的量化误差），QOM fixture 精确
  回读 1000，`transactions=4/read-bytes=4/written-bytes=1`。
- `accel`（ADXL345 0x53）：注入 `accel-x-g=1.0 / y=-0.5 / z=2.0` 后，guest
  `get_accel()` 精确得到 `9.80665 / -4.903325 / 19.6133 m/s²`（=raw×0.004×
  9.80665，raw 由 g fixture 换算），QOM 三轴 fixture 精确回读。
- `4relay`（U097 0x26）：`set_mode(1)`→`get_mode()=1`，`set_relay_state(1,1)`
  /`set_led_state(1,1)` 的读回与 QOM `relay-1-level`/`led-1-level` 一致；
  `set_relay_all(1)` 写 `0xff` 使四路 relay 与 LED 全亮（官方 Python 驱动
  副作用），`set_relay_all(0)` 全灭；最终 relay2=on、其余 off，`output-transitions`
  与 I2C 计数均增长。
- `weight-i2c`（U180 0x26）：注入 `weight-g=12.34 / adc-raw=1234567` 后，
  guest 读 `0x00=1234567`、`0x10≈12.340`、`0x60` 经驱动 `/100` 得 `12`、
  `0x70="12.340"`、`0xFE=3`/`0xFF=0x26`；`set_calibration(0,0,100,100000)`、
  `set_reset_offset()`、低通/平均/EMA 滤波写入后读回 `1/10/20`，QOM
  `written-bytes` 由 38 增到 50。该 Unit 与 4relay 默认地址同为 0x26，本轮用
  独立 StopWatch 会话，未与 4relay 共存于同一条总线。

每个会话在停止前取得 evidence ZIP，停止使用 `purge=0` 并回读保留
history；`manifest.json`、`serial.log`、`units/runtime.json`、
`units/state.json`、`units/contract.json` 均存在，帧为非空应用画面。

## 0120 修复（0119 的 BH1750 命令掩码 bug）

B 类证据首次运行暴露了已合入 `0119` 的一个真实模型 bug：`dlight` 命令解码
用 `(data & 0xe0)` 判断 continuous/one-time 测量命令，而这两类命令占据
bit4/bit5（`0x10`/`0x20`），掩码后恒为 0，导致每条测量命令都被 NACK；
冻结的官方 `driver/bh1750.py` 在构造函数里就写 `0x10`，因此 guest 立即
`OSError(259)`。修复补丁
[`0120-unit-i2c-dlight-command-mask.patch`](../../../patches/qemu-m5stack-peripherals/0120-unit-i2c-dlight-command-mask.patch)
把命令类判断统一改为 `0xf0`（`0x40..0x5f`/`0x60..0x7f` 的 MTreg 语义不变），
**本目录全部 B 类证据都使用 0120 修复后的运行时二进制**。

## 固件与运行时来源

- 参考固件缓存（service 只读、不入 Git）：
  - cores3 `platform/.cache/firmware/cores3/uiflow2.bin`
    SHA-256 `1324f12d3ddd5392f47a9eff537f9ce0b01a8e6e36d829b6bd22cdf82d2c1264`
  - atoms3r `…/atoms3r/uiflow2.bin` SHA-256
    `91c0f97c904271d4c47d240165fbf5589d44aa0d753ca17d685bfdce5bff199a`
  - sticks3 `…/sticks3/uiflow2.bin` SHA-256
    `c08196024019273ccadee9b4b3da303567f7ab206fa14edd1af283f04f6e98d8`
  - stopwatch `…/stopwatch/uiflow2.bin` SHA-256
    `99d6482befe094de47bf68ce43618d3868bd62fb1fc72f0b55c0d0c2ea4e7f8d`
- 每个 case 的合并镜像 SHA-256 与探针 SHA-256 记录在
  [`summary.json`](summary.json) 和对应 `report-<unit>.json`。
- QEMU：canonical native layer `75f1d24`（`0109` + `0110…0119`）之上应用
  `0120` 修复构建；本批实际服务使用的 `qemu-system-xtensa` SHA-256 为
  `e6f529fb7b925bc63877d124892b5af2a5a66fdcf10b180fedcc7c4b14b9b990`。
- Device Service：独立端口 `127.0.0.1:8799`、独立 state dir 与 Bearer token；
  用户 `8787` 服务未被触碰。会话使用 `M5_SERVICE_FLASH_MODE=host-image`。

## 复现

```bash
# 1) 启动隔离 Device Service（独立端口/state/token；不要用 8787）
M5_SERVICE_FLASH_MODE=host-image PYTHONPATH=platform/tools \
  python3.12 platform/tools/serve.py 8799 --bind 127.0.0.1 \
  --state-dir .work/unit-bclass-service --api-token "$(cat .work/unit-bclass-service.token)"

# 2) 逐款执行（每款一个可见 session）
export M5_SERVICE_API_TOKEN="$(cat .work/unit-bclass-service.token)"
for pair in "atoms3r dlight" "sticks3 accel" "cores3 4relay" "stopwatch weight-i2c"; do
  set -- $pair
  PYTHONPATH=platform/tools python3.12 tests/units/run_i2c_cases.py \
    --api-url http://127.0.0.1:8799 --device "$1" --case "$2" \
    --out-dir .work/unit-bclass-evidence
done

# 3) 停止服务，保留历史（本批不提交 raw ZIP/帧）
```

## 未覆盖

- 全部物理与电气语义 `NOT RUN`：4relay 触点/负载/吸合时间/耐压与隔离，
  dlight 光学/照度精度/MTreg 上电默认与产品页量程编码一致性，accel 物理
  加速度/量程 LSB/机械事件，weight-i2c 称重/校准运算/HX711 时序/温漂。
- `4relay` 产品页 Protocol 表与两份官方可执行驱动的位序相反；本实现采用
  驱动序（RELAY1=bit0/LED1=bit4），页面反序作为已登记冲突，不能混用。
- `weight-i2c` 与 `4relay` 默认地址同为 0x26，不能在同一条 I2C 总线共存；
  0x60 版本语义（快照 raw int vs master `/100`）仍 unresolved，本批冻结驱动
  表现为 `/100`。
- `accel` 的 DEVID(0x00) 仍为 reserved/unresolved（驱动从不读，不猜 0xE5）；
  tap/motion/free-fall 检测器只做到寄存器/INT_SOURCE 读清级别。
- 每款只回放了表中主机；其它主机/固件组合与 Web 输入桥
  （`live_browser`）本批未运行。
- Raw `result.json`、`serial.log`、`frame.png` 与 evidence ZIP 保存在本地
  git-ignored `.work/unit-bclass-evidence/`；提交内容仅为
  [`summary.json`](summary.json) 与本目录 `report-*.json` 摘要。

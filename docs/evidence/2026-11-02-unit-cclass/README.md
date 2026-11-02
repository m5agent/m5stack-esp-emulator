# Unit 第一批 C 类 3 款（ncir2/extio2/hbridge）虚拟设备证据

日期：`2026-11-02`。范围：把
[Unit 第一批协议研究](../../unit-research/2026-11-02-batch1-protocols.md) §4.10–4.12 的
C 类 3 款 I2C Unit 接入 QEMU I2C 寄存器事务数据面（0123），并通过
**独立 Device Service** 的可见 `/api/v1` 会话记录 **虚拟设备**证据。物理硬件、
红外光学、电气与机械语义全部 `NOT RUN`。

本页是验证证据，不定义当前能力；当前能力以
[项目当前状态](../../project-status.md) 为准，工作队列以
[项目 Backlog](../../project-backlog.md) 为准。所有结果只覆盖表内记录的
主机、固件 SHA、QEMU 二进制 SHA 和检查项，不能转授未列出的主机或固件。

## 结论

3 款各建 1 个可见 session，均在 guest 内运行参考固件自带的**原始冻结
UIFlow2 I2C Unit 驱动**，经真实 SoC I2C 控制器读写寄存器，没有 host 端
直写驱动返回值：

| Unit | 主机 / 端口 | 原始驱动类 | 会话 | 结果 |
| --- | --- | --- | --- | --- |
| `ncir2` | atoms3r `custom` | `unit.NCIR2Unit` | `40c25071cb53488b892150f726da75a2` | PASS |
| `extio2` | sticks3 `custom` | `unit.EXTIO2Unit` | `c09fbb7f4f9346cdbbd0f017b9b6d76c` | PASS |
| `hbridge` | cores3 `port-a` | `unit.HbridgeUnit` | `95e5f75fd77c49f9b490c6c4f3946357` | PASS |

关键 controller-backed 观测：

- `ncir2`（U150 0x5A）：注入 `object-c=25.5`/`chip-c=30.25`/`button-pressed=true`
  后 guest 冻结驱动输出 `25.5 / 30.25 / 1`；`-20.5°C` 负温度可编码；注入产品页
  上限 `380°C` 时 signed int16×0.01 编码饱和为 `327.67°C`（边界显式记录，不
  声明 380°C 正确回读）。发射率写 0.5 读回 0.5、阈值 5/40、报警 LED
  `[17,34,51]`、蜂鸣器 `2000/50/1`、RGB `[10,11,12]`、`0xFE=1`/`0xFF=90`；
  QOM `rgb-led=0x0A0B0C`、`buzzer-on=true`，I2C 计数增长。
- `extio2`（U011-B 0x45）：写入 8 通道模式 `[0,1,2,3,4,0,1,2]`、输出
  `ch0/1/5/6=1`、舵机角 90、脉宽 1500、RGB `0x112233`/`0x445566` 后 guest 读回
  与 QOM 数组一致；注入 `input-levels`/`adc-mv` 后 8 通道数字输入与
  adc8/adc12 读回精确等于 8/12-bit 量化值（如 3300mV→255/4095），
  `read_fw_version()=7`、地址 0x45。
- `hbridge`（U160 0x20）：注入 `adc-mv=1650`/`vin-current-a=1.5` 后 guest 读
  ADC8=128、ADC16=2048（量化值）、VIN current=1.5；`set_direction(1)` /
  `set_16bit_pwm(32767)` / `set_pwm_freq(500)` 读回一致，随后
  `set_direction(2)`/`set_8bit_pwm(128)` 的最终 QOM `direction=2`、
  `pwm-duty-pct≈50.196`、`pwm-frequency-hz=500`，身份 `0xFE=1`/`0xFF=32`。

每个会话在停止前取得 evidence ZIP，停止使用 `purge=0` 并回读保留
history；`manifest.json`、`serial.log`、`units/runtime.json`、
`units/state.json`、`units/contract.json` 均存在，帧为非空应用画面。

## 固件与运行时来源

- 参考固件缓存（service 只读、不入 Git）：
  - atoms3r `platform/.cache/firmware/atoms3r/uiflow2.bin` SHA-256
    `91c0f97c904271d4c47d240165fbf5589d44aa0d753ca17d685bfdce5bff199a`
  - sticks3 `…/sticks3/uiflow2.bin` SHA-256
    `c08196024019273ccadee9b4b3da303567f7ab206fa14edd1af283f04f6e98d8`
  - cores3 `…/cores3/uiflow2.bin` SHA-256
    `1324f12d3ddd5392f47a9eff537f9ce0b01a8e6e36d829b6bd22cdf82d2c1264`
- 每个 case 的合并镜像 SHA-256 与探针 SHA-256 记录在
  [`summary.json`](summary.json) 和对应 `report-<unit>.json`。
- QEMU：canonical native layer `75f1d24`（`0109+0110…0119`）+ 已合入
  `0120`/`0121`/`0122` + 本轮 `0123-unit-i2c-batch3.patch`；本批实际服务使用的
  `qemu-system-xtensa` SHA-256 为
  `8a19eb503f23a262de9a8872777599445a85d3df0e17b34a6e98b722373ab0f1`。
- Device Service：独立端口 `127.0.0.1:8799`、独立 state dir 与 Bearer token；
  用户 `8787` 服务未被触碰。会话使用 `M5_SERVICE_FLASH_MODE=host-image`。
- 会话创建前的 `unit-input` 校验要求 catalog 的数组 input 声明 `items`；
  本轮给 `extio2` 的 `input-levels`(bool×8) 与 `adc-mv`(number×8, 0..3300)
  补齐 `items/minItems/maxItems`，否则服务会拒绝注入。

## 复现

```bash
# 1) 启动隔离 Device Service（独立端口/state/token；不要用 8787）
M5_SERVICE_FLASH_MODE=host-image PYTHONPATH=platform/tools \
  python3.12 platform/tools/serve.py 8799 --bind 127.0.0.1 \
  --state-dir .work/unit-cclass-service --api-token "$(cat .work/unit-cclass-service.token)"

# 2) 逐款执行（每款一个可见 session）
export M5_SERVICE_API_TOKEN="$(cat .work/unit-cclass-service.token)"
for pair in "atoms3r ncir2" "sticks3 extio2" "cores3 hbridge"; do
  set -- $pair
  PYTHONPATH=platform/tools python3.12 tests/units/run_cclass_cases.py \
    --api-url http://127.0.0.1:8799 --device "$1" --case "$2" \
    --out-dir .work/unit-cclass-evidence
done

# 3) 停止服务，保留历史（本批不提交 raw ZIP/帧）
```

## 未覆盖

- 全部物理语义 `NOT RUN`：ncir2 红外光学/视场/发射率物理/温度精度，
  extio2 电气电平/NeoPixel 光学/舵机运动/ADC 精度，hbridge 电机扭矩/电流/
  换向与制动时序/RZ7899 死区与保护。
- `ncir2`：STM32 报警状态机不建模；0x5A 与已登记 `ncir`(MLX90614) 地址冲突，
  不能同总线；驱动 signed int16×0.01 编码上限 +327.67°C，产品页 380°C 量程
  与饱和策略仍 unresolved（本轮证据显式记录饱和边界，不声明 380°C 正确）。
- `extio2`：Protocol v1/v3 PDF 未读；ADC 满量程/参考电压、舵机角度/脉宽单位、
  芯片内部 RGB 字节序 unresolved；冻结固件驱动是否含 0x90/0xA0 PWM 未确认；
  ST IAP/升级不建模。
- `hbridge`：无独立 protocol PDF，仅按可执行驱动；0x30 VIN 电流仅 v1.1 硬件有，
  U160 v1.0 读回语义 unresolved（本批为 fixture 路径，非物理电流测量）。
- 每款只回放了表中主机；其它主机/固件组合与 Web 输入桥（`live_browser`）
  本批未运行。
- Raw `result.json`、`serial.log`、`frame.png` 与 evidence ZIP 保存在本地
  git-ignored `.work/unit-cclass-evidence/`；提交内容仅为
  [`summary.json`](summary.json) 与本目录 `report-*.json` 摘要。

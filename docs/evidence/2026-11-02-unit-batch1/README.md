# Unit 第一批 A 类 5 款（ssr/earth/hall/reflective-ir/vibrator）虚拟设备证据

日期：`2026-11-02`。范围：把
[Unit 第一批协议研究](../../unit-research/2026-11-02-batch1-protocols.md) 中 A 类 5 款
接入 QEMU 控制器数据面，并通过**独立 Device Service** 的可见 `/api/v1` 会话记录
**虚拟设备**证据。物理硬件、电气、光学、机械与磁场语义全部 `NOT RUN`。

本页是验证证据，不定义当前能力；当前能力以
[项目当前状态](../../project-status.md) 为准，工作队列以
[项目 Backlog](../../project-backlog.md) 为准。所有结果只覆盖表内记录的
主机、固件 SHA、QEMU 二进制 SHA 和检查项，不能转授未列出的主机或固件。

## 结论

5 款各建 1 个可见 session，均在 guest 内运行参考固件自带的**原始冻结
Unit 驱动**，通过真实 SoC GPIO/ADC/LEDC 控制器与板级接线产生并观测数据，
没有 host 端直写驱动返回值：

| Unit | 主机 / 端口 | 原始驱动类 | 会话 | 结果 |
| --- | --- | --- | --- | --- |
| `ssr` | cores3 `port-a` | `unit.SSRUnit` | `821f13174653417ba904f9f4b72da6a8` | PASS |
| `earth` | atoms3r `custom` | `unit.EarthUnit` | `ec2ab3ec67fb46f5a708d2a41e9f6372` | PASS |
| `hall` | sticks3 `custom` | `unit.HallEffectUnit` | `06ddb6a418b84a67ae94ea043163261f` | PASS |
| `reflective-ir` | stopwatch `port-a` | `unit.ReflectiveIRUnit` | `2824aa6ae81a4e0c9cc4d7a6beb1d49c` | PASS |
| `vibrator` | cores3 `port-a` | `unit.VibratorUnit` | `adbe5d4f57c349e18260d00f7a9d52b4` | PASS |

关键 controller-backed 观测：

- `ssr`：guest `SSRUnit.on()/off()/set_state(1)` 驱动的黄线 pad
  `output-level` 依次为 true→false→true→false，`output-transitions` 计数增长，
  且 `transactions/read-bytes/written-bytes` 恒为 0（该 Unit 没有 I2C 数据面）。
  官方驱动没有 `get_status()`；模型只暴露 guest 驱动的 pad 输出。
- `earth`：注入 `analog-mv` 1000→2500、`digital-level` true→false 后，QOM 精确
  回读注入值；guest 原始 `read_u16` 从 `21141` 增到 `52844`，比较器数字电平
  1→0，`adc-samples` > 0。`read_uv()`/`humidity()` 需要 S3 ADC 校准 eFuse
  fixture，本批未应用，记录为边界而非 PASS。
- `hall`：低有效白线输入。QOM `magnetic-detected` true 时 `input-level=false`，
  guest `get_status()` 读 0 且触发 active 回调；释放后回到 true/1 并触发
  negative 回调，两个方向的 guest IRQ 都来自真实 GPIO 输入边沿。
- `reflective-ir`：注入 `analog-mv=2000` + 数字电平上升/下降后，QOM 精确回读，
  guest 原始 ADC `26422→42282`，数字电平 1→0，`GPIO_RIR_EVENT 1/0` 两个
  边沿回调都出现，`adc-samples` > 0。
- `vibrator`：guest `VibratorUnit.set_freq(4000)/set_duty(50→25)/turn_off()`
  经真实 LEDC 配置被观测为 `frequency-hz≈4000`、`duty-pct≈49.99/24.99/0`；
  `once(freq=2000,duty=60,duration=300)` 把数据面编程为 2000Hz/60%，但
  **one-shot 完成回调没有把 duty 清 0**（原始 `Haptic`/`SoftTimer` callback
  gap，与仓库已记录的 Buzzer 风险同族）。模型忠实保留最后编程值；
  one-shot completion 不作为 PASS 声明。

每个会话在停止前取得 evidence ZIP，停止使用 `purge=0` 并回读保留
history；`manifest.json`、`serial.log`、`units/runtime.json`、
`units/state.json`、`units/contract.json` 均存在，帧为非空应用画面。

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
- QEMU：`espressif/qemu` `40edccac415693c5130f91c01d84176ae6008566` 上按
  native-lock 顺序（到 `0109`，含 `0110/0111/0112`）叠加 `0113`
  （Basic v2.7，来自已合并 PR）与
  [`0114-unit-gpio-batch1.patch`](../../../patches/qemu-m5stack-peripherals/0114-unit-gpio-batch1.patch)
  的 A 类 Unit 数据面构建；本批实际服务使用的
  `qemu-system-xtensa` SHA-256 为
  `d837e0e6bea85fff0406979ae98acea235f14c9779d79c8617f42b2d6cd41aa5`。
- Device Service：独立端口 `127.0.0.1:8799`、独立 state dir 与 Bearer token；
  用户 `8787` 服务未被触碰。会话使用 `M5_SERVICE_FLASH_MODE=host-image`，
  不依赖宿主 esptool。

## 复现

```bash
# 1) 启动隔离 Device Service（独立端口/state/token；不要用 8787）
M5_SERVICE_FLASH_MODE=host-image PYTHONPATH=platform/tools \
  python3.12 platform/tools/serve.py 8799 --bind 127.0.0.1 \
  --state-dir .work/unit-batch1-service --api-token "$(cat .work/unit-batch1-service.token)"

# 2) 逐款执行（每款一个可见 session；需本地 reference 固件缓存与 unit 0114 QEMU）
export M5_SERVICE_API_TOKEN="$(cat .work/unit-batch1-service.token)"
for pair in "cores3 ssr" "atoms3r earth" "sticks3 hall" "stopwatch reflective-ir" "cores3 vibrator"; do
  set -- $pair
  PYTHONPATH=platform/tools python3.12 tests/units/run_gpio_cases.py \
    --api-url http://127.0.0.1:8799 --device "$1" --case "$2" \
    --out-dir .work/unit-batch1-evidence
done

# 3) 停止服务，保留历史（本批不提交 raw ZIP/帧）
```

## 未覆盖

- 全部物理与电气语义 `NOT RUN`：SSR 过零/过流/负载隔离，Earth 探针化学与
  阈值真值，Hall 三颗 A3144E+74HC08D 空间逻辑与磁场强度，Reflective IR 的
  LM393 阈值电路/比较器极性应用语义/光学响应，Vibrator 电机振动强度/频率最优值。
- `earth` 的 `read_uv()`/`humidity()` 需要 `esp32s3` ADC 校准 eFuse fixture，
  本批未应用；原始 ADC 与数字比较器路径已覆盖。
- `vibrator` 的 `Haptic.once()` one-shot 完成未观测（原始 SoftTimer callback gap）。
- 每款只回放了表中主机；其它主机/固件组合不继承 PASS，Web 输入桥
  （`live_browser`）本批未运行。
- Raw `result.json`、`serial.log`、`frame.png` 与 evidence ZIP 保存在本地
  git-ignored `.work/unit-batch1-evidence/`；提交内容仅为
  [`summary.json`](summary.json) 与本目录 `report-*.json` 摘要。

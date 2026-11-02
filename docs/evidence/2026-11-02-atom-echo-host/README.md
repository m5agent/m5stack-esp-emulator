# Atom Echo / Atom Voice（C008-C）虚拟主机接入（限定验证）

日期：`2026-11-02`。范围：把视觉库存中仅有外壳的 Atom Echo（官方产品页名
**Atom Voice**，SKU `C008-C`）接入为独立 classic ESP32 原生 QEMU 主机
（machine `m5atomecho`）。本记录只声明虚拟设备结果：官方 UIFlow2 启动、
板级识别 142、SK6812 RMT、QMP 按键注入回读、Grove I2C 控制器扫描、
NS4168 I2S 扬声器 PCM 捕获与 SPM1423 PDM RX 注入路径。物理电气/声学
`NOT RUN`。

## 与任务前提的差异（重要）

任务文本按研究初稿写成 "ES8311 codec + I2S0 放音"。实测官方 C008-C 与
`BOARD_ID=142` 的 M5Unified 板级路径**没有板载 ES8311/I2C codec**：

- 官方 PinMap 与 M5Unified `board_M5AtomVoice` 分支都是
  **NS4168（无寄存器 I2S 功放）**：`pin_bck=GPIO19`、`pin_ws=GPIO33`、
  `pin_data_out=GPIO22`；M5Unified 对 classic ESP32 的扬声器默认使用
  **I2S1**（`M5UNIFIED_I2S_PORT_COUNT-1`）。补充 trace 实测 I2S1 有 8,070 次
  寄存器写、I2S1 DMA PCM `1,366,016` bytes，I2S0 无 PCM 捕获。
- 麦克风是 **SPM1423 PDM**：`pin_data_in=GPIO23`、`pin_ws=GPIO33`，M5Unified
  使用 **I2S0**（131 次寄存器写）。
- 官方 MicroPython 镜像里能搜到 ES8311 字符串，是 M5Unified 共享库编译进去的
  其它板（CoreS3/Atom VoiceS3R 等）代码，AtomVoice 板级分支不走该路径。
- 因此 probe 保留了 `ATOMECHO_I2C_SCAN` 与 `ATOMECHO_ES8311 absent` 标记，
  如实记录 scan 结果；**没有伪造 ES8311 设备模型或 I2C 从设备**。
- 两路控制器（I2S1 TX / I2S0 PDM RX）是分别编程的；NS4168 LRCK 与 SPM1423
  CLK 在硬件上共用 G33，但数字模型不建模 pad 争用，因此"半双工/同时录放"
  不在本记录范围。

## 结果

- 新增机器 `m5atomecho`（补丁 `0117-atomecho-board.patch`）：
  ESP32-PICO-D4、4 MB Flash、无 PSRAM、无屏；复用 classic Atom 板级逻辑
  （SK6812 在 G27、USER 按键 G39、1×1 诊断 console、input handler、Unit
  runtime、classic ADC）；NS4168/SPM1423 信号由 SoC 级 ESP32 I2S 模型提供，
  不额外挂设备；IR G12 未接线、未验收。
- 固件来源沿用 AtomU 引入的固定 SHA 官方 GitHub release 受控策略：
  `m5stack/uiflow-micropython` release `2.5.4` 的 Atom Echo 精确板镜像
  `uiflow-e437118-esp32-4mb-atomecho-v2.5.4-20261030.bin`，
  4,186,112 B，SHA-256
  `8bae873945e85eff496670b9fbddcf7b5fecf31c99eba786fc15cce8c8e89472`；
  `fetch_firmware.py` 直接下载并按目录 sha256 fail-closed 校验。
- 分区：`nvs 0x9000/0x6000`、`phy_init 0xF000/0x1000`、
  `factory 0x10000/0x361000`、`vfs 0x371000/0x8D000`；工具补 `0xFF` 到
  4 MiB，probe 只替换 vfs 卷。probe 镜像 SHA-256
  `ec3dbf2b4e712586efac19a5e5f0b96e0dc85f222f8784440ada3fb7eae30ca5`。
- 设备矩阵 case `atom-echo`（console 模式）三次独立运行 `PASS`（3/3）。
  同一 guest 内输出：

  ```
  ATOMECHO_BOOT_FLAG / ATOMECHO_MAIN_START / ATOMECHO_M5_BEGIN_OK
  ATOMECHO_BOARD 142
  ATOMECHO_I2C_SCAN ['0x48'] / ATOMECHO_ES8311 absent
  ATOMECHO_RGB 1 204060
  ATOMECHO_SPEAKER_BEGIN True / ATOMECHO_SPEAKER_RUNNING 1 / ATOMECHO_SPEAKER_STATUS ok
  ATOMECHO_MIC_BEGIN True / ATOMECHO_MIC_RECORD True
  ATOMECHO_MIC_PCM 6325 255 / ATOMECHO_MIC_STATUS ok
  ATOMECHO_PROBE_READY
  ATOMECHO_BUTTON_STATE 0 0 / 1 1 / 0 1
  ```

- 扬声器证据：NS4168 I2S1 标准模式经真实 DMA 描述符写出，宿主机在 DMA 边界
  捕获 `142,336–145,920` bytes PCM，`47,920` 非零采样，
  peak-to-peak `34,567`；字节数随标记触发停止点变化，非零/峰峰值三次一致。
  `M5SW_I2S_DMA_IRQ` 是 ESP32-S3 模型使用的变量，classic I2S 模型不需要。
- 麦克风证据：矩阵 runner 生成确定性 16-bit 宿主 PCM fixture
  （16,000 samples，`M5SW_I2S_RX_PCM_FILE`），guest 通过 I2S0 PDM RX 真实
  DMA 读取，`ATOMECHO_MIC_PCM` 非零、peak 253–255、状态 ok。这是**注入
  数据面**，不是真实麦克风/声学。
- 按键证据：QMP `key:a` 经板级 input handler 驱动真实 GPIO39 输入寄存器，
  guest 侧 UIFlow2 BtnA 读到按下/释放并重绘 RGB。
- RGB 证据：QOM `/machine/onboard_io` 解码 `led-rgb=2113632`（`0x204060`）、
  `led-frames=5`（RMT 完整帧计数 ≥ 3）。
- Grove 证据：guest 用 `machine.I2C(0, scl=Pin(32), sda=Pin(26))` 扫描到
  `['0x48']`。`0x48` 是 QEMU classic machine 自带 `tmp105`，不是板载器件；
  `0x18`（ES8311）不存在。
- 唯一的运行间差异是 ESP-IDF `i2c.master` 启动告警的虚拟时间戳和
  `ATOMECHO_MIC_PCM` 的时序派生值；结构标记与 QOM 值三次完全一致
  （serial log 哈希取 run 1，`6f83e371…`）。

## 边界

- NS4168 是无寄存器功放：模拟增益、PA 电气、扬声器声学均未建模；没有
  "功放使能" GPIO 可验证（M5Unified AtomVoice 分支没有 enable callback）。
- SPM1423 只用宿主 PCM fixture 验证数字 RX 路径；真实麦克风、灵敏度/SNR、
  共用 G33 pad 的同时录放时序未验证。
- IR（G12）、Grove Unit 协议、USB/FTDI、UIFlow2 启动菜单/网络、第三方固件、
  浏览器/WASM 准入均未测；无屏、无 PSRAM。
- 本结果不转授 AtomU/Atom Lite/Atom EchoS3R 或任意 Unit；真机、电气、声学、
  机械均 `NOT RUN`。
- 固件来源是 GitHub release asset，不是 M5Burner firmware ID；这是经审查的
  SHA 固定例外。

## 复现

```bash
# 1) 固定 SHA 官方固件（fail-closed 校验，写入 platform/.cache/firmware/atom-echo/）
python3 platform/tools/fetch_firmware.py atom-echo --analyze --chip-id 0x0000

# 2) 三遍设备矩阵（console 模式，host-image 直接启动；runner 生成 RX PCM fixture）
for i in 1 2 3; do
  python3 tests/uiflow2/run_device_matrix.py --device atom-echo \
    --flash-transport direct --out-dir /tmp/m5-atom-echo-run$i
done

# 3) 补充 I2S 端口 trace（可选；确认 I2S1 放音 / I2S0 PDM RX）
python3 tests/uiflow2/atom_echo_console_test/make_image.py \
  --base platform/.cache/firmware/atom-echo/uiflow2.bin --out /tmp/atomecho-trace-image.bin
M5SW_I2S_TRACE=1 M5SW_I2S_PCM_FILE=/tmp/atomecho-trace.pcm \
  M5SW_I2S_RX_PCM_FILE=/tmp/atomecho-rx.pcm \
  .work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa -M m5atomecho \
  -drive file=/tmp/atomecho-trace-image.bin,if=mtd,format=raw \
  -L .work/M5StopWatch-QEMU/build/qemu/pc-bios -display none \
  -serial file:/tmp/atomecho-trace.serial -serial null -serial null
```

QEMU 侧从 `.work/native-lock-source/qemu`（native-lock + 0110/0111/0112 +
0114，再按 0113→0116 顺序补齐）编译；补丁为
`patches/qemu-m5stack-peripherals/0117-atomecho-board.patch`
（SHA-256 `25bdf74c…`，已对 base `81594e5` 做 `git apply --check`）；
本记录使用的 `qemu-system-xtensa` SHA-256 为 `a337085d…`。

## 未覆盖

- NS4168 模拟增益/PA 输出/扬声器响度与失真、声学测量；
- 真实 SPM1423 采集、灵敏度/SNR、共用 G33 pad 的同时录放时序；
- IR NEC/RMT 发射；
- Grove Unit 数据面与端口电气兼容；
- USB/FTDI 串口路径、原厂 UIFlow2 启动菜单/网络、任意第三方固件；
- 真机电气/声学/机械与长期稳定性。

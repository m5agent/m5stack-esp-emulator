# AtomU（K117）虚拟主机接入（限定验证）

日期：`2026-11-02`。范围：把视觉库存中仅有外壳的 AtomU 接入为独立 classic
ESP32 原生 QEMU 主机（machine `m5atomu`）。本记录只声明虚拟设备结果：官方
UIFlow2 启动、板级识别、SK6812 RMT 输出、QMP 按键注入与 Grove I2C 控制器
扫描。物理电气/声学 `NOT RUN`。

## 结果

- 新增机器 `m5atomu`（补丁 `0116-atomu-board.patch`）：ESP32-PICO-D4、4 MB
  Flash、无 PSRAM、无屏；复用 classic Atom 板级逻辑（`m5atomclassic.c`）：
  SK6812 在 G27、USER 按键 G39、Grove 在 G26/G32；SPM1423 PDM 麦克风
  （G5/G19）由 SoC 级 ESP32 I2S0 PDM RX 模型提供，本板级不额外挂设备；
  IR（G12）未接线、未验收。
- 固件来源采用本任务新增的**固定 SHA 官方 GitHub release** 受控策略：
  `m5stack/uiflow-micropython` release `2.5.4` 的 AtomU 精确板镜像
  `uiflow-e437118-esp32-4mb-atomu-v2.5.4-20261030.bin`，
  4,186,112 B，SHA-256
  `affa252d21f223bbe21cf1767604d345df97b2cb8dd62bc76993588d9bd9eda7`。
  M5Burner 公开 API 没有 UIFlow2 AtomU 条目；该来源在 catalog 中显式
  `source: official-github-release` 并带 `sha256`，`fetch_firmware.py` 直接
  下载并按 SHA fail-closed 校验，缓存字节与声明不符时拒绝不出图像。
- 官方镜像为 4,186,112 B 稀疏 merged（分区 `factory 0x10000/0x361000`、
  `vfs 0x371000/0x8D000`），工具补 `0xFF` 到 4 MiB；console probe 只替换
  vfs 卷。probe 镜像 SHA-256
  `1232ba09e772c7f118a193fc2f19a7b4d86186bb54c917f1c99af02847985c44`。
- 设备矩阵 case `atomu`（console 模式）三次独立运行 `PASS`（3/3）。同一
  guest 内输出：

  ```
  ATOMU_BOOT_FLAG / ATOMU_MAIN_START / ATOMU_M5_BEGIN_OK
  ATOMU_BOARD 130
  ATOMU_DISPLAY none
  ATOMU_RGB 1 204060
  ATOMU_I2C_SCAN ['0x48']
  ATOMU_PROBE_READY
  ATOMU_BUTTON_STATE 0 0
  ATOMU_BUTTON_STATE 1 1 / ATOMU_RGB 1 40A020
  ATOMU_BUTTON_STATE 0 1 / ATOMU_RGB 1 204060
  ```

- 按键证据：QMP `key:a` 经板级 input handler 驱动真实 GPIO39 输入寄存器，
  guest 侧 UIFlow2 BtnA 读到按下/释放并重绘 RGB；不是 host 直接写 guest 值。
- RGB 证据：除串口标记外，同一 session 通过 QMP 读取 QOM
  `/machine/onboard_io`：`led-rgb = 2113632`（`0x204060`，与 guest 最后写入
  的颜色一致）、`led-frames = 5`（RMT 完整帧计数 ≥ 3，与三次运行一致）。
- Grove 证据：guest 用 `machine.I2C(0, scl=Pin(26), sda=Pin(32))` 扫描到
  `['0x48']`。`0x48` 是 QEMU classic ESP32 machine 自带的 `tmp105` 便利设备，
  不是 AtomU 板载器件；该标记只证明 guest I2C 控制器与 G26/G32 路由，
  不代表任何 Unit 协议。
- 稳定性的唯一差异是 ESP-IDF `i2c.master` 启动告警的虚拟时间戳：三次运行的
  `ATOMU_*` 标记、probe 镜像 SHA 与 QOM 值完全一致（serial log 哈希取 run 1，
  `c643097c…`）。

## 边界

- PDM 麦克风数据面未测：本板只在 machine 侧具备 SoC I2S0 PDM RX 能力，
  但没有注入 PCM、没有 guest 录音标记，因此**不声明 microphone 已模拟**。
- IR（G12）未接线、未测；Grove Unit 协议、USB/FTDI、UIFlow2 启动菜单/网络、
  第三方固件与浏览器/WASM 准入均未测。
- 无屏、无 PSRAM；显示/PSRAM 路径在本板不适用，不继承 Atom Lite/Atom Echo
  的任何结论。
- 本结果不转授同系列 Atom 主机或任意 Unit；真机、电气、声学、机械均 `NOT RUN`。
- 固件来源是 GitHub release asset，不是 M5Burner firmware ID；这是经审查的
  SHA 固定例外，目录与测试强制非 M5Burner 来源必须带 sha256。

## 复现

```bash
# 1) 固定 SHA 官方固件（fail-closed 校验，写入 platform/.cache/firmware/atomu/）
python3 platform/tools/fetch_firmware.py atomu --analyze --chip-id 0x0000

# 2) 三遍设备矩阵（console 模式，host-image 直接启动）
for i in 1 2 3; do
  python3 tests/uiflow2/run_device_matrix.py --device atomu \
    --flash-transport direct --out-dir /tmp/m5-atomu-run$i
done
```

QEMU 侧从 `.work/native-lock-source/qemu`（先应用 `0113-basic-v27-board.patch`
与 `0114-unit-gpio-batch1.patch`）编译，补丁为
`patches/qemu-m5stack-peripherals/0116-atomu-board.patch`；本记录使用的
`qemu-system-xtensa` SHA-256 为 `ecbe50bb…`，补丁 SHA-256 为 `82217b95…`。

## 未覆盖

- SPM1423 PDM 采集、麦克风灵敏度/SNR、模拟音频路径；
- IR NEC/RMT 发射；
- Grove Unit 数据面与端口电气兼容；
- USB/FTDI 串口路径、原厂 UIFlow2 启动菜单/网络、任意第三方固件；
- 真机电气/声学/机械与长期稳定性。

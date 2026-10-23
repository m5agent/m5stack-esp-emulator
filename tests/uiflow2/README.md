# UIFlow2 虚拟烧录与 UI 回归

最近核对：`2026-10-24`

设备参数在 `device_matrix.json` 中集中维护。统一流程：

1. 生成带测试 `boot.py`/`main.py` 的 merged flash；
2. ESP32-S3/C6/P4 通过 `esp-emu`、Core2 通过 QEMU ESP32 ROM 下载模式执行真实 `esptool write-flash`；
3. 将写后的虚拟 flash 与期望镜像逐字节校验；
4. QEMU 从同一份虚拟 flash 启动；
5. 校验目标分辨率首帧、非空画面、输入后像素变化；配置了
   `post_frame_color` 的输入设备还必须命中 UI 写入的固定像素标记；
6. 输出规范 `before.png`、`after.png`、串口和命令日志。

全量回归：

```bash
python3 tests/uiflow2/run_device_matrix.py \
  --out-dir /tmp/m5-uiflow2-device-matrix
```

单设备：

```bash
python3 tests/uiflow2/run_device_matrix.py --device nesso-n1
python3 tests/uiflow2/run_device_matrix.py --device core2
python3 tests/uiflow2/run_device_matrix.py --device tab5
```

输入验收不能只看截图哈希。Core2 曾出现触摸实际未计数、但半帧重绘仍改变
哈希而误判 PASS；现在触摸和按键测试会在识别到输入后写固定颜色标记，
矩阵直接读取该像素。墨水屏只做局部状态刷新，避免把 Spectra 6 长时间卡在
未完成的整帧写入。

Core2 stock internal-controller BLE：

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/core2_native_vhci/run_test.py \
  --attempts 5 \
  --out-dir /tmp/core2-native-vhci
```

该 runner 不重建 HCI-UART 固件，而是在 QEMU GDB 中拦截固件自己的
`esp_vhci_host_*` H2C/C2H，接 Bumble controller/peer。当前 milestone 为
外部 NUS GATT 5/5 PASS；bit-exact Espressif BT baseband/controller 仍
`NOT RUN`。

同一 guest 的 board/WiFi/公网与 native-VHCI BLE：

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/unified_core2/run_test.py \
  --image /tmp/core2-native-vhci-unified.bin \
  --out-dir /tmp/core2-native-vhci-unified \
  --ble-transport native-vhci \
  --attempts 3 --require-all-attempts
```

当前为 3/3 PASS；镜像必须是匹配的 stock internal-controller UIFlow2 构建。
同一路径已进入 Device Service：
`runtime=qemu-unified`、`profile=core2-native-vhci`，真实 `/api/v1` lease
同时返回 board/frame/QOM/audio/WiFi/公网/BLE，并保留 pcap、bridge 和 peer
evidence；当前仍依赖服务托管的 GDB bridge。

Device Service 的 GDB 诊断桥 repeated lease 目前为 `1/2`，失败在 C2H
callback 注入，因此单 lease PASS 不等于稳定后端。QEMU 内部替代路线当前
的边界是：

| 阶段 | 状态 | 验证入口 |
| --- | --- | --- |
| `HCI-1` host transport | `PASS` | `core2_native_hci/test_transport.py` |
| `HCI-2` guest H2C | `PARTIAL` | `core2_native_hci/test_guest_h2c.py`，只到首个 Reset |
| `HCI-3` guest C2H | `OPEN` | 尚无已提交实现 |
| `HCI-4` repeated lease | `OPEN` | 仍需无 GDB 的 Device Service `5/5` |

```bash
python3 tests/uiflow2/core2_native_hci/test_transport.py
```

`HCI-1` 测试只验证 H4 chardev framing、bounded queue、overflow、peer
lifecycle 和 shutdown，不验证 guest VHCI/BLE。设计和阶段门禁见
`docs/core2-native-hci-backend.md`。

guest H2C capture 切片：

```bash
python3 tests/uiflow2/core2_native_hci/test_guest_h2c.py \
  --image /path/to/stock/core2-uiflow2.bin
```

它不启动 GDB，从真实 VHCI shared memory 捕获 stock HCI Reset
`01030c00` 并送到外部 peer。C2H 尚未回送 guest，因此不是 BLE PASS。
本地曾尝试直接调用 guest `vhci_send`，函数虽然返回，guest 仍等待 ack 并
`ETIMEDOUT`；该入口不是直接 H4 ingest API，实验未提交。`HCI-3` 必须从
真实 controller-to-host 通知/队列语义继续。

Core2 peripheral 和 device matrix 现在都显式使用
`tcg,thread=single` + `icount shift=auto,align=off,sleep=off`。matrices
不再配置自动重试；若 case 声明 `retries`，runner 默认拒绝运行，只有显式
`--allow-retries` 才执行诊断重试。2026-10-24 00:11 的完整矩阵为
`67/67`、`274/274`，全部 `attempts=1`。
当前统一运行时入口是 `runtime=qemu-unified`；`qemu-wifi` 和 `qemu-ble`
只用于兼容 profile 或单选无线诊断，不应作为新调用的默认路径。

当时跨设备问题、修复和证据见
[`docs/uiflow2-cross-device-regression-audit.md`](../../docs/uiflow2-cross-device-regression-audit.md)。
当前能力不要从该历史页推断，统一看
[`docs/project-status.md`](../../docs/project-status.md)。

## I2S 音频捕获

`run_profile_ui_test.py` 支持 `longpress`、`drag` 和多帧/逐输入截图。
带 Speaker 的用例可设置：

```bash
M5SW_I2S_DMA_IRQ=1 \
M5SW_I2S_PCM_FILE=/tmp/speaker.pcm \
python3 tests/uiflow2/run_profile_ui_test.py ...
```

采集从首个非静音 DMA 描述符开始，之后连续写入，包括中间静音；不再按哈希
跳过重复块，也不会混入整段 snapshot。CoreS3 的 Speaker 输出是 48 kHz、
16-bit、mono，导出 WAV 时必须使用该格式。

`cores3_audio_fidelity` 用确定性的 1 kHz 方波验证采集链；已知输入应在
200 ms 内产生约 400 次符号翻转。仅检查“非零样本和峰峰值”无法发现
重复块、采样率错误或波形损坏。

```bash
python3 tests/uiflow2/check_pcm_square.py /tmp/live.pcm \
  --sample-rate 48000 --frequency 1000 --duration-ms 200
```

外设 API 探测：

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/run_peripheral_matrix.py \
  --out-dir /tmp/m5-uiflow2-peripheral-matrix
```

设备中心可以按设备直接调度同一份运行时用例组：

```bash
python3 tests/uiflow2/run_peripheral_matrix.py \
  --device stackchan \
  --out-dir /tmp/m5-stackchan-peripherals
python3 tests/uiflow2/run_peripheral_matrix.py \
  --device stackchan --list-json
```

纯外部后端设备（例如 Tab5）在外设运行组中返回空矩阵列表，其 external
probe 由 `/api/peripherals/<device>.runtime_cases` 单独调度。

覆盖 StickS3 的 IMU、A/B/P 按键和电源，以及 CoreS3 的 IMU、触摸、PWR、
电源、RTC 和摄像头初始化/取帧。结果和边界见
[`docs/uiflow2-peripheral-test-matrix.md`](../../docs/uiflow2-peripheral-test-matrix.md)。

NanoC6 无显示屏，单独使用板级外设 runner：

```bash
python3 tests/uiflow2/run_nanoc6_peripherals.py
```

它验证 GPIO19 RGBPWR、GPIO20 WS2812 GRB 波形、GPIO9 按键按下/释放和
GPIO7 蓝色 LED。C6 后端通过 `M5SW_C6_BOARD=nanoc6` 与 Nesso N1 板级外设
隔离，不再把 Nesso 的屏幕、SX1262 或强制 GPIO 状态挂到 NanoC6。

Nesso N1 单 guest 联合探针：

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/unified_nesso/run_test.py \
  --image /tmp/m5-nesso-unified.bin \
  --out-dir /tmp/m5-nesso-unified \
  --require-public-network
```

它同时运行 135x240 显示/触摸、PI4IOE、BQ27220/AW32001、BMI270、
SX1262 回环、RMT IR、蜂鸣器 PCM、QEMU ESP32-C6 WiFi DHCP/HTTP 和
UART1 HCI BLE。加 `--require-public-network` 时还要求同 guest 的
`example.com` IPv4 DNS/HTTP；不加则保留完全本地的 CI 门禁。
stock `hardware.RGB()` 不在该探针的 PASS 范围内。

StickS3 对应命令：

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/unified_sticks3/run_test.py \
  --image /tmp/m5-sticks3-unified.bin \
  --out-dir /tmp/m5-sticks3-unified \
  --require-public-network
```

StackChan 的 IMU/AW9523/INA226/IR 联合探针：

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/run_peripheral_matrix.py \
  --case stackchan-peripherals
```

该用例会同时验证 BMI270 加速度/陀螺仪、BM8563 RTC 走时校验、
AW9523 输入输出、INA226 电压/电流/功率，以及 NEC IR 的 TX 抓取和
RX 注入。固件启动后注入动态角速度，避免触发 M5Unified 的启动零偏校准。
外部 RTC 通过 `machine.I2C` 直接读写器件 BCD 寄存器；`machine.RTC`
只修改 ESP32 系统时间，不计为 RX8130/PCF8563 验证。

矩阵 runner 不接受“QEMU 没崩就算 PASS”。每个用例必须至少配置一种运行时
证据源（串口成功标记、QOM 状态、PCM、RMT 波形、磁盘 sector 或固定 UI
像素）；缺少证据源的用例会直接拒绝执行。guest 串口中的
`Guru Meditation Error`、Traceback、`status=error` 或 `FAIL` 也会把用例
判为失败。`summary.json` 中的每个 check 状态在运行时生成，并记录对应的
`evidence`，不再使用静态 PASS 元数据。
每个 matrix/external case 还在 `runtime-coverage.json` 的 `case_models`
中声明实际覆盖的芯片模型。设备上的每个 `simulated` 组件必须有本机用例，
不能从其他设备的同型号芯片测试中继承完成状态。
需要验证状态跃迁的用例可在 `qom_steps` 中声明多次宿主注入；
`qom_sequence_settle` 控制最后一次状态后的等待时间，固件实例保持运行，
不通过重启模拟“动态”状态。

Tab5 需要先构建仿真固件和 16 MiB merged image：

```bash
export UIFLOW_MICROPYTHON_DIR=/path/to/uiflow-micropython
python3 tests/uiflow2/build_tab5_emulator.py \
  --uiflow-repo "$UIFLOW_MICROPYTHON_DIR" \
  --clean
```

输出位于 `.work/uiflow2-tab5/`，包括 `micropython.elf` 和
`tab5-emulator-merged.bin`。Tab5 构建使用原生 M5GFX/UIFlow2 绘制路径，
仿真构建暂不启用 LVGL Python 绑定。

Tab5 的 SIT3088 RS-485 使用 `machine.UART` 半双工模式和
`esp-emu --uart1-tcp` 主机字节对端验证：

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/run_tab5_ui_test.py \
  --base .work/uiflow2-tab5/tab5-emulator-merged.bin \
  --elf .work/uiflow2-tab5/micropython.elf \
  --files-dir tests/uiflow2/tab5_rs485 \
  --timeout 60 --probe-only --uart1-peer \
  --ready-marker 'TAB5_RS485_DONE PASS'
```

该路径从 UART1 G20 发送、G21 接收，G34 作为 RS-485 方向控制；证据见
`tests/uiflow2/tab5_rs485/evidence-2026-10-22.json`。

Tab5 的充电/放电状态通过 PI4IOE2 `0x0F` 主动低电平输入验证，并由场景清单
固定下来：

```bash
python3 tests/uiflow2/run_tab5_peripheral_scenarios.py
```

`0x0F=0x00` 要求 `Power.isCharging()` 为 `True`，`0x0F=0x40` 要求为
`False`。当前实现支持每次启动时选择一个状态；IP2326 模拟电流、充满终止和
运行中热切换仍依赖后续 `esp-emu` 动态 I2C API。

Tab5 framebuffer 默认优先使用原生 `riscv64-elf-gdb`：

```bash
brew install riscv64-elf-gdb
python3 tests/uiflow2/run_tab5_rs485.py
```

原生 GDB 会直接抓取真实 1280×720 framebuffer 并注入触摸；Docker 仅在原生
GDB 不存在时作为 fallback。

只生成可启动虚拟 flash：

```bash
python3 tests/uiflow2/flash_device.py \
  --device sticks3 \
  --firmware platform/.cache/firmware/sticks3/uiflow2.bin \
  --out-dir /tmp/m5-flash-sticks3
```

传输说明：

- `esp-emu-esptool`：ESP32-S3/C6/P4，真实 esptool `write-flash`，写入后逐字节校验；
- `qemu-esptool`：Core2，通过 QEMU ESP32 ROM UART 下载模式和 `esptool --no-stub` 写入，再逐字节校验；
- Tab5：`esp-emu` P4 下载模式的地址空间限制在 8 MiB，因此仿真专用分区表把
  应用、sys、vfs 和 storage 全部放在 8 MiB 以下；生产分区布局不变。写后的
  16 MiB 虚拟 Flash 与期望镜像逐字节一致后，再从同一份 Flash 启动。
- CardputerZero：Linux ARM64，不是 ESP32/UIFlow2 固件目标，保持独立后端。

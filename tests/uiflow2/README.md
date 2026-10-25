# UIFlow2 虚拟烧录与 UI 回归

最近核对：`2026-10-25`

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
外部 NUS GATT 5/5 PASS；该 GDB 路线只用于 legacy/diagnostic 对照。
bit-exact Espressif BT baseband/controller 仍 `NOT RUN`。

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
evidence；该 profile 仍依赖服务托管的 GDB bridge，只用于诊断/兼容。

Device Service 的 GDB 诊断桥 repeated lease 目前为 `1/2`，失败在 C2H
callback 注入，因此单 lease PASS 不等于稳定后端。规范主路径改为
`core2-native-hci`：

| 阶段 | 状态 | 验证入口 |
| --- | --- | --- |
| `HCI-1` host transport | `PASS` | `core2_native_hci/test_transport.py` |
| `HCI-2` guest H2C | `PASS` | `core2_native_hci/test_guest_h2c.py` 捕获首个 Reset；完整命令流由 `HCI-3b` 验证 |
| `HCI-3a` guest C2H callback | `DIAGNOSTIC PASS` | `core2_native_hci/test_guest_h2c.py --enable-c2h`，targeted `5/5`；不是产品 C2H 后端 |
| `HCI-3b` HLI event | `PASS` | `core2_native_hci/test_hli_event.py`；池化 Reset Complete 经 event 13 交付，`01030c00 → 01011000` 连续 `5/5` |
| `HCI-3b` complete HCI/GATT | `PASS` | `core2_native_hci/run_full.py --hli-c2h` 使用 15-byte probe / 17-byte ATT PDU，完成 NUS discovery/subscription/write/notify 和 Bumble ACK，连续 `5/5` |
| `HCI-4` repeated lease | `PASS` | `core2_native_hci/run_service_5x.py`；五个独立 Device Service lease 同时通过 frame/QOM/WiFi/公网/NUS GATT/pcap/evidence，`gdb_bridge=false` |
| `CORE2-02` extended run | `PASS` | caller-saved Xtensa sregs 恢复 + halted/idle-only HLI 注入后，两批 `5×10s` 为 `10/10`，3 个 `60s` 为 `3/3`，2 个 `120s` 为 `2/2`；每轮 `hli-errors=0` |
| `CORE2-02` active-BLE 600s hold | `PASS` | 2 个独立 lease `2/2`；`ble_linger_seconds=660`，600 秒结束时 peer 仍连接，HLI `45/45`、队列和错误为 0 |
| `CORE2-02` bounded 7200s hold | `PASS` | artifact-bound 单 lease 使用 `tcg,thread=single,tb-size=128`，frame/QOM、WiFi/公网、active NUS GATT、pcap、HLI 和 cleanup 全部通过；240 个 host-resource 采样无持续增长 |
| `CORE2-02` same-guest reconnect | `PASS` | stock 固件在 3 个独立 lease 中分别完成 20、30、60、120 轮 scan/connect/NUS GATT/disconnect；120 轮每 lease HLI `3377/3377`、events `2297`、ACLs `1080`，HLI/TX queue、dropped 和 panic 为 0，连接池回到 `3/9/3`。根因是 Bumble 对无响应 `0x0c35` 返回非法 Command Status |
| `CORE2-02` 121-cycle reconnect | `3/3 PASS` | 修复 readiness budget 和 reconnect-only accelerator-sampling 两个 harness 缺陷后，3 个 artifact-bound lease 均为 `121/121`；同 firmware/ELF/QEMU/工具哈希，每 lease HLI `3405/3405`、events 2316、ACLs 1089，队列/错误/dropped/peer-close/panic 为 0 |
| `CORE2-02` no-stagger concurrency | `双实例 8/8 + 三实例 6/6 + 四实例 8/8 PASS` | 双实例两批 `4×120s`、三实例两批 `3×120s`；`0008` 预分配真实 guest event/ACL 对象，所有 lease 36 events/9 ACLs 走 fast path、HLI `45/45`、errors/reset/panic 为 0。三实例首轮暴露固定 `40s` peer scan 预算过短，后续按 session readiness 有界扩展到 `≤120s`；PSRAM sweep 下限按 `hold/5` 校准。四实例首批先 `1/4`，`0009` 扩到 8 event/4 ACL 后两批各 `4/4 PASS`；五实例及物理 controller 仍开放 |
| `CORE2-02` five-instance concurrency | `错峰 10/10 PASS；零错峰 OPEN` | 两批 30 秒错峰 `5×120s` 均 `5/5`，真实最大并发 5；每 lease HLI `45/45`、36 events/9 ACLs、WiFi/公网/GATT/PSRAM/frame/QOM/pcap/evidence 和 cleanup 全 PASS。相同实现下零错峰五实例一批 `5/5 PASS`、独立确认批 `3/5 FAIL`，失败复现 `0x402630cc` NimBLE ACK panic 或 external GATT exchange failure；更多实例及物理 controller 仍开放 |
| Core2 guest PSRAM sustained | `3/3 PASS` | QOM PSRAM device 为 `8 MiB`，普通 ESP32 DRAM1 heap 保持 `4 MiB` 直接映射窗口。3 个 artifact-bound lease 各 120 秒，从普通 heap 分配 `1 MiB`，分别完成 35/35/35 次全缓冲校验（累计 `105 MiB`）；上 4 MiB 另由 `esp_himem` MMU bank switch `3/3` 覆盖。每轮另做 10 次受控 HTTP、3–4 次公网 recheck，active BLE/frame/QOM/pcap/cleanup PASS。物理 PSRAM/cache timing 仍 `NOT RUN` |
| Core2 8 MiB device-group compatibility | `6/6 PASS` | 当前重建 QEMU `b5b2d878…` 下 6 个 UIFlow2 case、24 个检查全部一次通过且无 retry；覆盖触摸、RTC、电源键、音频、麦克风、INA3221、MPU6886 和 AXP192。INA3221 固定通道值改用 boot-time QOM 注入，避免默认 8 秒 post-boot 窗口的测试竞态 |
| Core2 guest PSRAM 600s | `1/1 PASS` | 单 lease 600 秒完成 179 次 `1 MiB` 全缓冲校验、51 次受控 HTTP、18 次公网 recheck；active BLE/HLI/bounded TCG/frame/QOM/912-packet pcap/cleanup PASS。20 个 RSS 采样增加 `352 KiB`，只覆盖本次虚拟 workload |

`HCI-4` 重跑需要已准备 unified Core2 镜像、匹配 ELF 和相同 QEMU build：

```bash
python3 tests/uiflow2/core2_native_hci/run_service_5x.py \
  --image /tmp/core2-native-hci-unified/uiflow2-ui-test.bin \
  --elf .work/uiflow2-core2-symbols/micropython.elf \
  --qemu .work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa \
  --attempts 5 \
  --hold-seconds 10 \
  --out-dir /tmp/m5-core2-native-hci-service-5x
```

当前证据为
`core2_native_hci/evidence-2026-10-24-hci4-service-5x.json`。它是
`virtual-device validation`，不是 RF、bit-exact controller 或真机结果。
新 PSRAM 持续压力镜像使用同一 runner 并追加
`--require-psram --hold-seconds 120 --attempts 3`；当前证据为
`core2_native_hci/evidence-2026-10-25-core2-psram-sustained-8m-3x120.json`。
更长窗口证据为
`core2_native_hci/evidence-2026-10-25-core2-psram-sustained-1x600.json`。
历史 extended-run 失败证据仍保留在
`core2_native_hci/evidence-2026-10-24-extended-run-fail.json`。当前修复后
证据为
`core2_native_hci/evidence-2026-10-24-hci4-halted-gate-5x.json`：两批
独立 5 次、每轮 hold 10 秒，合计 `10/10`，并且每轮
`hli-posts=hli-consumed=47`、`hli-errors=0`、HLI/meta queue 深度为 0。
后续 3 个独立 60 秒 hold 为 `3/3`，证据：
`core2_native_hci/evidence-2026-10-24-hci4-hold60-3x.json`；BLE peer
正常关闭时允许 `last-error=3`，但必须同时满足 `peer-closed>0`，HLI errors
仍必须为 0。
随后 2 个独立 120 秒 hold 为 `2/2`，证据：
`core2_native_hci/evidence-2026-10-24-hci4-hold120-2x.json`。GATT peer
关闭后固件继续发 HCI command 会填满 32-packet TX queue；只有同时满足
`peer-closed>0`、`tx-queue-depth>0` 时才允许 `last-error=2` 尾态。
active-BLE 模式再把 `network.ble_linger_seconds` 设为 hold+60 秒，2 个
独立 120 秒运行同样 `2/2`；随后 2 个独立 600 秒运行也 `2/2`。hold
完成时 peer 未断开，HLI `45/45`、`tx-queue-depth=0`、`last-error=0`。
120 秒证据：
`core2_native_hci/evidence-2026-10-24-hci4-active-ble-hold120-2x.json`。
600 秒证据：
`core2_native_hci/evidence-2026-10-24-hci4-active-ble-hold600-2x.json`。
同一 guest 的 disconnect/reconnect 已从失败修正为 PASS。当前矩阵是
3 个独立 lease 分别完成 20、30、60、120 轮连接生命周期；120 轮证据为
`core2_native_hci/evidence-2026-10-24-hci4-reconnect120-3x.json`，每 lease
HLI `3377/3377`、events `2297`、ACLs `1080`，连接池回到 `3/9/3`。历史
`NimBLE: HCI process ack returned 12` 由 Bumble 对无响应
`HCI_Host_Number_of_Completed_Packets (0x0c35)` 非法返回 Command Status
引起；下一命令消费 stale ACK 后触发 reset。20/30 轮和更早的 2/5/10 轮
证据保留在 `core2_native_hci/`，失败证据不会被后续 PASS 覆盖。
这关闭了本轮 two-minute extended-run 失败门禁；单独的单 lease artifact-bound
`tb-size=128` 两小时运行也已 PASS，RSS 和 phys footprint 未增长。它仍不是
物理 cache/PSRAM、RF 或 bit-exact controller PASS。Device
Service/Bumble/runner 共享 `1–121` 范围，并有 `122` 轮拒绝测试。
较早的十轮运行曾被 Device Service 的旧 30 秒等待硬上限误杀，失败证据保留在
`evidence-2026-10-24-hci4-reconnect10-timeout-fail.json`。
首次 121 轮运行又在 29 轮后暴露固定 180 秒预算不足；guest 无 panic，
runner/Device Service 已改用同一 workload-aware 预算，失败证据保留在
`evidence-2026-10-25-hci4-reconnect121-readiness-timeout-1x.json`。
随后 reconnect-only 路径又暴露 accelerator 只在 hold loop 内采样的假失败；
修复后 3 个独立 artifact-bound lease 均完成 `121/121`，聚合证据为
`core2_native_hci/evidence-2026-10-25-hci4-reconnect121-3x.json`，并绑定
相同 firmware/ELF/QEMU/工具哈希。物理 cache/PSRAM、RF、吞吐/teardown 和
bit-exact controller 边界仍未关闭。

```bash
python3 tests/uiflow2/core2_native_hci/test_transport.py
```

`HCI-1` 测试只验证 H4 chardev framing、bounded queue、overflow、peer
lifecycle 和 shutdown，不验证 guest VHCI/BLE。设计和阶段门禁见
`docs/core2-native-hci-backend.md`。

guest H2C capture 切片：

```bash
python3 tests/uiflow2/core2_native_hci/test_guest_h2c.py \
  --image /path/to/stock/core2-uiflow2.bin --enable-c2h
```

它不启动 GDB，从真实 VHCI shared memory 捕获 stock HCI Reset
`01030c00`，向 guest 交付 Reset Complete，再要求 guest 发出
`01011000`。callback status、错误计数和 send-available 均由 QOM 检查。
这证明单包 C2H 路径，不证明完整 BLE 初始化或 GATT。

Core2 peripheral 和 device matrix 现在都显式使用
`tcg,thread=single,tb-size=128` +
`icount shift=auto,align=off,sleep=off`。matrices
不再配置自动重试；若 case 声明 `retries`，runner 默认拒绝运行，只有显式
`--allow-retries` 才执行诊断重试。2026-10-24 06:47 的完整矩阵为
`67/67`、`274/274`，全部 `attempts=1`；该轮包含双 guest WiFi patch
`0028`，并把 Cardputer-ADV 键盘用例的启动/输入端等待调整为 10/2 秒。
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

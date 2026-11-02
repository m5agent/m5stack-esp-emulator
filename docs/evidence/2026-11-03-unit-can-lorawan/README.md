# Unit CAN / LoRaWAN lane 解锁与三款虚拟设备证据（2026-11-03）

范围：`can`（U085）、`mini-can`（U179）与 `lorawan-us915`（U184-US915）三款 Unit 的
CAN/TWAI 与 UART AT 字节层虚拟设备数据面。三款各一个 cores3 可见 Device Service
session，运行参考固件自带的原始冻结驱动/官方 C 模块；每例先取 evidence ZIP，再
`purge=0` 停止并回读保留 history。

本批解除了 batch-7 `can` BLOCKED、batch-8 `mini-can`/`lorawan-us915` BLOCKED：

- **batch-7 can / batch-8 mini-can**：此前 session 被 `QEMU Unit model/state contract is
  incomplete` 拒绝，根因不是 QEMU 缺 CAN 控制器，而是 **Unit runtime 契约/挂载路径**：
  catalog `rx-frames/tx-frames/can-state` 等字段与 QEMU 已有 batch-7 CAN 模型属性
  （`frames-observed`/`injected-frames`/`last-frame-hex`/`inject-hex`）不一致，且
  profile 仍是 `planned`、`hosts` 为空。本批把契约对齐到真实 QOM 属性、profile 升
  `implemented` + `hosts=["cores3"]`，session 即可在 real esp32s3 TWAI 控制器与
  cores3 `m5-canbus` CanBusClient lane 上运行。
- **batch-8 lorawan-us915**：QEMU 侧 `lorawan-us915` 的 UART TX 捕获与 0150
  `gpio_uart_rx_device_for_white()`/idle responder 路径本已存在；BLOCKED 的真实根因是
  **guest 侧 UART 初始化顺序**——冻结 ASR650x wrapper 先 `machine.UART(1, tx, rx)`
  （无 baud）再 `init()`，QEMU TX matrix 捕获只有在该 UART 先被 baud 配置后才观测到
  写入。补上与 batch-7 `lorawan-cn470` 证据相同的**已文档化 guest-side UART
  bootstrap** 后，官方冻结 `LoRaWANUnit` 的 AT 字节即进入既有 Unit UART lane，
  fixture responder 也经既有 fallback 注入 responses。

因此 **本批不需要新的 QEMU 源码补丁**（patch 0157 不使用）：QEMU 源码保持 canonical
`75f1d24` + canonical 35 层链（through `0154`）；变更集中在 Unit runtime 契约
（`platform/units/catalog.json`、`runtime-profiles.json`）与证据 probe/runner。

## 单一 QEMU 构建

| 项 | 值 |
| --- | --- |
| QEMU 源码状态 | canonical `75f1d24` + canonical 链 35 层（`0120`…`0154`）；本批无新增 QEMU 补丁 |
| QEMU 树 | `.work/native-lock-source/qemu`（`rm -rf build` 后重新 `configure`；注意 build 目录不可从其他 worktree 复制——绝对路径会把源码指向别处） |
| 运行时二进制 SHA-256（签名部署副本） | `cead867a…`（每条 report 的 `runtime_binary_sha256` 一致；与 Evidence summary 的 `qemu_builds` 一致） |
| Device Service | 独立 `127.0.0.1:8831`、独立 state/token、`M5_SERVICE_FLASH_MODE=host-image`；用户 `8787` 与并行 8799/8801 服务均未触碰 |

## Unit runtime 契约变更（CAN lane）

- `can`/`mini-can` profile：`planned → implemented`、`hosts=["cores3"]`、
  `inputs={"inject-hex"}`、`state={"frames-observed","injected-frames","last-frame-hex"}`；
  catalog `runtime.status=implemented`、`model_status=partial`、属性名与 QOM 对齐；
  `can.interface.bus` 由 `uart` 修正为 `can`。
- `mini-can`/`can` 的旧 `rx-frames/tx-frames/frames-sent/frames-received/can-state`
  契约字段被替换为真实 QOM 属性（旧契约无对应 QOM → 触发 `contract is incomplete`）。
- `lorawan-us915`：profile 升 `implemented` + `hosts=["cores3"]`（QOM 属性
  `responses-hex/tx-hex/frames-sent/frames-injected` 原本已对齐），catalog
  `runtime.status=implemented`、`model_status=partial`。
- host 端口：三款官方连接器均为 PORT.C；当前 runtime 只准入 cores3 PORT.A（`port-a`，
  GPIO2/1 harness），与既有 batch-6/7/8/10 证据一致，逐 report 记录
  `official_port=PORT.C` 与 `runtime_port_substitution`。官方连接器物理接线未验证。

## 结果

| Unit | 驱动路径 | runtime 端口 | 结果 |
| --- | --- | --- | --- |
| `can` | 官方 `m5can` C 模块（esp32s3 TWAI） | cores3 port-a（官方 PORT.C） | **PASS** |
| `mini-can` | 官方 `m5can` C 模块（esp32s3 TWAI，TJA1051T/3） | cores3 port-a（官方 PORT.C） | **PASS** |
| `lorawan-us915` | 冻结 `unit/lorawan.py` → ASR650x 驱动，UART1 | cores3 port-a（官方 PORT.C） | **PASS**（仅字节层） |

### CAN / Mini CAN

- guest 侧由真实 TWAI 控制器发出一帧标准帧 `123#0102030405060708`：
  QOM `frames-observed = 1`、`last-frame-hex = 123#0102030405060708`（guest TX 帧被
  cores3 `m5-canbus` 上的 CanBusClient 观测）。
- host 通过 Unit QOM `inject-hex = 456#deadbeef` 注入一帧：QOM
  `injected-frames = 1`，guest TWAI 收到并打印 `CAN_RECV 456#deadbeef`，guest
  `state()` 全程 `RUNNING`（6）。
- **冻结 `unit/can.py` wrapper 的本固件版本不可用**：`CANUnit((WHITE,YELLOW),0)` 在
  wrapper 内抛 `TypeError: 'int' object isn't subscriptable`；mode-first 变体则以
  `ESP_ERR_INVALID_ARG` 拒绝 timing 参数。为如实取证，probe 直接使用该 wrapper
  所继承的**同一个官方 `m5can` C 模块**（`CAN(0, CAN.NORMAL, tx, rx)`，默认
  125 kbit/s timing）驱动真实 TWAI；该限制在 report 的 `wrapper_caveat` 与 serial
  `CAN_WRAPPER_CAVEAT` 中显式记录，不伪装成 frozen wrapper 成功。
- 边界：CAN 电气/收发器/隔离/终端/位定时/过滤/仲裁 **NOT modeled / NOT RUN**；
  物理 CAN 总线行为 NOT RUN；CAN 帧不经过 UART，PORT.C 的 UART host-port 语义不适用。

### LoRaWAN-US915（仅 UART 字节层）

- 已文档化 guest-side UART bootstrap（同 batch-7 `lorawan-cn470`）：先
  `machine.UART(1, tx=YELLOW, rx=WHITE, baudrate=115200)`，再构造冻结
  `LoRaWANUnit(1, (WHITE, YELLOW))`。
- guest 冻结 ASR650x 驱动写出的 AT 字节（QOM `tx-hex`）：
  `AT+CWORKMODE=2`、`AT+CWORKMODE=1`、`AT+DTRX=5,48454C4C46`（HELLO），
  `frames-sent = 3`；fixture responder `responses-hex` 注入 3 次
  （`frames-injected = 3`）并回读一致。
- 边界：冻结 `unit/lorawan.py` 仍继承 `driver.asr650x.LoRaWAN_470`，产品为
  STM32WLE5/RAK3172（driver/product mismatch）；不声称 AT 协议解码、Join 或
  US915 OTAA/ABP、duty-cycle、FCC、RF/天线 —— 全部 **NOT RUN**；只断言 UART 字节层。

## 复现

```bash
# 1) QEMU：canonical 35 层链（无新增补丁；务必删 build 重配，勿复制其他 worktree 的 build）
rm -rf .work/native-lock-source/qemu/build
cd .work/native-lock-source/qemu
PKG_CONFIG_PATH=/Users/m5agent/Documents/ChatGPT/esp-emulator/.work/unit-runtime-build/deps/lib/pkgconfig:... \
  ./configure --target-list=xtensa-softmmu --python=/.work/unit-runtime-build/venv/bin/python \
  --enable-gcrypt --enable-slirp --disable-docs --disable-werror ...
ninja -C build -j10 qemu-system-xtensa
cp build/qemu-system-xtensa ../../M5StopWatch-QEMU/build/qemu/build/
xattr -c ../../M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa
codesign --force --sign - ../../M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa

# 2) 独立 Device Service（8831，独立 state/token，host-image；不碰 8787/8799/8801）
M5_SERVICE_FLASH_MODE=host-image \
M5_QEMU_XTENSA="$PWD/.work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa" \
M5_QEMU_XTENSA_ROM_DIR="$PWD/.work/M5StopWatch-QEMU/build/qemu/pc-bios" \
  PYTHONPATH=platform/tools python3.12 platform/tools/serve.py 8831 \
  --bind 127.0.0.1 --state-dir .work/unit-can-lorawan-service-8831 \
  --api-token "$(cat .work/unit-can-lorawan-service-8831.token)"

# 3) 每款一个可见 session（can / mini-can / lorawan-us915）
export M5_SERVICE_API_TOKEN="$(cat .work/unit-can-lorawan-service-8831.token)"
PYTHONPATH=platform/tools python3.12 tests/units/run_can_lorawan_cases.py \
  --api-url http://127.0.0.1:8831 --case can --out-dir .work/unit-can-lorawan-evidence
```

原始 ZIP/帧/串口日志/probe 文件保留在本地忽略的 `.work`；仓库只提交摘要、哈希与
复现命令。`report-<unit>.json` 记录 firmware/runtime SHA、QOM 样本、serial markers、
checks、frame 与 stop history；`summary.json` 汇总单一构建与三款结果。

## 未覆盖与边界

- CAN 电气/差分电平/隔离/终端/总线仲裁/错误帧/真实总线负载 **NOT RUN**；
- 官方 PORT.C 物理接线未验证（使用 cores3 PORT.A harness，逐 report 记录替换）；
- 冻结 `unit/can.py` wrapper 的 release 版本兼容性问题未在固件侧修复（只记录并用
  同一官方 C 模块取证）；
- LoRaWAN-US915：AT 协议解码、Join/OTAA/ABP、US915 duty-cycle、FCC、RF/天线、
  产品/驱动错配全部 **NOT RUN**；
- 本结果只覆盖 cores3 + 记录固件 SHA + 记录 QEMU 二进制 SHA，不转授其他主机或固件。

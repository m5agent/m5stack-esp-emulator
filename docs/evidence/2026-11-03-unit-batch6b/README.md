# Unit 第六批剩余 6 款虚拟设备证据

日期：`2026-11-03`。范围：把 batch6 剩余 6 款 Unit（`unit-id`、`thermal2`、
`qrcode`、`uwb`、`dmx`、`finger`）的数据面通过**独立 Device Service** 的可见
`/api/v1` 会话记录为**虚拟设备**证据。物理 RF/热成像/光学/生物识别/电气语义
全部 `NOT RUN`。

本页是验证证据，不定义当前能力；当前能力以
[项目当前状态](../../project-status.md) 为准，工作队列以
[项目 Backlog](../../project-backlog.md) 为准。所有结果只覆盖表内记录的
主机、固件 SHA、QEMU 二进制 SHA 和检查项，不转授未列组合。

## 关键点：单一 QEMU 构建 + 0145 证据修复

6 款都在 `0142`（batch6 B）层；本批只需**一个** QEMU 构建，`0145` 是本轮
证据发现的模型修复。

| 项 | 值 |
| --- | --- |
| QEMU 源码状态 | canonical `75f1d24` + canonical 链 25 层（0120–0144，含 **0142** batch6 B）+ **0145（本轮证据修复）** |
| QEMU 树 | `.work/native-lock-source/qemu`（`rm -rf build` 后重新 `configure`，未复用旧 build.ninja） |
| 运行时二进制 SHA-256（签名部署副本） | `71ff4c9b…`（每条 report 的 `runtime_binary_sha256` 一致） |
| 参考固件 | cores3 `platform/.cache/firmware/cores3/uiflow2.bin`，SHA-256 `1324f12d…` |
| Device Service | 独立 `127.0.0.1:8799`、独立 state/token、`M5_SERVICE_FLASH_MODE=host-image`；用户 `8787` 未触碰 |

## 证据修复（本轮发现）

`0147-unit-batch6b-evidence-fixes.patch`，base 为 canonical 链到 `0144` 的树：

| 根因 | 影响 | 修复 |
| --- | --- | --- |
| `0142` UWB/DMX/Finger 只登记了 UART TX 捕获条件，没有接入 idle 应答器的 arming 分支 | UART 命令字节不触发 fixture 注入，UWB 构造 "not connect"、Finger 版本门失败、DMX 无 frame 计数 | 把三款加入 idle arming 分支 |
| FPC1020A 的 GET_VERSION 一条命令要读**两帧**（控制帧 + 8 字节版本数据帧），通用应答器每次 idle 只注入一个 chunk | 第二帧缺失，版本门无法通过 | `finger` 改为一次性注入整条扁平 fixture 流 |
| Thermal2 寄存器构建读的是上电缓存字段，没有读 QOM fixture 槽位 | session-initial median/average/differential 输入不进入 guest 回读（guest 读到默认 25.0） | 改读 `values[0..2]` |

修复后的二进制用于**全部 6 个 session**（不只重跑受影响款），因此所有
report 的 `runtime_binary_sha256` 一致。

## 结论

6 款各建 1 个可见 session，均在 guest 内运行参考固件自带的**原始冻结 UIFlow2
驱动**，经真实 SoC I2C/UART 控制器读写，没有 host 端直写驱动返回值：

| Unit | 主机/端口 | 原始驱动类 | 结果 |
| --- | --- | --- | --- |
| `unit-id` | cores3 port-a | `IDUnit` (ATECC608B, 0x35) | **BLOCKED**（wake-to-address-0 harness 限制） |
| `thermal2` | cores3 port-a | `Thermal2Unit` (0x32) | PASS |
| `qrcode` | cores3 port-a | `QRCodeUnit`（I2C mode, 0x21） | PASS |
| `uwb` | cores3 port-a（官方 PORT.C） | `UWBUnit`（BU01 AT, UART） | PASS（仅字节层） |
| `dmx` | cores3 port-a（官方 PORT.C） | `DMX512Unit`（cdriver.esp_dmx） | PASS（仅字节层） |
| `finger` | cores3 port-a（官方 PORT.C） | `FingerUnit`（FPC1020A, UART） | PASS（仅字节层） |

**端口替换说明**：官方 PinMap 把 uwb/dmx/finger 放在 PORT.C，但当前 host-port
注册表只准入 `cores3/PORT.A`，因此这些 session 使用 cores3 PORT.A 的 GPIO 2/1
作为 harness 接线；guest 的 SoC 控制器路径真实执行，**官方连接器物理接线未被
验证**。每个 report 的 `official_port`/`runtime_port_substitution` 记录替换。

关键 controller-backed 观测（完整值见 `summary.json` 与 `report-<unit>.json`）：

- `thermal2`：guest `get_device_detail(0)`=`0x4064`、`(1)`=`100.1`、alarm=0、
  button=0、median=`31.5`；768 字节（384×u16）温度数组 head =
  `12224/12256/12224/13216`（raw=temp*128+8192 与 QOM fixture 精确一致）；
  QOM median/average/differential = `31.5/30.0/1.5`、i2c-address=0x32。
  **0x33 二义仍 unresolved（与 thermal 冲突），只实现 0x32。**
- `qrcode`：guest status=1、len=15、data=`M5STACK-TEST-QR`、trigger mode=0、
  button=0、fw=1；`clear_qrcode_data_status()` 后 guest/QOM status=0。
  **摄像头/扫码光学/解码 NOT RUN；UART 侧未建模。**
- `uwb`：构造完成（UWB fixture 应答器按命令注入）；QOM `tx-hex` =
  `41540d0a 41542b616e63686f725f7461673d302c4e6f6e650d0a 41542b5253540d0a
  41542b696e74657276616c3d350d0a 41542b7377697463686469733d310d0a`，
  frames-sent/injected≥5。**UWB RF/天线/测距/网络 NOT RUN；页面明确不支持
  自定义数据传输；只断言字节层。**
- `dmx`：`cdriver.esp_dmx` 在本参考固件可执行，guest `write_data(1,255)` 后
  QOM `tx-hex` 以 `00ff0000…` 开头（DMX start-code=0、channel 1=255 帧字节）。
  **DMX512/RS485 差分、隔离、XLR、120Ω、250kbps 时序 NOT RUN；只断言字节层。**
- `finger`：version gate=`B1.10.00`、user count/capacity=150（fixture 应答）、
  QOM `tx-hex` 以 `f526` 开头（GET_VERSION 帧）且 frames≥1。
  **指纹采集/匹配/150 用户/193B 特征 NOT RUN；只断言 0xF5/XOR 字节层。**
- `unit-id`：guest `IDUnit` 构造成功（0x35 scan 通过），但冻结 ATECC 驱动在每条
  命令前 `wakeup()` 向 I2C 地址 `0x00` 写 `0x00`；绑定 0x35 的 Unit 从机无法
  接收该 wake，`revision`/`serial`/`random` 均失败（CRC mismatch / port error）。
  **blocker：不伪造 revision/serial；真实 ECDSA/AES/Trust&GO 证书链、key slot
  锁定、10Kb EEPROM NOT RUN；树内无任何真实私钥/证书。**

每个会话在停止前取得 evidence ZIP，停止使用 `purge=0` 并回读保留 history；
`manifest.json`/`serial.log`/`units/*` 完整性检查在每条 report 中记录。原始
ZIP/frame/serial 留在本地忽略的 `.work`，仓库只提交摘要、哈希与复现命令。

## 复现

```bash
# 1) 构建 QEMU（base = canonical 25 层链到 0144，再 apply 0145）
rm -rf .work/native-lock-source/qemu/build
cd .work/native-lock-source/qemu
D=/Users/m5agent/Documents/ChatGPT/esp-emulator/.work/unit-runtime-build
PATH="$D/venv/bin:$PATH" PKG_CONFIG_PATH="$D/deps/lib/pkgconfig:$D/deps/share/pkgconfig" \
  ./configure --target-list=xtensa-softmmu --python="$D/venv/bin/python" ...
PATH="$D/venv/bin:$PATH" ninja -j10 qemu-system-xtensa
cp build/qemu-system-xtensa ../../M5StopWatch-QEMU/build/qemu/build/
# 2) 独立 Device Service（8799，独立 state/token，host-image）
M5_SERVICE_FLASH_MODE=host-image \
M5_QEMU_XTENSA="$PWD/.work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa" \
M5_QEMU_XTENSA_ROM_DIR="$PWD/.work/M5StopWatch-QEMU/build/qemu/pc-bios" \
  PYTHONPATH=platform/tools python3.12 platform/tools/serve.py 8799 \
  --bind 127.0.0.1 --state-dir .work/unit-batch6b-service \
  --api-token "$(cat .work/unit-batch6b-service.token)"
# 3) 每款一个可见 session（fixture 由 session-initial Unit inputs 提供）
export M5_SERVICE_API_TOKEN="$(cat .work/unit-batch6b-service.token)"
PYTHONPATH=platform/tools python3.12 tests/units/run_batch6b_cases.py \
  --api-url http://127.0.0.1:8799 --case thermal2 --out-dir .work/unit-batch6b-evidence
```

`unit-id` 预期 `BLOCKED`；其余 5 款预期 `PASS`。原始 ZIP/帧/串口日志留在本地
忽略的 `.work`，仓库只提交摘要、哈希与复现命令。

## 未覆盖与边界

- 全部物理语义：RF/热成像/光学/生物识别/电气 NOT RUN；
- 端口：uwb/dmx/finger 官方 PORT.C 用 cores3 PORT.A harness 替换（未验证物理连接器）；
- `thermal2` 的页面 `0x33` 地址二义、`qrcode` 的 UART 模式、`uwb` 的 RF/网络能力、
  `dmx` 的 DMX512 电气层、`finger` 的生物特征能力均未验证；
- `unit-id` 的 revision/serial/random 未取得（wake 前置失败），不伪造、不转授；
- 本结果只覆盖 cores3 + 记录固件 SHA + 记录 QEMU 二进制 SHA，不转授其他主机/固件。

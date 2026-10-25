<!-- GENERATED FILE: run `python3 platform/tools/project_snapshot.py --write` -->

# 项目快照（自动生成）

来源日期：`2026-10-25`；最新 evidence 日期：`2026-10-25`。

本页只汇总机器可读源和已提交 evidence，避免在多个文档手写同一组动态事实。实现结论、风险说明和验证层级仍以[项目当前状态](project-status.md)、[验证证据台账](validation-ledger.md)和 [项目 Backlog](project-backlog.md) 为准。

## 设备与后端

- 设备登记：`14` 台；Device Service 可创建：`13` 台。
- 设备分组：`esp32-c6` 2，`esp32-lx6` 1，`esp32-p4` 1，`esp32-s3` 9，`linux-arm64` 1。
- 外设状态：`partial` 1，`simulated` 13。

| 设备 | SoC | 后端 | 外设 | 最近验证 | 当前边界 |
| --- | --- | --- | --- | --- | --- |
| StopWatch (`stopwatch`) | ESP32-S3R8 | `qemu-esp32s3` | `simulated` | `2026-10-23` / `display-touch-peripherals-wifi-ble-pass` | 无登记 blocker |
| AtomS3R (`atoms3r`) | ESP32-S3-PICO-1-N8R8 | `qemu-esp32s3` | `simulated` | `2026-10-23` / `display-input-peripherals-wifi-ble-pass` | 无登记 blocker |
| CoreS3 (`cores3`) | ESP32-S3 | `qemu-esp32s3` | `simulated` | `2026-10-23` / `display-touch-peripherals-wifi-ble-pass` | UIFlow startup-menu palette PNG/tRNS assets render striped artifacts; ordinary RGB PNG and opaque drawing paths are correct |
| StickS3 (`sticks3`) | ESP32-S3-PICO-1-N8R8 | `qemu-esp32s3` | `simulated` | `2026-10-23` / `display-input-peripherals-wifi-ble-pass` | 无登记 blocker |
| Cardputer-ADV (`cardputer-adv`) | ESP32-S3FN8 | `qemu-esp32s3` | `simulated` | `2026-10-23` / `display-keyboard-peripherals-wifi-ble-pass` | 无登记 blocker |
| StackChan (`stackchan`) | ESP32-S3 | `qemu-esp32s3` | `simulated` | `2026-10-23` / `display-input-peripherals-wifi-ble-pass` | 无登记 blocker |
| StamPLC (`stamplc`) | ESP32-S3FN8 | `qemu-esp32s3` | `simulated` | `2026-10-23` / `display-input-peripherals-wifi-ble-pass` | 无登记 blocker |
| PaperColor (`papercolor`) | ESP32-S3R8 | `qemu-esp32s3` | `simulated` | `2026-10-23` / `display-input-peripherals-wifi-ble-pass` | 无登记 blocker |
| PaperMono (`papermono`) | ESP32-S3R8 | `qemu-esp32s3` | `simulated` | `2026-10-23` / `display-touch-peripherals-wifi-ble-pass` | 无登记 blocker |
| NanoC6 (`nanoc6`) | ESP32-C6FH4 | `qemu-esp32c6` | `simulated` | `2026-10-24` / `board-peripherals-wifi-ble-pass` | Zigbee/802.15.4 controller data plane is not modeled (RUNTIME-02) |
| Arduino Nesso N1 (`nesso-n1`) | ESP32-C6 | `qemu-esp32c6` | `simulated` | `2026-10-24` / `display-touch-peripherals-wifi-ble-pass` | Meshtastic remains PARTIAL after an independent post-application instruction access fault (RUNTIME-01 flash/PMP defect is fixed) |
| CardputerZero (`cardputer-zero`) | RP3A0 (BCM2837) | `external-linux-arm64` | `simulated` | `2026-10-22` / `linux-display-input-i2c-audio-power-usb-camera-partial` | not an ESP32 firmware target |
| Core2 (`core2`) | ESP32-D0WDQ6-V3 | `qemu-esp32lx6` | `simulated` | `2026-10-25` / `display-input-peripherals-wifi-ble-pass` | physical cache/PSRAM timing equivalence remains NOT RUN; bit-exact ESP32 BT baseband/controller remains NOT RUN; two independent two-instance no-stagger 4x120s gates pass 8/8, two independent three-instance 3x120s gates pass 6/6, two independent four-instance 4x120s gates pass 8/8, and two independent five-instance 30-second-stagger 5x120s gates pass 10/10; zero-stagger five-instance cold start remains unstable after one 5/5 PASS and one independent 3/5 FAIL on the same implementation; more-than-five-instance stability, sustained throughput and teardown modes beyond active-stop remain OPEN; the bounded-TCG host-memory result is validated only for the tested 7200s workload |
| Tab5 (`tab5`) | ESP32-P4NRW32 | `esp-emulator-native` | `partial` | `2026-10-22` / `display-touch-rs485-pass-peripherals-partial` | SC2356 MIPI CSI-2 controller/frame path missing from esp-emu 0.50.0; ES8388/ES7210 I2S register and PCM endpoints missing from esp-emu 0.50.0; ESP32-P4 USB Host controller and endpoint attachment missing; Tab5 ST7123 touch is currently a firmware GDB mailbox rather than an I2C chip model; Tab5 SDIO storage is not wired to a host block backend; Tab5 INA226 register preload reaches Power as 8000 mV/1248 mA/87%, direct machine.I2C write/read reaches RX8130 registers, and PI4IOE CHG_STAT/CHG_EN reach Power.isCharging() in both charging and discharging scenarios, but RTC progression, dynamic I2C/time injection and IP2326 analog current/termination behavior remain partial; BMI270 identity also remains partial |

## 通用固件审查

公开样本快照覆盖 `7` 台设备、`21` 个固件：`10` PASS、`11` PARTIAL、`0` FAIL。PARTIAL 不自动等于固件缺陷；`runtime_model_gap` 必须保留模型边界。

## 运行时模型缺口

| ID | 状态 | 缺口 |
| --- | --- | --- |
| `RUNTIME-01` | `FIXED` | C6 软件复位后 chip-id 错误 |
| `RUNTIME-05` | `FIXED` | S3 QEMU AP WPA2-PSK 数据面 |
| `RUNTIME-02` | `OPEN` | C6 Zigbee/802.15.4 运行时未建模 |
| `RUNTIME-03` | `OPEN` | Core2 legacy I2C controller/board-bus routing 未闭环 |
| `RUNTIME-04` | `OPEN` | Core2 for AWS ATECC608 未建模 |

## Backlog Task 板

| Task | 当前状态 | 下一项最小交付 |
| --- | --- | --- |
| `NET-04` | 进行中 | 真实 server/worker network namespace、worker-local StickS3 QEMU、三个独立 Docker 容器对、active-token multicast discovery、cross-subnet/NAT unicast seed discovery、network blackhole 后 OS process 与真实 QEMU PID stop/reap + lease expiry/requeue/retry、worker-local `qemu-unified` 的 HTTP/BLE/pcap companion fence、central/runtime restart continuity、session-create idempotency、trusted-host companion continuity，以及 re-claim 后旧 lease result `409` fencing 已 PASS。下一步补物理跨主机迁移/reattach、无 reachable seed 的任意 NAT traversal、QEMU 内 guest/device-controller 和 worker 未拥有的外部 side-effect fencing、namespace-managed/Tab5/cross-host companion 和生产调度 |
| `CORE2-02` | 进行中 | QOM 8 MiB、upper-bank `esp_himem` `3/3`、`3×120s` heap/周期联网 `3/3`、单次 600 秒压力、121 轮三 lease、最终 `tb-size=128` 7200s、active-stop/recovery、30 秒错峰 `2×120s`、双/三/四实例两批独立门禁和五实例 30 秒错峰两批 `10/10` 均已 PASS；`0008` 建立真实 guest HCI event/ACL fast path，`0009` 以 `8/4` 备用池关闭四实例启动 ACK burst，四实例每轮 36 events/9 ACLs、HLI `45/45`、`hli-errors=0`。`0010` ACK-state trace 证明零错峰五实例失败从 HLI delivery delay 开始，旧 response 与新 command 交错；behavioral workaround 均未稳定 |
| `FW-01` | 进行中 | 运行时权限、完整源码级许可扫描与法律审批 |
| `FW-02` | 进行中 | 真机 secure boot、Flash Encryption、eFuse 和生产 key 流程 |
| `FW-03` | 进行中 | API/WebBurner capability、Manifest、WebBurner 分段 size/SHA-256/SHA-1/MD5 完整性、矩阵 SHA、SD/NVS fixture 和 SHA-bound `ui-interactive`/`headless-serial`/`network-first` expectation 已完成；当前 AtomS3R/PaperMono 四样本为 `3 PASS / 1 PARTIAL / 0 FAIL`。OpenAI 在同一 BIN + NVS fixture 上通过 network-first 的 DHCP/DNS/TCP443/pcap；Open/WPA2 正确与错误密码也已确认。下一步补真实 key/云端服务结果，再扩更多设备与 firmware family |
| `RUNTIME-02` | 进行中（backend blocked） | esp-emu `--thread-sim` 已观察到双向 802.15.4 帧，但 commissioning/join 未完成；补 MAC ACK/commissioning 语义或取得公开固件匹配 ELF |
| `RUNTIME-03` | 进行中 | 对齐 Core2 legacy I2C controller port、SCL/SDA pin 与板级 bus；确认 `disable_timer_interrupt()` 的 BM8563 RTC 路径 |
| `RUNTIME-04` | 进行中 | 为 Core2 for AWS 提供 ATECC608 测试 slot/config fixture |
| `SVC-01` | 进行中 | central control-plane、runtime-service restart continuity、session-create idempotency 和 trusted-host unified HTTP/BLE companion continuity 已完成；namespace-managed/Tab5/cross-host companion、跨主机 idempotency、无 reachable seed 的任意 NAT traversal 与跨主机 reattach 仍待做 |
| `SVC-02` | 待做 | warm pool、队列、配额、对象存储和审计 |
| `SVC-03` | 待做 | 拆分 `device_service.py` 的存储、runtime、evidence 和 session 状态机 |
| `DOC-01` | 待做 | 将接近 6000 行的 `test_docs_consistency.py` 按文档索引、权威状态/Backlog、Core2、网络/worker、固件安全等领域拆分；把手写 stale-claim 断言收敛为结构化 claim/evidence 清单 |
| `HW-01` | 待做 | 代表设备同固件 SHA 的真机测试计划 |
| `TAB5-01` | 决策 | 重建或扩展 P4 backend |
| `UI-01` | 待做 | 逐设备高保真外壳、hitbox 和截图阈值 |
| `CZ-01` | 待做 | CardputerZero 系统、驱动和长期回归 |

## 代码与文档规模

- `platform/tools`：`40` 个 Python 模块，`34011` 行；规模最大的模块如下。

| 模块 | 行数 |
| --- | ---: |
| `device_service.py` | 9869 |
| `firmware_manifest.py` | 3067 |
| `user_firmware_matrix.py` | 2069 |
| `network_sandbox.py` | 1556 |
| `firmware_filesystems.py` | 1469 |
| `worker_agent.py` | 1429 |

- `tests/`：`66` 个可执行 Python 测试文件，分布在 `48` 个目录；`186` 个 evidence JSON。
- `patches/`：`10` 个补丁组，`59` 个 patch 文件。
- 文档：`214` 个 Markdown 页面，`19915` 行。

## 文档与测试

- 平台测试：`477` 项。
- Docs 新鲜度登记：`33` 行；其中非历史页 `26` 行，历史固定页 `7` 行。
- 文档职责分布：待办 `3`，契约 `6`，历史固定 `7`，实现/设计 `6`，参考 `7`，工作流/导航 `4`。
- 全量文档盘点：`214` 个 Markdown 页面；职责分布：权威/专题页 `33`，设备档案 `18`，示例 `1`，治理/入口 `3`，文档导航 `1`，补丁说明 `11`，平台说明 `3`，仓内历史记录 `5`，测试/用例说明 `137`，第三方来源说明 `2`。
- 所有非历史页的最近复核日期均与当前事实日期一致。
- 没有带显式旧复核日期的委派文档。
- 代码边界和大型模块的维护建议由[代码与验证入口地图](code-map.md)维护。

## 维护入口

- 当前能力、风险和真机边界：[项目当前状态](project-status.md)。
- 未完成 Task、依赖和验收：[项目 Backlog](project-backlog.md)。
- 带日期的验证结果和 evidence：[验证证据台账](validation-ledger.md)。
- 代码、测试和证据路径：[代码与验证入口地图](code-map.md)。
- 测试分层和 evidence 规则：[测试总索引](../tests/README.md)。
- QEMU/固件补丁分组：[补丁总索引](../patches/README.md)。
- 文档职责和新鲜度：[文档导航](README.md)。

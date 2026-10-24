# 运行时模型缺口登记

日期：`2026-10-25`

本文是“固件行为与模拟器模型不一致”时的统一登记页。它记录已经复现的
运行时能力缺口、关闭证据、责任边界和剩余验收条件；当前总体能力见
[项目当前状态](project-status.md)，修复排期见
[项目 Backlog](project-backlog.md)，证据历史见
[验证证据台账](validation-ledger.md)。

`runtime_model_gap` 表示模拟器缺少固件实际依赖的运行时能力。它也是
`PARTIAL`，不是固件 `PASS`，也不是固件 `FAIL`。只有排除模型缺口后，
同一串口异常才允许进入固件缺陷结论。

## 分类规则

| 观测 | 结论 | 是否说明固件有缺陷 |
| --- | --- | --- |
| 镜像、芯片、板型、分区或 eFuse 声明不兼容 | `REJECTED` / `unsupported_capability` | 仅说明不匹配，不评价固件 |
| 兼容镜像在目标设备上稳定触发已知固件异常 | `FAIL` | 是，仍需保留错误日志和复现条件 |
| 固件依赖尚未建模的控制器、复位域、无线协议或板级器件 | `PARTIAL` / `runtime_model_gap` | 否，先修模型或明确不支持 |
| Device Service、QEMU 启动参数、磁盘或网络夹具失败 | `INFRA_ERROR` | 否 |
| 目标设备、runtime 或所需输入没有运行 | `NOT RUN` | 否 |

同芯片、同设备名或同固件家族不能自动继承另一块板或另一个固件 SHA 的
`PASS`。板级装配、Flash/PSRAM、eFuse、复位生命周期、分区和实际外设数据面
都必须与样本匹配。

## 已关闭缺口

### RUNTIME-01：C6 软件复位后 chip-id 错误

| 字段 | 当前值 |
| --- | --- |
| 状态 | `FIXED`（virtual-device validation） |
| 影响 | ESP32-C6 QEMU 16 MiB Flash 的读地址模式、legacy program/erase 地址宽度和复位后 PMP 状态 |
| 首次路径 | 固件进入 C6 ROM/application，随后执行 `LP_SW_HPSYS` 软件复位 |
| 复位后现象 | ROM 报 `Invalid chip id. Expected 13 read 12. Bootloader for wrong chip?` |
| 样本 | M5Burner `1897200000000001757`，`Meshtastic unofficial` |
| 固件 SHA-256 | `ef8249ac7930fa51ac5bf03cea52d8de9a59dcbaf2130663ca0d5087a8053744` |
| 根因证据 | [`cross-vendor-runtime-model-gaps.json`](../tests/firmware/evidence-2026-10-24-cross-vendor-runtime-model-gaps.json) |
| 修复证据 | [`c6-soft-reset-flash-addressing.json`](../tests/firmware/evidence-2026-10-24-c6-soft-reset-flash-addressing.json) |

根因：

- C6 16 MiB 配置把 m25p80 全局强制为 4 字节地址；
- `0x20` Sector Erase 和 `0x02` Page Program 等 legacy 命令实际仍发送
  3 字节地址，模型误把首字节数据当成第 4 个地址字节；
- core dump 目标 `0x300000/0x900000...` 被写到 offset `0`，覆盖 C6
  secondary bootloader 头，使下一次 ROM 读到 chip id `0x0c`；
- QEMU 的通用 RISC-V reset 只 unlock PMP entry，没有清除旧地址/权限，
  第二次 ROM boot 还会在 `0x50002000` 触发 PMP Store access fault。

修复：

1. 16 MiB 读路径保留 4-byte address 配置；
2. legacy program/erase opcode 固定使用 3-byte address，显式 4-byte
   program/erase opcode 继续使用 4-byte address；
3. ESP RISC-V CPU 在 C6 复位时清空 PMP table、`mseccfg` 和 TLB；
4. 同一固件重新通过 Device Service 执行后不再出现 `Invalid chip id`，
   `runtime_model_gaps=[]`；
5. Nesso N1 官方外设组 `5/5`、NanoC6 板级探针不回归。

剩余边界：该 Meshtastic 样本仍会在应用启动后触发独立的 Instruction access
fault，因此当前样本状态是 `PARTIAL/fatal_after_application_frame`，不能写成
完整功能 PASS。这个问题不再属于 RUNTIME-01，需要单独确认是固件缺陷还是新的
运行时模型偏差。

### RUNTIME-05：S3 QEMU AP WPA2-PSK 数据面

| 字段 | 当前值 |
| --- | --- |
| 状态 | `FIXED`（virtual-device validation） |
| 影响 | 要求非空密码、WPA2 authmode threshold 或 EAPOL 的 ESP32-S3 固件 |
| 首次路径 | 公开 OpenAI Voice Assistant 从 NVS 读取密码，将 Open threshold 提升为 WPA2 |
| 原现象 | 旧 QEMU AP 只广播 Open auth，guest 持续 retry，不发生 association |
| 修复证据 | [`openai-nvs-precondition.json`](../tests/firmware/evidence-2026-10-25-openai-nvs-precondition.json) |
| QEMU patch | [`0029-esp32s3-wpa2-psk-data-plane.patch`](../patches/qemu-m5stack-peripherals/0029-esp32s3-wpa2-psk-data-plane.patch) |

修复包含：

1. beacon/probe/association response 广告 WPA2-PSK RSN；
2. 从 SSID/password 派生 PMK，并由 M1-M4 推导、安装 PTK/GTK；
3. 验证 M2/M4 MIC；错误密码在 M2 拒绝并 deauthenticate，guest 可重试；
4. S3 RX 在 radio 边界验证 CCMP，并向 closed WiFi firmware 提供其
   hardware-decrypted CCMP 布局；
5. 每次 WPA2 session 由 session id 派生 locally-administered MAC，同时写入
   S3 eFuse fixture 和 QEMU NIC，避免 guest、supplicant 和 DHCP 地址不一致；
6. DHCP reply 在 802.11 层按 pairwise-key unicast 交付，不绕过 guest
   DHCP、ARP、DNS 或 TCP 栈。

同一公开固件、同一 SHA 的结果：

- 正确密码：4-way、associate、CCMP RX、DHCP、`api.openai.com` DNS、
  TCP/443 和 HTTPS 尝试 PASS；
- 错误密码：M2 MIC mismatch、reason 15 deauth、retry、无 association、
  无 DHCP、无 HTTP PASS；
- Open 密码回归仍 PASS；
- pcap、串口、QEMU stderr marker、session-isolated NVS overlay 和清理绑定
  同一 session。

剩余边界：WPA3-SAE、WPA2 group-key multicast、真实 RF/PHY、channel/rate、
漫游和物理网卡行为仍是 `NOT RUN`。该修复是 WPA2-PSK 成对密钥与单播管理/
数据路径，不是完整无线安全栈。

## 当前缺口

### RUNTIME-02：C6 Zigbee/802.15.4 运行时未建模

| 字段 | 当前值 |
| --- | --- |
| 状态 | `OPEN` |
| 影响 | NanoC6 及后续依赖 ESP32-C6 IEEE 802.15.4/Zigbee 控制器的固件 |
| QEMU 现象 | `Zigbee_main` 阻塞并触发 task watchdog；当前 QEMU C6 profile 没有对应 radio/controller 数据面 |
| esp-emu 可行性 | 0.50.0 的 `--thread-sim` 能转发双向 802.15.4 帧；源码构建的 C6 switch/light 对已完成组网与 steering 启动，但未完成 commissioning/join 或 On/Off 命令 |
| 当前阻断 | 缺少可验证的 MAC ACK/commissioning 语义；公开 M5Burner Zigbee bin 的 ELF SHA 没有匹配文件，因此不能用 `--thread-sim` 直接验证该公开样本 |
| 证据 | [`cross-vendor-runtime-model-gaps.json`](../tests/firmware/evidence-2026-10-24-cross-vendor-runtime-model-gaps.json)、[`c6-zigbee-thread-sim-feasibility.json`](../tests/firmware/evidence-2026-10-24-c6-zigbee-thread-sim-feasibility.json) |

关闭条件：

1. 明确 Espressif C6 802.15.4 MAC/基带、DMA、中断和固件驱动路径；
2. 通过真实 guest 驱动和控制器接口建模，不在应用或 Python 层伪造
   `Zigbee_main` 状态；
3. 至少覆盖一个加入/收发/离网生命周期，或明确把不支持路径继续返回为
   `runtime_model_gap`；
4. 与 WiFi/BLE 共存的结论单独记录，不能由单次 Zigbee 启动推断。

下一项最小交付是取得可重建的 802.15.4 MAC ACK/commissioning 路径，或提供与
公开固件匹配的 ELF 并让 `run_feasibility.py` 从 `PARTIAL` 进入 join +
On/Off PASS。若两者都无法取得，该项目保持显式不支持，而不是承诺“所有 C6
固件均可运行”。

### RUNTIME-03：Core2 legacy I2C controller/board-bus routing 未闭环

| 字段 | 当前值 |
| --- | --- |
| 状态 | `OPEN` |
| 影响 | Core2 官方 legacy UIFlow 与 FactoryTest 的 PMIC/RTC 初始化交接 |
| 现象 | AXP 地址探测成功，QEMU trace 读到 chip id `0x4a`；随后 `disable_timer_interrupt()` 的下一事务发往 address `0x51`，`start_rc=1`（无 ACK），并在产生新的 address `0x34` PMIC 事务前返回 `I2C bus error (19)` |
| 识别依据 | 冻结 qstr 中 `hardware/__init__.py`、`BM8563`、`disable_timer_interrupt` 和 `__read_byte` 相邻；`0x51` 与 PCF8563/BM8563 RTC 地址一致。该组合强烈指向 RTC-candidate 路径，但仍需匹配源码或端口 trace 确认 |
| A/B 结果 | 默认 AXP2101 和 `M5SW_CORE2_PMIC=axp192` 均在初始化交接阶段失败；AXP192 QOM 节点存在；当前 trace 已排除“首次 chip-id 寄存器响应错误” |
| 证据 | [`core2-public-firmware-model-gaps.json`](../tests/firmware/evidence-2026-10-24-core2-public-firmware-model-gaps.json)、[`core2-axp-i2c-trace.json`](../tests/firmware/evidence-2026-10-24-core2-axp-i2c-trace.json) |

关闭条件：

1. 同时在 controller trace 中记录 I2C port id、配置的 SCL/SDA pins、目标
   QEMU bus 和板级 slave bus，解释为什么 `0x51` 被发到无设备路径；
2. 取得与 public firmware 匹配的 UIFlow1 source/frozen bytecode，确认
   AXP/BM8563 类实际使用的 controller、address/read API 和初始化顺序；
3. 修正板级 controller-to-physical-bus routing 或对应模型，不把同一 PMIC
   寄存器复制到多条总线来掩盖问题；
4. 若后续 trace 到达 AXP 设备，再判断是否仍需补 AXP192/AXP2101 寄存器语义；
5. 同一固件 SHA 在 Device Service 中渲染非空应用帧并保持运行。

当前调查边界：公开 `M5Stack_MicroPython` 尚未找到匹配该旧 UIFlow1 样本的
类实现，frozen MPY 提取也尚未成功。已确认 AXP `0x34` probe 和 chip id
`0x4a` 正常，下一个 `0x51` controller transaction 已无 ACK，而且失败发生
在下一次 AXP `0x34` 访问之前；因此不能继续用 PMIC 寄存器补丁解释当前首个
失败点。下一轮需要在不影响活动 soak 的独立 QEMU 构建中记录 port、GPIO mux
和板级 bus handoff。

### RUNTIME-04：Core2 for AWS ATECC608 未建模

| 字段 | 当前值 |
| --- | --- |
| 状态 | `OPEN` |
| 影响 | `Core2_For_AWS` 及依赖 ATECC608 安全元件的固件 |
| 现象 | ATECC608 初始化返回 `atcab_init` 失败，固件随后 `abort()`，无应用帧 |
| 证据 | [`core2-public-firmware-model-gaps.json`](../tests/firmware/evidence-2026-10-24-core2-public-firmware-model-gaps.json) |

关闭条件：

1. 明确公开固件使用的 ATECC608 I2C 命令和必需配置区；
2. 提供不从仓库分发生产私钥的测试 slot/config fixture；
3. 同一固件完成安全元件初始化并进入应用帧，安全芯片结论仍与功能帧分开。

## 与固件矩阵的关系

跨厂商矩阵的状态语义由
[热门用户固件矩阵](user-firmware-simulation-matrix.md)定义。S3/C6 的
18 样本历史快照中有两个缺口进入本页，其中一个现已关闭；当前合并后的
21 个公开非基线样本还纳入了 Core2 PMIC/AWS 缺口。它们绑定当时的 artifact
SHA；公开 CDN 的当前 BIN 会变化，刷新后必须重新执行，不能继承历史 FAIL
或 PARTIAL。其余 `PARTIAL`
仍按首帧、输入、串口生命周期或
仅串口设备等独立原因记录，不能因为页面放在同一个矩阵中就合并为模型缺陷。
`RUNTIME-05` 来自后续 OpenAI 首次启动对照，不属于那 21 个历史样本的原始
`runtime_model_gap` 计数；它已由独立三组 Open/WPA2/错误密码证据关闭。

新增 `runtime_model_gap` 时必须同时：

1. 在 evidence 中保留 bounded serial/error、firmware SHA、profile 和检查项；
2. 在本页增加受影响的控制器/复位域、已知边界和关闭条件；
3. 在 Backlog 建立 Task ID；
4. 修复后用新 evidence 关闭任务，旧诊断 evidence 不得静默改写。

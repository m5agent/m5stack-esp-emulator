# 运行时模型缺口登记

日期：`2026-10-26`

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

### RUNTIME-03：Core2 I2C/timer/WDT-mask 已修复，legacy LVGL flush wait 未闭环

| 字段 | 当前值 |
| --- | --- |
| 状态 | `OPEN` |
| 修复进度 | controller-to-physical-bus routing `FIXED`；minimal probe 的 `CCOMPARE == CCOUNT` equal-deadline `FIXED`；TIMG WDT level IRQ 的 `INT_ENA` mask `FIXED`；stateful SSI 批量数据面 `VALIDATED`；统一 handoff timeline `VALIDATED`；WDT-off 45/120 秒对照把失败收敛到约 44 秒后的 LVGL double-buffer flush wait；BIN-bound 映射确认 display `flush_cb` 已执行，但 SPI completion/`lv_disp_flush_ready` 未出现；reset PC `0` 和 black-frame `OPEN` |
| 影响 | Core2 官方 legacy UIFlow、FactoryTest，以及 long-synchronous flash/partition-read workload |
| I2C 根因 | AXP `0x34` chip id `0x4a` 读取成功；controller trace 进一步证明旧固件在 `/machine/soc/i2c0/i2c` 上访问 AXP 和 RTC address `0x51`，而旧板模型只把 AXP/INA 挂在 controller 0，把 RTC/touch/IMU 挂在 controller 1。`0x51` 的 `start_rc=1` 由 controller-to-physical-bus routing 拆分直接解释 |
| I2C 修复 | `0031-core2-shared-board-i2c.patch` 将两个 controller register block 都路由到唯一物理 GPIO21/22 board bus，器件只挂一份 |
| Timer 根因 | 最小探针在 `CORE2_FLASH_IPC_READ_START` 后捕获到 timer ISR 写入 `CCOMPARE == CCOUNT`。旧 QEMU 用无符号减法把它解释成 `2^32` ticks；Core2 下一次 timer 中断因此被推迟约 26.8 秒，超过 interrupt-WDT 窗口，随后两个 CPU 都停在 idle |
| Timer 修复 | `0034-xtensa-ccompare-equal-deadline.patch` 只把相等期限安排到下一 CPU cycle；其他 delta 仍保留原 32 位回绕语义，不增加 catch-up、trace 或 timeout 放宽 |
| WDT mask 根因 | `0032` trace 捕获到 `INT_ENA=0x00000000`、`INT_RAW=0x00000004`、masked status `0x00000000` 时，旧模型仍抬高 WDT level IRQ。WDT raw status 本身不是 interrupt request，level line 只应由 `INT_RAW & INT_ENA` 驱动 |
| WDT mask 修复 | `0035-esp32-timg-wdt-int-ena.patch` 只在 `INT_ENA.WDT` 置位时抬高 level IRQ，保留 raw status 和 WDT stage timer 行为；同一 legacy SHA 修复后仍出现 `TG0WDT_SYS_RESET` 和 reset PC `0`，因此它不是 `RUNTIME-03` 根因修复 |
| QIO 修复/诊断 | `0036-ssi-transfer-buf.patch` 增加通用 byte-buffer SSI 接口和 m25p80 `STATE_READ` 快速路径，保留 command/address/dummy/CS/wrap 状态；前 512 个 64-byte 批次与原逐字节路径完全一致，Core2 UIFlow2 外设组 `6/6 PASS`。临时 `blk_pread` 与 SSI 字节一致，但绕过状态机；旧 REPL 观察在当前重建 120 秒窗口中未复现 |
| cross-core 诊断 | 关闭 WDT reset 后，直接 state trace 观察到 flash-op `can_start`/`complete` 和 cross-core reason 反复在 0/1 间变化；CPU0 会多次位于 `spi_flash_op_block_func` 等待路径，CPU1 位于 cache/DPORT 或任务切换路径。该阶段排除了永久 handshake deadlock，并曾把累计同步 handoff 吞吐列为候选；后续 WDT-off 45/120 秒 late-state 证明 Flash/SSI 活动有终点，候选已退役 |
| handoff timeline | `0037-esp32-handoff-trace.patch` 用默认关闭的 `M5SW_ESP32_HANDOFF_TRACE` 把 virtual time、CPU、guest PC、cross-core、DPORT cache、SSI transaction、UART IRQ 与 TIMG WDT 写入统一格式。早期 normal-WDT 配置曾在 TG1 最后一次 feed 后 `800,000,000 ns` 进入 stage-0 timeout；该结果保留为历史 trace 配置证据，不作为当前固定路径 |
| PC 地址审计 | 早期 1 ms PC 采样对照复现过固定 800 ms gap，但 reset 提前。`audit_elf_bin_mapping.py` 对 public legacy v1.15.4 BIN 与 local UIFlow2 v2.5.3 ELF 做同 VMA 字节比较，CPU0 `0x400843ac/af/b1` 三处全部 mismatch，因此 `uart_rx_intr_handler_default` 与 `mp_execute_bytecode` 符号映射被拒绝 |
| PC 当前解释 | 地址簇本身仍来自同一 public BIN。BIN 自身在 `0x400843ac` 附近读取/写入 cross-core、DPORT `0x3ff000e8/e4` 与 Flash/cache handoff 状态，和旧 IDF cache-disable 控制流一致；但没有 matching ELF/MAP，不能命名精确函数或证明具体等待对象。UART storm 解释撤回 |
| exact-time freeze | `0038-esp32-handoff-pause.patch` 用 `M5SW_ESP32_HANDOFF_PAUSE_NS` 在指定 virtual time 发 `SIGSTOP`，不启用高频 PC sampling。14.800 s 早窗口两核 PC 不固定；15.301 s 晚窗口 CPU0 `0x40087980`、CPU1 `0x40084484`，CPU1 `INTSET=0x40`、`interrupt_request=HARD`。BIN 源码形态与旧 IDF `spi_flash_op_block_func` complete wait 和 cache handshake 一致，证明晚窗口不是 UART，但仍未证明哪个 restore/SSI/DPORT 操作未返回 |
| exact-time state sweep | `0039-esp32-handoff-state-dump.patch` 在 pause 前直接记录两核 PC/IRQ 状态、`0x3ffc7ec8/c9`、`0x3ffc7750/54`、DPORT cache、cache-sync、SSI 和 cross-core counters。14.8/15.3/15.9 s 三轮中 CPU0 前两轮均停在 `0x40087980`，CPU1 在 15.9 s 已进入不同路径；cache-sync calls `16144→16180→17444`，changed-page 累计停在 `6679`，SSI transactions `6984→6998→7506`、cross-core writes `40274→40566→43584` 继续增加。两核永久停止被排除 |
| completed handoff setter trace | `0040-xtensa-handoff-pc-trace.patch` 只记录显式 BIN-bound setter PC。normal-WDT 首轮在 `5.913935 s` 出现 stage-0 timeout，`15.914787 s` 首次 reset；reset 前 complete/can-start 的四个 setter 计数为 `4,377/4,377/4,377/4,376`。说明 cache handoff 反复完成；旧“永久 deadlock”解释不支持，剩余问题是大量完成周期为何仍未产生足够应用进度 |
| WDT liveness 3x | `run_wdt_liveness.py` 关闭 PC trace，保留 TIMG verbose trace，通过三个独立 Device Service lease 观察同一 firmware。TG0 stage-0 在 `5.9107-5.9226 s` timeout 且中断被 mask；TG0 stage-1 在 `15.9119-15.9266 s` 触发首次 reset。TG1 每轮完成 `6,618-6,807` 次 feed，最大相邻间隔 `8.478-10.410 ms`，最后 feed 距 reset `1.779-4.271 ms`，`0` 次 TG1 timeout；stage-0 后没有 TG0 feed/reconfigure/protect 写入。三轮分类统一为 `BOOTLOADER_TG0_STAGE1_RESET_WITH_TG1_LIVE`，历史 `800 ms` TG1 gap 当前为 `NOT_REPRODUCED` |
| WDT-off late state | `0041` 增加 A0-A15、PS、对象前向指针和有界 stack dump。WDT-off 45/120 秒两个独立 lease 均停在 CPU0 `0x4026306e` halted waiti、CPU1 `0x40100049` running spin；cache-sync calls `49,848`、changed pages `45,847`、state updates `49,265` 和 SSI `22,554` transactions / `671,936` RX bytes 在两次 snapshot 中完全相同，最后 Flash/SSI 活动约 `43.91-44.00 s`。cross-core writes 从 `123,476` 增至 `139,094`。BIN-bound 反汇编把地址绑定到 LVGL 7 `lv_refr_vdb_flush`：`A2` 是 `lv_disp_buf_t`，`A2+24` 是 `flushing=1`；`A10` 是 display driver，`A10+28` 是 `wait_cb=0`，两个 buffer 均有效 |
| LVGL flush callback | `0x40174758` display `flush_cb` 在 50 秒 WDT-off PC trace 中于 `44.198632 s` 调用一次；本应调用 `lv_disp_flush_ready()` 的 `0x40174884` completion callback 没有出现，黑帧 SHA 不变 |
| SPI IRQ completion model | `0042` 补上 `SPI_SLAVE.TRANS_DONE/TRANS_INTEN` 和 SPI IRQ level，并记录 `trans_done=1/trans_inten=1/level=1`；50 秒窗口内 completion callback/`lv_disp_flush_ready` 仍未观测，normal-WDT 60 秒仍在约 `15.9157 s` 由 TG0 stage-1 首 reset。该模型是 diagnostic/partial，不关闭 `RUNTIME-03` |
| host flush control | 当 `changed_pages == 0` 时跳过 `memory_region_flush_rom_device()` 的探索性修改仍进入 `TG0WDT_SYS_RESET`，reset PC `0` 和黑帧 SHA 不变。该修改未保留为补丁；host-side 整块 flush 不是已测得的根因 |
| 修复后 | `0x34`、`0x51`、INA3221 `0x40` 均 ACK，原 `I2C bus error (19)` 消失；最小 probe 在 trace 开/关和 `shift=5`/`auto` 对照中通过首启动门禁，进入 `CORE2_FLASH_IPC_PASS` |
| 当前阻断 | normal-WDT 下 legacy `UIFlow_Core2 v1.15.4` 仍在 TG0 stage-1 首次 system reset，reset CPU PC `0`，只有 302-byte 黑帧。WDT-off 下 display `flush_cb` 已执行，但 SPI completion callback 未执行，LVGL `lv_disp_buf_t.flushing` 保持 1；120 秒仍无 setup/REPL |
| 当前判断 | 原“未知 flag/object”已退役。CPU1 明确位于 LVGL 7 `lv_refr_vdb_flush` 的双缓冲 wait，display `flush_cb` 已启动，但 `0x40174884` completion 和 `lv_disp_flush_ready` 未出现。`0042` 的 `TRANS_DONE/TRANS_INTEN` IRQ level 已能建立，但还不足以让 guest completion 路径运行；剩余缺口在 SPI interrupt matrix/status、queue/ISR 调度或后续硬件状态 |
| 证据 | [`core2-lvgl-spi-wait.json`](../tests/firmware/core2_handoff_trace/evidence-2026-10-26-core2-lvgl-spi-wait.json)、[`core2-wdt-off-late-state.json`](../tests/firmware/core2_handoff_trace/evidence-2026-10-26-core2-wdt-off-late-state.json)、[`0042 SPI/LVGL diagnostic patch`](../patches/qemu-m5stack-peripherals/0042-esp32-spi-trans-done-irq-diagnostic.patch)、[`0041 register/stack patch`](../patches/qemu-m5stack-peripherals/0041-esp32-handoff-register-stack-dump.patch)、[`late-state contract`](../platform/tests/test_core2_wdt_off_late_state.py)、[`core2-wdt-liveness-3x.json`](../tests/firmware/core2_handoff_trace/evidence-2026-10-26-core2-wdt-liveness-3x.json)、[`WDT liveness runner`](../tests/firmware/core2_handoff_trace/run_wdt_liveness.py)、[`WDT liveness contract`](../platform/tests/test_core2_wdt_liveness.py)、[`core2-handoff-pc-trace.json`](../tests/firmware/core2_handoff_trace/evidence-2026-10-26-core2-handoff-pc-trace.json)、[`core2-handoff-state-sweep.json`](../tests/firmware/core2_handoff_trace/evidence-2026-10-26-core2-handoff-state-sweep.json)、[`core2-handoff-pause.json`](../tests/firmware/core2_handoff_trace/evidence-2026-10-26-core2-handoff-pause.json)、[`0038 pause patch`](../patches/qemu-m5stack-peripherals/0038-esp32-handoff-pause.patch)、[`0039 state dump patch`](../patches/qemu-m5stack-peripherals/0039-esp32-handoff-state-dump.patch)、[`0040 PC trace patch`](../patches/qemu-m5stack-peripherals/0040-xtensa-handoff-pc-trace.patch)、[`state sweep runner`](../tests/firmware/core2_handoff_trace/run_pause_sweep.py)、[`PC trace runner`](../tests/firmware/core2_handoff_trace/run_pc_trace.py)、[`state sweep contract`](../platform/tests/test_core2_handoff_state_sweep.py)、[`PC trace contract`](../platform/tests/test_core2_handoff_pc_trace.py)、[`core2-pc-mapping-audit.json`](../tests/firmware/core2_handoff_trace/evidence-2026-10-26-core2-pc-mapping-audit.json)、[`mapping audit tool`](../tests/firmware/core2_handoff_trace/audit_elf_bin_mapping.py)、[`core2-handoff-timeline.json`](../tests/firmware/core2_handoff_trace/evidence-2026-10-26-core2-handoff-timeline.json)、[`summarizer`](../tests/firmware/core2_handoff_trace/summarize.py)、[`core2-ssi-transfer-buf.json`](../tests/firmware/evidence-2026-10-26-core2-ssi-transfer-buf.json)、[`core2-qio-crosscore-diagnostic.json`](../tests/firmware/evidence-2026-10-26-core2-qio-crosscore-diagnostic.json)、[`core2-shared-board-i2c.json`](../tests/firmware/evidence-2026-10-25-core2-shared-board-i2c.json)、[`core2-wdt-timing.json`](../tests/firmware/evidence-2026-10-25-core2-wdt-timing.json)、[`core2-flash-ipc-wdt.json`](../tests/firmware/core2_flash_ipc/evidence-2026-10-26-core2-flash-ipc-wdt.json)、[`equal-deadline evidence`](../tests/firmware/core2_flash_ipc/evidence-2026-10-26-core2-ccompare-equal-deadline.json)、[`0031 patch`](../patches/qemu-m5stack-peripherals/0031-core2-shared-board-i2c.patch)、[`0032 trace patch`](../patches/qemu-m5stack-peripherals/0032-esp32-timg-wdt-trace.patch)、[`0034 timer patch`](../patches/qemu-m5stack-peripherals/0034-xtensa-ccompare-equal-deadline.patch)、[`0035 WDT mask patch`](../patches/qemu-m5stack-peripherals/0035-esp32-timg-wdt-int-ena.patch)、[`0036 SSI batch patch`](../patches/qemu-m5stack-peripherals/0036-ssi-transfer-buf.patch)、[`0037 handoff trace patch`](../patches/qemu-m5stack-peripherals/0037-esp32-handoff-trace.patch) |

关闭条件：

1. 保持 `0034` 的最小 probe 门禁可重放，业务补丁不得夹带 IRQ ring/trace；
2. 保持 `0035` 的 `INT_RAW & INT_ENA` level 语义，并证明 raw status 仍可读；
3. 保持 `0036` 的 stateful SSI byte-buffer 数据面与 byte equivalence，
   禁止重新引入直接 `blk_pread` bypass；
4. 对同一 legacy firmware SHA 记录 TG0/TG1 watchdog feed/clear、stage0/
   stage1、`INTSET`、`INTENABLE`、timer expiry、IDLE/service task 进度和
   reset 前最后一个有效 PC；三次 WDT liveness 已满足 TG0 stage0/stage1、
   TG1 feed 间隔和 reset 顺序，后续需补启动 phase 归属；
5. 使用 `0037` timeline 把 TG0 stage-1 前的 flash-cache pause、
   cross-core call/ack、DPORT high-interrupt 和 guest 清标志按启动 phase
   关联；历史 `800 ms` 窗口仅在相同 trace 配置重放后才能重新作为候选；
6. 取得 public legacy v1.15.4 的 matching ELF/MAP；byte audit 已证明 local
   UIFlow2 v2.5.3 ELF 在 CPU0 三个采样地址上全部不等，不得继续使用该
   UART/VM 符号映射；
7. 在 matching 符号缺失时，用 BIN 自身字节和中低频事件确认
   cross-core/DPORT/cache-disable 区域，并直接区分 CPU0 vCPU 未获调度、
   guest spin 与 handoff 永久等待；
8. 保持 `0x40100049` 的 BIN-bound 语义：LVGL `lv_refr_vdb_flush`
   双缓冲 wait，`A2+24` 为 `flushing`，`A10+28` 为可空 `wait_cb`；
9. 修正 SPI `TRANS_DONE` 到 interrupt matrix/guest SPI ISR 的投递和
   queue/status completion，直到 display completion callback
   `0x40174884` 与 `lv_disp_flush_ready` 可观测；
10. 同一 legacy 固件 SHA 在正常 WDT、真实 SSI/m25p80 数据面下渲染非空
   应用帧并保持运行，不得依赖 WDT 关闭、bulk bypass 或 retry；
11. 回归现有 UIFlow2 Core2 设备组，确保 shared bus 不破坏 touch/IMU/RTC/
   audio/mic 路径。

当前调查边界：shared bus、equal-deadline timer、WDT mask、stateful SSI、
统一 timeline、state sweep、setter trace 和三-run WDT liveness 都已形成可重放
控制，但 normal-WDT legacy 仍在 TG0 stage-1 首 reset，且没有非空帧。
WDT-off 45/120 秒对照进一步显示 Flash/SSI 活动约在 44 秒结束，CPU0 进入
`waiti`，CPU1 稳定在 LVGL 双缓冲 flush wait；120 秒时仍没有 setup/REPL。
当前最窄问题是 SPI completion 到 `lv_disp_flush_ready()` 的链路，而不是
继续假设 TG1 feed 停止、Flash 扫描永不结束或存在未命名 late object。旧 UIFlow1 的
TG0 stage-1 reset、reset PC `0`、non-empty frame 与稳定运行仍为 `FAIL`。
matching ELF/MAP 缺失时不得从不同版本固件借用符号；`Core2FactoryTest`
修复后仍未重跑。

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

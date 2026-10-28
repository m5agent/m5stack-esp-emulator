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

### RUNTIME-03：scheduler/DPORT 与经典 RMT 初始化已修复，legacy WDT/LVGL/应用帧未闭环

| 字段 | 当前值 |
| --- | --- |
| 状态 | `OPEN` |
| 修复进度 | controller-to-physical-bus routing `FIXED`；minimal probe 的 `CCOMPARE == CCOUNT` equal-deadline `FIXED`；TIMG WDT level IRQ 的 `INT_ENA` mask `FIXED`；stateful SSI 批量数据面 `VALIDATED`；统一 handoff timeline `VALIDATED`；`0064` 修复 pending SPI/INTMATRIX remap；`0065` 关闭单线程 TCG slice 导致的 high-priority DPORT handoff deadlock，五轮首启动 `5/5 PASS`；`0066` 补经典 ESP32 RMT，移除 Neopixel translator 初始化失败并让 legacy Serial 到达 `APIKEY`；最新 WDT-off runtime 仍为 302-byte 黑帧，normal-WDT reset、display completion/`lv_disp_flush_ready`、setup/REPL 与非空应用帧 `OPEN` |
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
| SPI pending remap | `0064` 为 interrupt matrix 保存输入 level，并在 mapping 写入时重新计算 CPU external-interrupt outputs。独立 ESP-IDF SPI3 probe 在同一固件/ELF 上从 pre-fix callback timeout 变为 fixed `3/3 PASS`，显式覆盖 pending source remap、`TRANS_DONE && TRANS_INTEN`、guest post callback 和 queued-result completion。该结果修复通用 SPI/INTMATRIX 子缺口，但 legacy `UIFlow_Core2 v1.15.4` 仍没有非空应用帧 |
| DPORT high-priority handoff | `0065` 跟踪每个 CPU 的 Xtensa level-4/5 handler：handler 在 `memw` 发布 start flag 后让出 TCG slice，sender 经 `retw` 返回 end 路径时再次协作；level-5 返回 level-4 时不清 active，离开 level 4、RFI/RFE 与 reset 才清除。guest 指令、virtual time、中断级别和协议 flag 未修改；状态机只在 TCG icount 启用时工作。五轮独立 early-state 在 `5.000000002-5.000000031 s` 结束，`5/5 PASS`，消除 CPU0 等 start/CPU1 等 end 的调度诱导死锁 |
| Classic ESP32 RMT | `0066` 实现 `0x3ff56000` legacy RMT 的 8 channel、寄存器、2 KiB RMTMEM、`conf0.mem_size` 读回、memory-mode TX、threshold、`TX_END`、INTMATRIX source 47 和有界 symbol capture。修复前 `mem_size=0` 导致 `RMT translator buffer create fail` / Neopixel `OSError`；修复后 trace 四次捕获 channel 7、每次 49 symbols，Serial 到达 `BOARD NAME`/`APIKEY`。只证明控制器内存 TX 初始化，不证明 GPIO waveform 或电气时序 |
| host flush control | 当 `changed_pages == 0` 时跳过 `memory_region_flush_rom_device()` 的探索性修改仍进入 `TG0WDT_SYS_RESET`，reset PC `0` 和黑帧 SHA 不变。该修改未保留为补丁；host-side 整块 flush 不是已测得的根因 |
| 修复后 | `0x34`、`0x51`、INA3221 `0x40` 均 ACK，原 `I2C bus error (19)` 消失；最小 probe 在 trace 开/关和 `shift=5`/`auto` 对照中通过首启动门禁，进入 `CORE2_FLASH_IPC_PASS` |
| 当前阻断 | final runtime 的 normal-WDT 控制仍在 TG0 stage-0 `7.249439902 s`、stage-1 `17.249439902 s` 超时，并于 `17.249530334 s` 首次 `TG0WDT_SYS_RESET`；两核 guest 报告 PC `0`。WDT-off 在 68 秒到达 `APIKEY`，但 320x240 帧仍为 302-byte、`0` nonblack pixels；display completion、setup/REPL 和正常启动下的非空应用帧均未出现 |
| 当前判断 | `0065` 已证明旧固定双 PC deadlock 是 scheduler artifact，`0066` 已证明 Neopixel 初始化失败是缺失 classic RMT，两者都是实际模型修复。剩余问题不能再用 DPORT 永久 deadlock 或 RMT translator 初始化解释；下一轮需在 normal-WDT 下定位 `APIKEY` 之后的首个未完成 guest/controller 路径，并保持最终三设备 UIFlow2 回归 |
| 证据 | [`本轮协作 IRQ/RMT/三设备证据`](evidence/2026-10-28-cooperative-highint-rmt/README.md)、[`机器摘要`](evidence/2026-10-28-cooperative-highint-rmt/summary.json)、[`0066 RMT patch`](../patches/qemu-m5stack-peripherals/0066-esp32-classic-rmt-legacy.patch)、[`0066 contract`](../platform/tests/test_esp32_classic_rmt_patch.py)、[`0065 cooperative patch`](../patches/qemu-m5stack-peripherals/0065-xtensa-high-priority-irq-cooperative-yield.patch)、[`0065 contract`](../platform/tests/test_xtensa_high_priority_irq_cooperative.py)、[`SPI IRQ remap fixed`](../tests/firmware/core2_spi_irq_remap/evidence-2026-10-28-core2-spi-irq-remap.json)、[`SPI IRQ remap pre-fix control`](../tests/firmware/core2_spi_irq_remap/evidence-2026-10-28-core2-spi-irq-remap-control.json)、[`core2-lvgl-spi-wait.json`](../tests/firmware/core2_handoff_trace/evidence-2026-10-26-core2-lvgl-spi-wait.json)、[`core2-wdt-off-late-state.json`](../tests/firmware/core2_handoff_trace/evidence-2026-10-26-core2-wdt-off-late-state.json)、[`0064 SPI/INTMATRIX patch`](../patches/qemu-m5stack-peripherals/0064-esp32-intmatrix-pending-irq-remap.patch)、[`0064 contract`](../platform/tests/test_core2_intmatrix_pending_remap_patch.py)、[`0042 SPI/LVGL diagnostic patch`](../patches/qemu-m5stack-peripherals/0042-esp32-spi-trans-done-irq-diagnostic.patch)、[`0041 register/stack patch`](../patches/qemu-m5stack-peripherals/0041-esp32-handoff-register-stack-dump.patch)、[`late-state contract`](../platform/tests/test_core2_wdt_off_late_state.py)、[`core2-wdt-liveness-3x.json`](../tests/firmware/core2_handoff_trace/evidence-2026-10-26-core2-wdt-liveness-3x.json)、[`WDT liveness runner`](../tests/firmware/core2_handoff_trace/run_wdt_liveness.py)、[`WDT liveness contract`](../platform/tests/test_core2_wdt_liveness.py)、[`core2-handoff-pc-trace.json`](../tests/firmware/core2_handoff_trace/evidence-2026-10-26-core2-handoff-pc-trace.json)、[`core2-handoff-state-sweep.json`](../tests/firmware/core2_handoff_trace/evidence-2026-10-26-core2-handoff-state-sweep.json)、[`core2-handoff-pause.json`](../tests/firmware/core2_handoff_trace/evidence-2026-10-26-core2-handoff-pause.json)、[`0038 pause patch`](../patches/qemu-m5stack-peripherals/0038-esp32-handoff-pause.patch)、[`0039 state dump patch`](../patches/qemu-m5stack-peripherals/0039-esp32-handoff-state-dump.patch)、[`0040 PC trace patch`](../patches/qemu-m5stack-peripherals/0040-xtensa-handoff-pc-trace.patch)、[`state sweep runner`](../tests/firmware/core2_handoff_trace/run_pause_sweep.py)、[`PC trace runner`](../tests/firmware/core2_handoff_trace/run_pc_trace.py)、[`state sweep contract`](../platform/tests/test_core2_handoff_state_sweep.py)、[`PC trace contract`](../platform/tests/test_core2_handoff_pc_trace.py)、[`core2-pc-mapping-audit.json`](../tests/firmware/core2_handoff_trace/evidence-2026-10-26-core2-pc-mapping-audit.json)、[`mapping audit tool`](../tests/firmware/core2_handoff_trace/audit_elf_bin_mapping.py)、[`core2-handoff-timeline.json`](../tests/firmware/core2_handoff_trace/evidence-2026-10-26-core2-handoff-timeline.json)、[`summarizer`](../tests/firmware/core2_handoff_trace/summarize.py)、[`core2-ssi-transfer-buf.json`](../tests/firmware/evidence-2026-10-26-core2-ssi-transfer-buf.json)、[`core2-qio-crosscore-diagnostic.json`](../tests/firmware/evidence-2026-10-26-core2-qio-crosscore-diagnostic.json)、[`core2-shared-board-i2c.json`](../tests/firmware/evidence-2026-10-25-core2-shared-board-i2c.json)、[`core2-wdt-timing.json`](../tests/firmware/evidence-2026-10-25-core2-wdt-timing.json)、[`core2-flash-ipc-wdt.json`](../tests/firmware/core2_flash_ipc/evidence-2026-10-26-core2-flash-ipc-wdt.json)、[`equal-deadline evidence`](../tests/firmware/core2_flash_ipc/evidence-2026-10-26-core2-ccompare-equal-deadline.json)、[`0031 patch`](../patches/qemu-m5stack-peripherals/0031-core2-shared-board-i2c.patch)、[`0032 trace patch`](../patches/qemu-m5stack-peripherals/0032-esp32-timg-wdt-trace.patch)、[`0034 timer patch`](../patches/qemu-m5stack-peripherals/0034-xtensa-ccompare-equal-deadline.patch)、[`0035 WDT mask patch`](../patches/qemu-m5stack-peripherals/0035-esp32-timg-wdt-int-ena.patch)、[`0036 SSI batch patch`](../patches/qemu-m5stack-peripherals/0036-ssi-transfer-buf.patch)、[`0037 handoff trace patch`](../patches/qemu-m5stack-peripherals/0037-esp32-handoff-trace.patch) |

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
9. 保持 `0064` 的 pending SPI remap、`TRANS_DONE && TRANS_INTEN` 和
   guest callback 回归；继续解释最新 legacy runtime 为何在 display
   `flush_cb` 之前停止或 reset，直到 completion callback
   `0x40174884` 与 `lv_disp_flush_ready` 可观测；
10. 同一 legacy 固件 SHA 在正常 WDT、真实 SSI/m25p80 数据面下渲染非空
   应用帧并保持运行，不得依赖 WDT 关闭、bulk bypass 或 retry；
11. 回归现有 UIFlow2 Core2 设备组，确保 shared bus 不破坏 touch/IMU/RTC/
   audio/mic 路径；
12. 保持 `0065` 的 level-4/5 handler `memw`/`retw` 协作点和 RFI/reset
   active-state 清理，并继续以零 retry 首启动证明 DPORT handoff 不再固定
   双 PC 死锁；
13. 保持 `0066` 的 classic RMT 寄存器、`mem_size`、RMTMEM、threshold、
   `TX_END` 和有界 capture 契约；RMT 初始化通过不能替代 GPIO waveform、
   Neopixel 光学或 legacy 应用帧 PASS；
14. 在同一 final runtime 上给出 `APIKEY` 之后的首个未完成 guest/controller
   路径，并在 normal-WDT 下完成 setup/REPL、非空应用帧和稳定运行。

当前调查边界：shared bus、equal-deadline timer、WDT mask、stateful SSI、
统一 timeline、pending SPI remap、high-priority IRQ 协作和 classic RMT
都已形成可重放控制。`0065` 关闭调度诱导 DPORT deadlock，`0066` 关闭
Neopixel RMT translator 初始化失败；最终 WDT-off 控制到达 `APIKEY` 后仍是
302-byte 黑帧。normal-WDT 的 TG0 stage-1 reset、display completion、
setup/REPL、non-empty frame 与稳定运行仍为 `FAIL`。matching ELF/MAP 缺失时
不得从不同版本固件借用符号；`Core2FactoryTest` 修复后仍未重跑。

### RUNTIME-06：ESP-NOW controller loopback 已验证，外部/加密 peer 未建模

| 字段 | 当前值 |
| --- | --- |
| 状态 | `PARTIAL` |
| 影响 | 原厂 `espnow.ESPNow`、`ESPNowBase`、`m5espnow.M5ESPNow` 的 payload、receive 和 IRQ 路径；当前不覆盖外部 peer、PMK 加密、跨设备 fabric 和 RF/timing |
| 当前模型 | `0067-esp32-espnow-controlled-peer-loopback.patch` 在明确设置 `M5SW_ESPNOW_LOOPBACK=1` 时，只对 802.11 management action frame 做同 guest 回环：guest 经正常 TX DMA 写帧，模型交换 peer/source 后经正常 RX DMA 送回；broadcast 使用固定 locally-administered fixture peer `02:00:00:00:00:42` |
| 已验证 | 最终 QEMU `c3c3140322513de6f3ef724513e2f1272764e6af8a8fdd7c7bfd4448dc17f534` 上 StopWatch、StickS3、Core2 的 `m5espnow` unicast/broadcast/receive/IRQ PASS；native 三组 API 的 `send`/`recvinto`/`irq` 各 PASS；model patch 默认关闭 |
| 未覆盖 | 两个独立 guest/外部 peer、PMK 加密 payload、错误 key、丢包/重试、channel/rate、bit-exact controller、RF/antenna 和电气时序 |
| 证据 | [`最终接口复测`](evidence/2026-10-28-espnow-and-three-board-interface-retest/README.md)、[`0067 patch`](../patches/qemu-m5stack-peripherals/0067-esp32-espnow-controlled-peer-loopback.patch)、[`0067 contract`](../platform/tests/test_esp32_espnow_loopback_patch.py) |

关闭条件：

1. 使用两个独立 guest 或可审计外部 peer，完成真实 action-frame 交换；
2. PMK 加密 payload、错误 key、peer add/update/delete 与 receive/IRQ 生命周期可重放；
3. loopback、external 和 encrypted lane 分开记录，不能用 loopback 结果替代外部 peer；
4. 物理 RF/controller 等价性另行验证，不从 QEMU 结果推论。

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

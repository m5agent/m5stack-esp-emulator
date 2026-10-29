# 运行时模型缺口登记

日期：`2026-10-29`

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

### RUNTIME-04：Core2 for AWS ATECC608

| 字段 | 当前值 |
| --- | --- |
| 状态 | `FIXED`（virtual-device validation） |
| 影响 | `Core2_For_AWS` 及依赖 ATECC608 初始化、locked config 和 Info revision 的固件 |
| 原现象 | ATECC608 地址 `0x35` 全部 NACK，`atcab_init` 返回 `f0`，固件随后 `abort()` |
| 修复 | [`0085-core2-atecc608.patch`](../patches/qemu-m5stack-peripherals/0085-core2-atecc608.patch) 增加 CryptoAuthentication I2C slave、wake/idle/sleep、CRC16、Read 和 Info；同时修正 classic ESP32 DMA descriptor start 与 GPIO DC command/data 分类 |
| 证据 | [ATECC608 validation](evidence/2026-10-29-core2-atecc608/README.md)、[summary.json](evidence/2026-10-29-core2-atecc608/summary.json) |

同一公开 BIN SHA256
`22ee8c0f5d3c9640be370cb1a89496ed265b685d573b0e41d62320cf6288ff3a`
连续三个 `/api/v1` session 均从原 `atcab_init` 失败推进到
`atecc608: ok: 60 02`，并产生一致的 `320x240`、`76,800` nonblack
pixels、`160` colors 应用帧。每轮 evidence ZIP 有效，停止使用
`purge=0`，历史保留、QEMU PID 消失、lease 释放。

fixture 使用已锁定的确定 config/data zone、revision `00 00 60 02` 和测试
serial，不包含生产私钥或证书。`RUNTIME-04` 只关闭初始化/identity 和
virtual-device 应用帧门禁；ECDSA 生成/签名、生产 slot/trust root、
side-channel、电气行为和真机仍为独立 `NOT RUN`。样本自身仍因独立 BMI270
错误和未全验的后续 tab 保持 `PARTIAL`，但不阻塞本模型缺口关闭。

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
| 修复进度 | controller-to-physical-bus routing `FIXED`；minimal probe 的 `CCOMPARE == CCOUNT` equal-deadline `FIXED`；TIMG WDT level IRQ 的 `INT_ENA` mask `FIXED`；stateful SSI 批量数据面 `VALIDATED`；统一 handoff timeline `VALIDATED`；`0064` 修复 pending SPI/INTMATRIX remap；`0065` 关闭单线程 TCG slice 导致的 high-priority DPORT handoff deadlock，五轮首启动 `5/5 PASS`；`0066` 补经典 ESP32 RMT，移除 Neopixel translator 初始化失败并让 legacy Serial 到达 `APIKEY`；VFS/WiFi fixture 校正后 `qemu-wifi` 120 秒已执行注入的 `/flash/boot.py`；`0068` 修复 legacy HSPI/SPI2 panel routing；`0069` 修复 protected WDTFEED 语义；`0075` 排除 RDSR WIP/busy 错误并把 pre-BOARD 成本定位到 scheduler/list 跨核锁竞争；`0086` 修正 episode 诊断的 `Bad icount read` 并测得长持有区间；`0088` 证明 100 ms RR 放大 contended CAS，并在 opt-in `1 ms` quantum 下大幅减少 spin，但 WDT reset 不变；原厂 startup UI、normal-WDT reset 和完整应用帧仍 `OPEN` |
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
| VFS/WiFi fixture 校正 | 通用 LittleFS 镜像不被 legacy guest 接受，guest 会重新格式化正确的 `vfs` 分区；改用 UIFlow checkout 自带 `littlefs2` packer 后注入的 `/flash/boot.py` 首次可执行。裸 QEMU 诊断尚未传 `misc.esp32_wifi` NIC，guest 会在 `0x60033d24` 的 `WIFI_DMA_OUT_STATUS` alias 缺少后端状态。`/api/v1` 的 `qemu-wifi` + matching VFS 在 120 秒执行到 `CORE2_LEGACY_VFS_BOOT`，CPU0/CPU1 为 `0x40249c5d/0x400e1ffd`，旧 `0x40100049` late wait 未复现；setup/main 和 nonblack frame 仍 `NOT REACHED`/`FAIL` |
| Dual-SPI panel routing | 公开 legacy `display.TFT` 默认选择 ESP32 HSPI/SPI2，而板级模型只把 panel sink 接到 VSPI/SPI3；负控有 `412` 次 legacy DMA `addr=104` 写落在非面板控制器、面板 `0` 次。`0068` 将同一面板同时接到 SPI2/SPI3（DC15），Device Service `qemu-wifi` 的 legacy `m5stack`/`lcd` probe 得到 `320x240`、`1422` nonblack pixels、`2` colors；Python API 完成不等于原厂 startup UI 完成 |
| Core2 M5UI panel DMA | `0074` 修复 classic ESP32 panel flush 的 DMA descriptor + CPU data-register 双消费。修复前 48 个 `320x10` strip 应写 `6,400` bytes、实际写 `12,736`，20x60 image window 应写 `2,400`、实际写 `4,736`；修复后 54/54 RAMWR window exact。同一 hash-pinned candidate 的 state `4/4` 与 triangle/image `2/2 FRAME_PASS`，最终 frame `5a074d29…`。MADCTL、rotation 和 READY 后延迟三个控制均未消除修复前条带 |
| WDTFEED protection | ESP-IDF v4.4.8 的 `wdt_hal_feed()` 直接写 `TIMG_WDTFEED`，不会先解锁 `WDTPROTECT`；旧模型把 `A_TIMG_WDTFEED` 整体放在保护条件内。`0069` 只把 feed 路径移出保护条件，配置写入仍要求 key。C 合同和 patch reverse-check PASS；同一 legacy 固件 60 秒正常 WDT 仍在 `7.2528 s` stage-0、`17.2528 s` stage-1 reset，因此该修复是模型语义正确性，不是 startup UI 修复 |
| UART virtual-clock alignment | `0070` 在默认关闭的 `M5SW_UART_TRACE` 中记录每个 TX byte 的 `qemu_clock_get_ns(QEMU_CLOCK_VIRTUAL)`；`run_pause_sweep.py` 将字节重组为带起止虚拟时间的完整行。WDT-off 80 秒中 banner `2.77 s`、BOARD/APIKEY `55.00 s`、boot.py `77.11 s`；状态点两核仍运行，SSI `104,061` transactions、cross-core writes `432,918`。normal-WDT `shift=5` 仍在 `17.2529 s` reset，显式 `shift=2` 在更长墙钟窗口中仍于 `15.5609 s` reset 且未到 BOARD NAME；降低 accelerator 不能作为产品修复 |
| pre-boot phase profile | `run_pause_sweep.py` 新增显式 `--pc-sample-ns`、`--uart-trace` 和 `phase_profile`，修复 UART parser 未启用 trace、PC sampling 元数据恒为 `NOT RUN` 的工具缺口。50 ms 采样 1,599 点的 WDT-off 80 秒控制中，CPU0 31.0% 在 `0x4026306e` waiti、60.4% 在 `0x40087980..8e` handoff 簇；SSI 聚合计数为 103,058 transactions / 3,181,984 RX bytes（平均约 30.9 bytes/transaction），最后记录的 command/payload counter 为 `0xBB/64`。verbose trace 采样间隔 1024，只捕获 108 个 transaction-begin（95 个 `0x05` status read、2 个 `0xBB` 64-byte read、10 个 `0x00`、1 个 `0x02`），全量 command/length 分布仍未知。normal-WDT 仍 stage-0 `7.2536 s`、stage-1 reset `17.2536 s`，TG1 live。全部 high-priority memw/retw、CPU1-only、cross-core-write、SPI-TRANS_DONE 立即切核控制都被否定并丢弃；下一项增加 controller 级聚合直方图并定位 guest driver 请求分布 |
| SSI transaction profile | `0071` 在默认关闭的 handoff metrics 中增加完整 16-bit command、RX-length 和 completion→next-command gap 聚合，并在冻结点输出；runner 校验 command/length 总数等于 transaction 数、gap 总数等于 `transaction-1`。关闭 PC sampling 的同 SHA WDT-off 80 秒控制得到 `104,302` transactions，其中 `0x05` RDSR `49,489`、`0xBB` 64-byte Fast Read `49,586`；RX length `1` 为 `53,054`、`64` 为 `49,586`。`104,301` 个 command gap 合计 `79.699109375 s`，分布集中在 `1-10 us`、`100 us-1 ms` 和 `1-10 ms`；PC sampling 开启时分布和计数相近。结果排除“采样漏掉单个超大 controller 传输”的解释，证明主要工作预算位于 guest 两次 command 之间；command-length 联合配对和具体 guest driver 函数仍未定位 |
| SSI command correlation | `0072` 增加 command-length 联合键、按 command 的 gap 和 command transition；三个有界稀疏表均有 overflow。同 SHA 80 秒控制中 `0x05/1` 为 `50,071`、`0xBB/64` 为 `49,882`；主循环 `0xBB→0x05` `49,582`、`0x05→0xBB` `49,600`。`0x05` 前 gap `65.670563678 s`（`82.398%`、平均 `1.3115489 ms`），`0xBB` 前仅 `0.152263360 s`（`0.191%`、平均 `3.05 us`）。联合、per-command 和 transition 总数分别等于 transaction 或 `transaction-1`，overflow 全为 `0`；normal-WDT 仍 `17.249440926 s` reset。当前预算已定位到 64-byte read 后、下一次 status read 前，但具体 guest driver/IRQ 函数仍未命名 |
| SSI command issuer PC | `0073` 增加 command/CPU/transaction-issuer-PC 稀疏表和 overflow；只输出于显式 freeze。同一 frozen QEMU `e2efbc67…` 的 WDT-off 80 秒控制得到 `105,161` transactions，PC 表总数同为 `105,161`、overflow `0`。`0x05` `49,972` 次中 `49,961` 次来自 `0x4006222c`，该地址位于 IDF ESP32 ROM `esp_rom_spiflash_read_user_cmd=0x400621b0` 与 `esp_rom_spiflash_read_status=0x4006226c` 之间；`0xBB/64` `49,783` 次中 `49,452` 次来自应用 segment 5 的 `0x40093b57`（offset `0x167f`）。没有 matching legacy ELF/MAP，不能命名精确应用函数。同 QEMU normal-WDT 仍在 `17.253607230 s` reset，TG1 live、零 timeout |
| Status/CAS correlation | `0075` 在显式 freeze 中记录 `RDSR(0x05)` 状态字节、前序 `0xBB/64`、cache-counter delta、PS/IRQ，以及有界 `s32c1i` PC/caller/lock/old-owner/holder-PC 桶。同 SHA 20 秒 WDT-off 控制中 status 仅出现 `0x00`/`0x02`，bit0 WIP/BUSY 全为 `0`；主要 gap 仍位于下一次 status read 前。CAS 汇总确认 `0x3ffbf2cc` 的跨核锁竞争，而不是 old-owner 值损坏。默认 normal-WDT 与 failed-CAS slice-yield 控制分别在 `17.24849 s`、`17.24893 s` 触发相同 TG0 stage-1 reset，后者被否定为修复。PC 仍是 BIN-bound 地址，未用不匹配 ELF 命名 |
| CAS hold episodes | `0086` 在 `0075` 的默认关闭 handoff trace 上增加按 CPU、lock、attempt 和 duration 聚合的跨核 CAS episode；在 no-I/O TB 中跳过 virtual-clock 采样，避免诊断自身触发 `Bad icount read`，不改变 guest 指令或 CAS 结果。同 SHA 的 normal-WDT/WDT-off 10 秒 freeze 分别得到 `238/253` 个区间；`0x3ffbf2cc` 为 `162/166` 个、累计 `6.743534018/6.600981470 s`、最长 `482.823328/581.176638 ms`。BIN 指令结构与 public ESP-IDF v3.3.5 匹配为 `xTaskQueueMutex`，主要 waiter 是 `xTaskIncrementTick`/`vTaskSwitchContext`；第二个热点 `0x3ffb7ab0` 是某 `Queue_t + 76` 的 mux，但 matching application ELF/MAP 仍缺失。失败 CAS yield 在 10 秒把 task-queue 等待从 `6.601 s` 降到 `0.446 s`，但 15 秒时主要预算转移到 queue mux（`0.825→4.534 s`），总 episode 仍约 `5.4 s`，正常 WDT reset 边界不变。这否定“yield 完全无效”，也证明它只是重分配等待而非完成修复；host-vCPU 调度延迟与实际 guest 长临界区仍待区分 |
| Contended-CAS RR attribution | `0088` 在真实跨核 failed S32C1I 后缩短下一个单线程 RR quantum 到 `1 ms`；默认关闭，guest CAS、lock owner、icount、WDT deadline 和 peripheral path 不变。同 binary 5 秒 WDT-off A/B 将 CAS `1,070,625→91,465`、contended `984,964→2,702`、episode time `2.239772672→1.017736288 s`，CPU0 从 `0x40087986` handoff-spin 簇移到 `0x400951fe`，而 SSI `0x05`/`0xBB` 只差 8。20 秒控制在两 lane SSI 计数相同时仍把 episode time 从 `15.330116502 s` 降到 `10.449083200 s`。`100 us` 未能带来更好的 guest 位置，因此保留 `1 ms`。normal-WDT control/candidate 仍在 `17.249535709/17.248020126 s` 触发同一 TG0 stage-1 reset，说明它是重要调度放大器而不是启动修复 |
| host flush control | 当 `changed_pages == 0` 时跳过 `memory_region_flush_rom_device()` 的探索性修改仍进入 `TG0WDT_SYS_RESET`，reset PC `0` 和黑帧 SHA 不变。该修改未保留为补丁；host-side 整块 flush 不是已测得的根因 |
| 修复后 | `0x34`、`0x51`、INA3221 `0x40` 均 ACK，原 `I2C bus error (19)` 消失；最小 probe 在 trace 开/关和 `shift=5`/`auto` 对照中通过首启动门禁，进入 `CORE2_FLASH_IPC_PASS` |
| 当前阻断 | `0068` 已让 legacy `m5stack`/`lcd` probe 产生 1422 nonblack pixels，但原厂 startup UI 仍没有完成画面；normal-WDT 仍出现 TG0 system reset。剩余问题已从 display controller routing 转为 startup UI 生命周期与 WDT 关系 |
| 当前判断 | `0065` 证明旧固定双 PC deadlock 是 scheduler artifact，`0066` 证明 Neopixel 初始化失败是缺失 classic RMT，VFS/WiFi fixture 校正排除了输入污染，`0068` 证明 legacy HSPI panel 数据面可工作，`0069` 排除了 protected feed 被模型丢弃，`0070` 证明 normal-WDT 的 first failure 早于 BOARD/APIKEY，而 WDT-off 在同一时间点仍有真实 SSI/cache 进度。`0071/0072` 确认 `0xBB→0x05→0xBB` 主循环，主要 gap 位于下一次 `0x05` 前；`0073` 将高频 issuer 绑定到 ROM read-command 区间和应用 segment 5；`0075` 证明 status bit0 始终为 `0`、old-owner 值正常；`0086` 把热锁结构匹配到 `xTaskQueueMutex`/queue mux；`0088` 证明 100 ms RR quantum 会把跨核 spin 放大一个数量级，但 contender-aware `1 ms` quantum 仍不能解除 TG0 stage-1 reset。下一步需结合 matching ELF/MAP、tick/IRQ rate 和启动任务的实际长临界区；不能靠 WDT-off、扩 timeout、缩 VFS、accelerator override 或局部调度 yield 冒充修复 |
| 证据 | [`contended-CAS scheduler`](evidence/2026-10-29-core2-contended-cas-scheduler/README.md)、[`scheduler summary`](evidence/2026-10-29-core2-contended-cas-scheduler/summary.json)、[`0088 patch`](../patches/qemu-m5stack-peripherals/0088-xtensa-contended-cas-fair-yield.patch)、[`0088 contract`](../platform/tests/test_core2_legacy_status_cas.py)、[`CAS hold episodes`](evidence/2026-10-29-core2-legacy-cas-episodes/README.md)、[`episode summary`](evidence/2026-10-29-core2-legacy-cas-episodes/summary.json)、[`0086 patch`](../patches/qemu-m5stack-peripherals/0086-esp32-legacy-cas-episode-profile.patch)、[`status/CAS correlation`](evidence/2026-10-29-core2-legacy-status-cas/README.md)、[`status/CAS summary`](evidence/2026-10-29-core2-legacy-status-cas/summary.json)、[`0075 patch`](../patches/qemu-m5stack-peripherals/0075-esp32-legacy-status-cas-correlation.patch)、[`Core2 M5UI DMA dedup`](evidence/2026-10-29-core2-m5ui-dma-dedup/README.md)、[`M5UI DMA summary`](evidence/2026-10-29-core2-m5ui-dma-dedup/summary.json)、[`0074 patch`](../patches/qemu-m5stack-peripherals/0074-esp32-spi-panel-dma-dedup.patch)、[`SSI command issuer PC`](evidence/2026-10-29-core2-ssi-command-pc/README.md)、[`issuer PC summary`](evidence/2026-10-29-core2-ssi-command-pc/summary.json)、[`0073 patch`](../patches/qemu-m5stack-peripherals/0073-esp32-ssi-command-pc.patch)、[`SSI command correlation`](evidence/2026-10-29-core2-ssi-command-correlation/README.md)、[`SSI transaction profile`](evidence/2026-10-29-core2-ssi-transaction-profile/README.md)、[`0071 patch`](../patches/qemu-m5stack-peripherals/0071-esp32-ssi-transaction-profile.patch)、[`dual-SPI panel routing`](evidence/2026-10-28-core2-dual-spi-panel-routing/README.md)、[`0068 patch`](../patches/qemu-m5stack-peripherals/0068-core2-dual-spi-panel-routing.patch)、[`VFS/WiFi fixture 校正`](evidence/2026-10-28-core2-legacy-vfs-wifi-fixture/README.md)、[`0066 RMT patch`](../patches/qemu-m5stack-peripherals/0066-esp32-classic-rmt-legacy.patch)、[`0065 cooperative patch`](../patches/qemu-m5stack-peripherals/0065-xtensa-high-priority-irq-cooperative-yield.patch)、[`state sweep runner`](../tests/firmware/core2_handoff_trace/run_pause_sweep.py)、[`0037 handoff trace patch`](../patches/qemu-m5stack-peripherals/0037-esp32-handoff-trace.patch) |

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
8. `0071`/`0072` 已建立 controller-level command、RX-length、gap、
   command-length、per-command gap 和 transition 聚合；主循环为
   `0xBB/64 -> 0x05/1 -> 0xBB/64`，主要 gap 位于下一次 `0x05` 前。
   `0073` 已把高频 issuer 绑定到 ROM read-command 区间 `0x4006222c`
   和应用 segment 5 `0x40093b57`。`0075` 已排除 RDSR busy 位并定位到
   scheduler/list 跨核锁竞争；下一步结合 matching symbols、
   tick/IRQ rate 与最长锁持有区间解释该路径；
9. 保持 `0x40100049` 的 BIN-bound 语义：LVGL `lv_refr_vdb_flush`
   双缓冲 wait，`A2+24` 为 `flushing`，`A10+28` 为可空 `wait_cb`；
10. 保持 `0064` 的 pending SPI remap、`TRANS_DONE && TRANS_INTEN` 和
   guest callback 回归；继续解释最新 legacy runtime 为何在 display
   `flush_cb` 之前停止或 reset，直到 completion callback
   `0x40174884` 与 `lv_disp_flush_ready` 可观测；
11. 同一 legacy 固件 SHA 在正常 WDT、真实 SSI/m25p80 数据面下渲染非空
   应用帧并保持运行，不得依赖 WDT 关闭、bulk bypass 或 retry；
12. 回归现有 UIFlow2 Core2 设备组，确保 shared bus 不破坏 touch/IMU/RTC/
   audio/mic 路径；
13. 保持 `0065` 的 level-4/5 handler `memw`/`retw` 协作点和 RFI/reset
   active-state 清理，并继续以零 retry 首启动证明 DPORT handoff 不再固定
   双 PC 死锁；
14. 保持 `0066` 的 classic RMT 寄存器、`mem_size`、RMTMEM、threshold、
   `TX_END` 和有界 capture 契约；RMT 初始化通过不能替代 GPIO waveform、
   Neopixel 光学或 legacy 应用帧 PASS；
15. 在同一 final runtime 上给出 `APIKEY` 之后的首个未完成 guest/controller
   路径，并在 normal-WDT 下完成 setup/REPL、非空应用帧和稳定运行。

当前调查边界：shared bus、equal-deadline timer、WDT mask、stateful SSI、
统一 timeline、pending SPI remap、high-priority IRQ 协作和 classic RMT
都已形成可重放控制。`0065` 关闭调度诱导 DPORT deadlock，`0066` 关闭
Neopixel RMT translator 初始化失败；最终 WDT-off 控制到达 `APIKEY` 后仍是
302-byte 黑帧。normal-WDT 的 TG0 stage-1 reset、display completion、
setup/REPL、non-empty frame 与稳定运行仍为 `FAIL`。matching ELF/MAP 缺失时
不得从不同版本固件借用符号；`Core2FactoryTest` 修复后仍未重跑。

### RUNTIME-06：ESP-NOW virtual-controller 功能边界已闭环

| 字段 | 当前值 |
| --- | --- |
| 状态 | `FIXED`（virtual-device validation） |
| 影响 | 原厂 `espnow.ESPNow`、`ESPNowBase`、`m5espnow.M5ESPNow` 的 payload、receive、IRQ、independent-guest plaintext/CCMP/replay、stock guest key-state/rotation、native/wrapper lifecycle、三 guest shared-LMK fabric、pairwise-LMK routing、PN 耗尽 fail-closed、受控 loss/retry、channel 门禁、rate metadata 和 60 秒双向 soak；物理 RF/controller 等价性不属于该 `FIXED` 结论 |
| 当前模型 | `0067` 提供同 guest controller loopback；`0076` 用显式配对的 IPv4 loopback UDP 端口连接两个独立 controller；`0077` 在 bridge 边界执行真实 AES-CCMP/MIC；`0078` 拒绝 duplicate PN；`0079` 提供单 peer 64-frame authenticated replay window；`0080` 映射 classic ESP32/S3 controller key store；`0081` 组成三 guest fabric；`0082` 按 stock key-entry peer MAC 选择 per-peer LMK；`0083` 禁止 48-bit TX PN 回绕；`0084` 在真实 action frame 外加 8-byte channel/rate envelope，RX 在 CCMP/DMA 前校验 channel/rate，并把被交付 frame 的 envelope channel/rate 写入 controller RX metadata。该 envelope 是受信测试 fixture、位于 CCMP 外，不作为 authenticated security field。Python host 不合成 key、payload、MIC 或 callback |
| 已验证 | controller loopback、independent-guest plaintext、CCMP 正负控、duplicate drop、64-frame reorder、native add/delete/modify、M5ESPNow wrapper add/delete/re-add、guest key-state/key rotation、三 guest shared-LMK fabric、pairwise-LMK 六方向 payload、B/A cross-wire、PN 耗尽正控、same-LMK stale-rekey 负控、受控两帧丢失后的应用重试、channel 6 正控、channel 1↔6 双向拒绝、11/24 Mbps 混合 metadata 和 60 秒双向 soak 均已通过 |
| 未覆盖 | bit-exact controller/baseband、RF propagation、天线、实测 channel/rate、电气时序和 physical hardware |
| 证据 | [`loss/channel/rate 证据`](evidence/2026-10-29-espnow-loss-channel-rate/README.md)、[`0084 patch`](../patches/qemu-m5stack-peripherals/0084-esp32-espnow-loss-channel-rate.patch)、[`PN exhaustion 证据`](evidence/2026-10-29-espnow-ccmp-pn-exhaustion/README.md)、[`0083 patch`](../patches/qemu-m5stack-peripherals/0083-esp32-espnow-ccmp-pn-exhaustion.patch)、[`per-peer key 证据`](evidence/2026-10-29-espnow-per-peer-key-routing/README.md)、[`0082 patch`](../patches/qemu-m5stack-peripherals/0082-esp32-espnow-per-peer-key-routing.patch)、[`peer fabric 证据`](evidence/2026-10-29-espnow-peer-fabric/README.md)、[`0081 patch`](../patches/qemu-m5stack-peripherals/0081-esp32-espnow-peer-fabric.patch)、[`guest key-state 证据`](evidence/2026-10-29-espnow-guest-key-state/README.md)、[`replay-window 证据`](evidence/2026-10-29-espnow-external-ccmp-window/README.md)、[`native lifecycle 证据`](evidence/2026-10-29-espnow-peer-lifecycle/README.md)、[`M5ESPNow lifecycle 证据`](evidence/2026-10-29-espnow-m5espnow-lifecycle/README.md)、[`lifecycle/fabric runner`](../tests/uiflow2/api_sweep/run_espnow_pair.py) |

关闭条件：

1. loss/retry、channel/rate 和更完整长稳生命周期可重放（`0084` 已满足）；
2. loopback、external plaintext、env-key fixture、shared-LMK/per-peer-key fabric、cross-wire 和 PN exhaustion 负控分开记录，不能互相替代；
3. 物理 RF/controller 等价性另行验证，不从 QEMU 结果推论；该独立边界不阻塞当前 virtual-device `FIXED` 状态。

## 与固件矩阵的关系

跨厂商矩阵的状态语义由
[热门用户固件矩阵](user-firmware-simulation-matrix.md)定义。S3/C6 的
18 样本历史快照中有两个缺口进入本页，其中一个现已关闭；当前合并后的
21 个公开非基线样本还纳入了 Core2 PMIC/AWS 历史缺口；AWS ATECC608
初始化缺口已单独关闭，但该 firmware 仍保持 `PARTIAL`。它们绑定当时的 artifact
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

## 浏览器固定示例的输入边界（2026-10-29）

这些限制由 `UI-02` 继续跟踪，不属于原生设备或物理硬件 PASS：

- PaperMono 的固定 UIFlow2 v2.5.3 基底在 portrait 原始点 `(240,650)` 上，
  stock `M5.Touch.getX/getY` 实际返回 `(90,400)`。浏览器示例经官方
  `getTouchPointRaw(0)` 和原 FT/I2C 路径做命中，并保留逻辑坐标和释放缓存
  标记；这不是 frozen SDK 校准修复。SDK offset 候选只有源码/host C++ 控制，
  未构建执行对应固件，不授予其 PASS。
- StopWatch 的 SDK 逻辑尺寸为 468²、当前 QEMU 面板为 466²；圆内显示标记
  可完整观察，但原始触摸 `(233,233)` 到 guest 逻辑 `(239,239)` 的校准偏差
  仍开放。显示和触摸不能由相同芯片名称推定为逐坐标精确。
- Cardputer-ADV 的固定示例通过原 KeyboardI2C 的 FIFO/ASCII decoder 轮询
  确认按下和释放。`0016` 是明确物理矩阵映射；`0018` 只修 TI SCPS215G
  规定的默认 `INT_CFG=0` 锁存/W1C 语义。`INT_CFG=1` 的 50 µs 脉冲、
  `KEY_IEN` 门控、其它中断源、自动 GPIO IRQ 交付和一般 modifier/chord
  应用仍需各自执行证据，不能从该固定轮询路径继承。

固定源码、官方 API/数据手册来源和范围见
[逐板浏览器 fixture](../tests/browser-qemu/board_display/README.md) 与
[QEMU WASM 补丁](../patches/qemu-wasm-probe/README.md)。

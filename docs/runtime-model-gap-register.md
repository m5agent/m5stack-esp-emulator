# 运行时模型缺口登记

日期：`2026-10-24`

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

## 与固件矩阵的关系

跨厂商矩阵的状态语义由
[热门用户固件矩阵](user-firmware-simulation-matrix.md)定义。当前 18 个公开
样本的历史快照中有两个缺口进入本页，其中一个现已关闭；其余 `PARTIAL`
仍按首帧、输入、串口生命周期或
仅串口设备等独立原因记录，不能因为页面放在同一个矩阵中就合并为模型缺陷。

新增 `runtime_model_gap` 时必须同时：

1. 在 evidence 中保留 bounded serial/error、firmware SHA、profile 和检查项；
2. 在本页增加受影响的控制器/复位域、已知边界和关闭条件；
3. 在 Backlog 建立 Task ID；
4. 修复后用新 evidence 关闭任务，旧诊断 evidence 不得静默改写。

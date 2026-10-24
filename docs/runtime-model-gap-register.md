# 运行时模型缺口登记

日期：`2026-10-24`

本文是“固件行为与模拟器模型不一致”时的统一登记页。它只记录已经复现、
仍未关闭的运行时能力缺口、证据、责任边界和验收条件；当前总体能力见
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

## 当前缺口

### RUNTIME-01：C6 软件复位后 chip-id 错误

| 字段 | 当前值 |
| --- | --- |
| 状态 | `OPEN` |
| 影响 | ESP32-C6 QEMU 软件复位生命周期；目前已由一个 Nesso N1 社区固件稳定触发 |
| 首次路径 | 固件进入 C6 ROM/application，随后执行 `LP_SW_HPSYS` 软件复位 |
| 复位后现象 | ROM 报 `Invalid chip id. Expected 13 read 12. Bootloader for wrong chip?` |
| 样本 | M5Burner `1897200000000001757`，`Meshtastic unofficial` |
| 固件 SHA-256 | `ef8249ac7930fa51ac5bf03cea52d8de9a59dcbaf2130663ca0d5087a8053744` |
| 证据 | [`cross-vendor-runtime-model-gaps.json`](../tests/firmware/evidence-2026-10-24-cross-vendor-runtime-model-gaps.json) |

已知边界：

- 首次启动已经进入 C6 ROM/application，不是镜像格式或 Flash 地址错误；
- `read 12` 的具体 ROM/eFuse/寄存器来源尚未定位，不能仅凭数字猜测 efuse 位；
- 还没有证明所有 C6 软件复位都受影响，因此当前证据只绑定该 firmware SHA、
  Nesso N1 profile 和对应 QEMU build；
- 不允许通过 Python/QOM 在每次 ROM 读取时返回假 chip id 来“修复”。

关闭条件：

1. 从 ESP-IDF/ROM 路径确认 `expected 13/read 12` 的实际读取来源；
2. 修正 C6 reset domain、eFuse backing、strap 或寄存器保留语义中的真实缺陷；
3. 同一 firmware SHA 重跑后不再出现 `Invalid chip id`，并保留 serial、frame、
   input、runtime/profile 和 QEMU build 证据；
4. NanoC6/Nesso N1 的其他 C6 unified 用例不回归；
5. 结果标记为 `virtual-device validation`，不扩展为 RF 或真机结论。

### RUNTIME-02：C6 Zigbee/802.15.4 运行时未建模

| 字段 | 当前值 |
| --- | --- |
| 状态 | `OPEN` |
| 影响 | NanoC6 及后续依赖 ESP32-C6 IEEE 802.15.4/Zigbee 控制器的固件 |
| 现象 | `Zigbee_main` 阻塞并触发 task watchdog；当前 C6 profile 没有对应 radio/controller 数据面 |
| 证据 | [`cross-vendor-runtime-model-gaps.json`](../tests/firmware/evidence-2026-10-24-cross-vendor-runtime-model-gaps.json) |

关闭条件：

1. 明确 Espressif C6 802.15.4 MAC/基带、DMA、中断和固件驱动路径；
2. 通过真实 guest 驱动和控制器接口建模，不在应用或 Python 层伪造
   `Zigbee_main` 状态；
3. 至少覆盖一个加入/收发/离网生命周期，或明确把不支持路径继续返回为
   `runtime_model_gap`；
4. 与 WiFi/BLE 共存的结论单独记录，不能由单次 Zigbee 启动推断。

如果无法取得可执行的控制器权威语义，该项目保持显式不支持，而不是承诺
“所有 C6 固件均可运行”。

## 与固件矩阵的关系

跨厂商矩阵的状态语义由
[热门用户固件矩阵](user-firmware-simulation-matrix.md)定义。当前 18 个公开
样本中有两个缺口进入本页；其余 `PARTIAL` 仍按首帧、输入、串口生命周期或
仅串口设备等独立原因记录，不能因为页面放在同一个矩阵中就合并为模型缺陷。

新增 `runtime_model_gap` 时必须同时：

1. 在 evidence 中保留 bounded serial/error、firmware SHA、profile 和检查项；
2. 在本页增加受影响的控制器/复位域、已知边界和关闭条件；
3. 在 Backlog 建立 Task ID；
4. 修复后用新 evidence 关闭任务，旧诊断 evidence 不得静默改写。

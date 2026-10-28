# 2026-10-29：Core2 UIFlow2 `m5ble` 候选修复与 BLE teardown 收口

## 结论

Core2 当前原厂 UIFlow2 `v2.5.3` 的 `m5ble-server` 路径稳定复现：

- `21 PASS + 1 ERROR`；
- 唯一失败为 `m5ble.m5ble.Server.get_client(0)`；
- 异常为 `TypeError("'set' object isn't subscriptable")`。

根因是 `Server._connected_devices` 为 `set`，但公开
`get_client(index)` 直接对它执行下标访问。hash-pinned 候选源码先按
`connect_handle` 排序，再应用零基索引；最终两轮并发 Core2 session 均为
`22/22 PASS`，`get_client(0)` 返回回调中同一个真实连接对象。

全部为 **virtual-device validation**。stock 固件失败保留，候选源码
override 不表示原厂冻结固件已经修复。

## 候选身份

| 项目 | 值 |
| --- | --- |
| 官方源码 commit | `db526eccc003335a89c3237112fcf2d1eb2d0904` |
| 源文件 | `m5stack/libs/m5ble/m5ble.py` |
| preimage SHA256 | `18c449e6be47b1d311ffeb4320809d02d01a73e0af11630728c56a19d00ce180` |
| dependency | `ble-uuid32`, patch SHA256 `8ec1f14f42702cc38b9c15975c300cad833aa32a64cb0598e420b5f1e392e15c` |
| candidate SHA256 | `d82c1aec593de997d2d63f6bc409f6786a3b90e8b4b793c722cb9c61b8c82703` |
| patch SHA256 | `2eb188e55907121204fca732cecbdb3dc8e0878a09191b2e093b477169ea11d7` |
| base firmware SHA256 | `b228c0e2d877e77a8a352e917ed84f4da8ea92d15b25e28f431a2999620fe3c4` |
| matching ELF SHA256 | `5bec056bb775bcc94bc020e4fa411def097ea17b108dcd597d9cdab3c347db49` |
| QEMU SHA256 | `9bf74439ddbe7225a64eb437290043729fb032525756adb834565ec412f8c197` |
| runtime/profile | `qemu-unified` / `core2-native-hci`, `icount shift=5` |

## 最终两轮并发执行

| Run | Guest 结果 | Session | Guest firmware SHA256 | Evidence ZIP SHA256 | Peer log SHA256 |
| --- | ---: | --- | --- | --- | --- |
| 1 | `22/22 PASS` | `25c17a963cf74d5a9db6f7e67f0c03da` | `ed4202801720bdcdff3a6055de9e8ba177b6930455b48903cff141cae5e79724` | `8594a6cbd6f89d1d404c2533c9e79bece28f0b5791314ac35fff5b0da23f339e` | `d81c6ae694269e71c92e852c21af167265ad3da1c268b984b4ac3d86a8e9e9d9` |
| 2 | `22/22 PASS` | `f7fd68a2115e44c59dd08fb10f6b59fe` | `52440b0c15cbc76fc639780c0ca4075898e348780758a13758a65444ce2cb6b4` | `33cd2e073e97183b5596dc0e685060c643e708836093f6a43ddcdd7b486b81c4` | `69b2c272e531582982a63eee88c064ae9c95f00bc813195f0294259bff18001e` |

两轮 serial SHA256 分别为
`c082d1696b50ad8104c1c77ba8e24f7c9e7de76e6e535a1498e63ac6d9433690`
和 `0e328dbdcb0f110b985321b94cbffd0ea51b424cdf6eb96f0207b2c03117d435`；
最后一帧 SHA256 均为
`57580743a08a3f4ebdf57240cbcc997002ef63b7234531f946127f1495973f43`。

两次 peer 日志均实际观察到：

- advertisement `M5-CORE2-UNIFIED`；
- NUS service `6e400001-b5a3-f393-e0a9-e50e24dcca9e`；
- TX characteristic subscription `6e400003-b5a3-f393-e0a9-e50e24dcca9e`；
- central write `M5_CORE2_UNIFIED`；
- notification `ACK:M5_CORE2_UNIFIED`。

候选报告明确标记 `library_lane=candidate-source`、
`firmware_lane=stock-frozen` 和
`stock_firmware_result_unchanged=true`。两个 session 都先取得 evidence
ZIP，再以 `purge=0` 停止；runtime PID 与 BLE companion 均已退出。

## Teardown 并发问题

在 M5UI 矩阵同时运行时，GATT 和精确 ACK 已经完成，但 500 ms 内的紧接
`deinit()` 曾出现两次停住：

- stock `bleuart.BLEUARTServer.deinit`：`7 PASS + 1 TIMED_OUT`；
- 单补丁 `m5ble.Device.deinit`：`21 PASS + 1 TIMED_OUT`。

QEMU HCI trace 显示 disconnect 后 library 又排队 advertising restart，
随后 `active(False)` 进入 teardown。协议 probe 现在在显式断连后等待
`2000 ms`，让 GATT disconnect、自动重广告停止和 BLE task 的后续状态
完成，再调用 `deinit()`。修正后的两轮 stock `ble-nus` 均 `8/8 PASS`，
两轮最终 candidate `m5ble-server` 均 `22/22 PASS`，且都与同一 Core2
M5UI 矩阵并发执行。该 settle 只解决测试时序竞争，不声称任意调用方式下
`active(False)` 都有有界完成时间。

## 首次诊断

第一次候选运行在进入 API 前报 `KeyError: M5BLE`。原因是测试注入层把
官方模块源码当作包含 `M5BLE` 符号的单文件模块加载，而该文件实际定义
模块级 `Device`、`Server` 和 `Client`，包入口才把模块别名为 `M5BLE`。
该轮保留为测试夹具诊断，不计入候选功能结果。后续又发现同一
`m5ble.py` 叠加 UUID32 decoder 修正才形成可交付候选；早先只应用
`0025` 的 `4efd584a…` 两轮结果保留为单补丁诊断，不替代最终
`d82c1aec…` 的两轮结果。

## 复现

```bash
PYTHONPATH=platform/tools:.work/py312 python3.12 \
  tests/uiflow2/api_sweep/prepare_uiflow_library_candidates.py \
  --candidate m5ble-server-client-index \
  --source-root <pinned-uiflow-checkout> \
  --out-dir <candidate-output>

PYTHONPATH=.work/py312 python3.12 \
  tests/uiflow2/api_sweep/run_protocols.py \
  --execute --api <isolated-device-service> \
  --group m5ble-server --device core2 \
  --m5ble-source <candidate-output>/candidate_m5ble.py \
  --core2-elf <matching-uiflow-elf> \
  --token-file <private-token-file> \
  --out-dir <fresh-run-directory> --timeout 240
```

## 边界

- 只覆盖 Core2 当前 stock base、matching ELF、QEMU 和 native-HCI profile。
- 不把结果继承给 StopWatch/StickS3 stock internal-controller BLE。
- 未验证 BLE pairing/security、RF、天线、共存、controller bit-exact、
  物理时序或真机。
- 原始 ZIP、串口、frame、pcap 和候选源码只保留在 ignored `.work/`；
  本页只保留哈希、计数、有限 session 标识和复现命令。

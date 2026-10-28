# 2026-10-29：Core2 stock UIFlow2 BLE NUS via native HCI

## 结论

此前三设备全接口复测把 Core2 stock BLE 送入 `core2-unified`，未提供
`core2-native-hci` 所需的 matching ELF，随后在
`UNIFIED_CORE2_IO_CONFIG_READY` 前超时。该结果被记录为 stock GATT
`BLOCKED_MODEL`，但 control plane 使用的是错误 profile。

当前 `run_protocols.py` 对 Core2 BLE groups：

- 使用 `core2-native-hci`；
- 显式上传 matching Core2 UIFlow2 ELF；
- 要求 `--core2-elf`，缺失时 fail closed；
- 以同一条 peer log 中的 connected、GATT discovery、subscription、
  exact peer write 和 exact ACK notification 作为数据面 oracle。

同一 stock `UIFlow2 v2.5.3` base 在 QEMU
`9bf74439ddbe7225a64eb437290043729fb032525756adb834565ec412f8c197`
上完成三个独立 Core2 `ble-nus` session，每个均 `8/8 PASS`。

## 数据面证据

每个 session 的 peer 日志都包含：

- advertisement name `M5-CORE2-UNIFIED`；
- BLE connection；
- NUS service `6e400001-b5a3-f393-e0a9-e50e24dcca9e`；
- TX characteristic subscription `6e400003-b5a3-f393-e0a9-e50e24dcca9e`；
- peer write `M5_CORE2_UNIFIED`；
- exact notification `ACK:M5_CORE2_UNIFIED`。

guest 同时报告 BLEUARTServer `any/read/readline/irq`、close 和 deinit
PASS。三个 session 均取得 evidence ZIP，runtime PID gone，history
preserved。

| Run | Result | Evidence ZIP SHA256 | Peer log SHA256 |
| --- | ---: | --- | --- |
| 1 | `8/8 PASS` | `8bce94370d3be9a433dea55b785a0070540f65aac10ac9385bcf3f102d38faa1` | `6f1cdd792ce08b71862dad1de2d4478682afaa445c50ad52970b9f7cb4d31f6c` |
| 2 | `8/8 PASS` | `a35f1fd7ebfce401ead664a38ff761715cb0f9a5bf776bf842646d100811e060` | `f9fcf6e2c04a42ba97b5dd97e73f8bfe28b995c1dc09c17333fb8eddbed6dc66` |
| 3 | `8/8 PASS` | `66122c83ba2318e4697d1ccb7bbdc9f0019d0d7c995e94eacc50454d8dfb4a36` | `0625ab754a1567aaf412e3fac796c7f8d1dc139fb33565d4e7315853b7fe8754` |

## 身份

| 项目 | 值 |
| --- | --- |
| Base firmware SHA256 | `b228c0e2d877e77a8a352e917ed84f4da8ea92d15b25e28f431a2999620fe3c4` |
| Matching ELF SHA256 | `5bec056bb775bcc94bc020e4fa411def097ea17b108dcd597d9cdab3c347db49` |
| ELF size | `50,143,184` bytes |
| QEMU SHA256 | `9bf74439ddbe7225a64eb437290043729fb032525756adb834565ec412f8c197` |
| Runtime | `qemu-unified`, `profile=core2-native-hci`, `icount shift=5` |
| Hardware validation | `NOT RUN` |

## 仍开放

- StopWatch/StickS3 stock images still use their internal controller; the
  Core2 native-HCI result does not transfer to their `uiflow2-*-unified`
  profiles.
- Core2 `m5ble-server` completed `21 PASS`; one stock API call,
  `m5ble.m5ble.Server.get_client(index)`, raises
  `TypeError("'set' object isn't subscriptable")`. This is retained as a
  stock SDK/API defect, not hidden as a controller success.
- BLE RF, antenna, pairing/security, coexistence, timing and physical
  hardware remain `NOT RUN`.

全部为 virtual-device validation。Core2 结论只适用于所列 stock base、
matching ELF、QEMU SHA 和 `core2-native-hci` profile。

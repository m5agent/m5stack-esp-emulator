# Core2 concurrent capacity boundary

日期：`2026-10-30`

结论：`virtual-device validation`，状态 `BOUNDARY_CONFIRMED`。Core2
单设备并发默认上限保持 `8`，不提升到 `9`。九实例并非绝对不可启动：
三次独立零错峰尝试中有两次 `9/9 PASS`，但第三次出现 `8/9`，且失败 lease
在 NimBLE `ble_hs_hci_process_ack` 中 `LoadProhibited`。单次 panic 足以
拒绝把九实例写入产品默认容量。

## 九实例边界

- 失败 control 的最大真实并发仍是 9，说明 9 个 QEMU 和 lease 已实际建立；
  失败发生在 guest BLE 启动，而不是容量预检提前拒绝。
- 首个 panic PC 为 `0x402630cc`，matching ELF 符号化为
  `ble_hs_hci_process_ack`；随后 `0x40092e43` 是复位后的次生故障。
- 失败前已经观察到 boot、display、WiFi、controlled HTTP、公网 DNS/HTTP
  和 PSRAM 初始化；`peer_gatt_timeout=false`，不是 Bumble peer 超时。
- 两次 `9/9 PASS` 和一次 `8/9 FAIL` 的原始 evidence SHA256 均记录在
  `summary.json`。两次通过不能覆盖一次可重放的 guest panic。

因此 `MAX_CONCURRENCY` 与 `DEFAULT_MAX_PER_DEVICE` 均保持 `8`，并增加
`validate_concurrency(9)` fail-closed 契约测试。

## 当前运行时的重检恢复

当前固定 QEMU/runtime 下，120 秒窗口的网络重检曾因宿主短时拥塞出现单次
`OSError(118)` 或 `OSError(-202)`。修改后：

- controlled HTTP 和公网 HTTP 每次最多尝试 3 次，间隔 1 秒；
- socket timeout 分别提高到 20 秒和 25 秒；
- 最终仍必须满足累计成功次数，不能靠一次失败直接跳过；
- PSRAM pattern error 与可恢复 network recheck error 分开记录；
- extended GATT request/notification timeout 为 45 秒；
- 当前 120 秒持续压力 floor 为 3 次 1 MiB sweep、2 次 heartbeat、
  2 次 HTTP 和 2 次公网重检。

当前最终 tool hash 下的两批独立零错峰 `2×60s` 均为 `2/2 PASS`，合计
`4/4`。每个 lease 完成 1 MiB PSRAM 的三次连续读回、两次 HTTP/公网重检、
WiFi、外部 NUS GATT、frame、32 节点 QOM、pcap、evidence 和 cleanup；
HLI `45/45`，errors/prealloc-failures/panic/GATT timeout 均为 0。

两批原始 evidence：

- A：SHA256 `dfd80cead1f73cdd94f8ccee8f79322e3c55105945637e08c01bece47b2ba146`
- B：SHA256 `1a65e9612473ffa79c7df4c76fa5900168271293721c77cd1387aac269d0e382`

## 未关闭

- 当前宿主高负载时，零错峰八实例冷启动重新绑定不稳定：部分批次的所有
  guest 均已输出 `UNIFIED_CORE2_READY`，但 BLE server 初始化出现
  `OSError(116)`；单实例和两实例 control 仍正常。不能把该宿主状态写成
  八实例功能 FAIL，也不能据此宣布八实例 PASS。
- 九实例容量仍显式拒绝，不能由两次通过反推为可生产默认值。
- 全部结果为虚拟设备验证，不代表物理 PSRAM/cache timing、bit-exact BT
  controller/baseband、RF 或真机。

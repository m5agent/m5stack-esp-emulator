# 2026-11-24 便携 review-sta 网络审查与控制固件

对应 [#238](https://github.com/m5agent/m5stack-esp-emulator/issues/238)。新增
`runtime=qemu-wifi` 的 `network.profile=review-sta`：同一 guest 的 Wi-Fi NIC 接到
每会话 UNIX socketpair，对端在进程内只为 `10.0.2.2` 应答 ARP、DHCP、DNS、HTTP、
TCP、UDP 和 MQTT，不打开任何 IP socket。该路径不需要 Linux 网络命名空间、root、
nftables 或 iproute2，在 macOS 工作节点上直接可用。

## 结果

在独立 Device Service（代理自有端口、独立状态目录与令牌）上，用同一份常驻原生
QEMU `04abc3ba…` 跑了 8 款板卡的控制固件，`32/32` 与预期一致：

| 板卡 | known-good | known-bad（错误 WPA2 密码） | offline | setup-required（按住 B） | 不输入对照 |
| --- | --- | --- | --- | --- | --- |
| Cardputer / Cardputer ADV | PASS | FAIL `wifi_auth_failed` | NOT_USED | 无 B 键 | 无 |
| StickS3 / StopWatch / PaperDIY | PASS | FAIL `wifi_auth_failed` | NOT_USED | PASS | PARTIAL |
| PaperS3 | PASS | FAIL `wifi_auth_failed` | NOT_USED | 无 B 键 | 无 |
| Core2 | PASS | FAIL `wifi_auth_failed` | NOT_USED | NOT RUN（B 是触摸条） | 无 |
| StickC Plus2 | PASS | FAIL `wifi_auth_failed` | NOT_USED | PASS | PARTIAL |

- known-good 断言链：控制器 WPA2 握手、DHCP、DNS A、HTTP GET 与 POST、原始 TCP、
  UDP、MQTT CONNECT 与 PUBLISH 全部 PASS，`data_plane=PASS`。
- known-bad：控制器跟踪 `EAPOL 2/4 MIC mismatch`，无 DHCP 租约，判 `FAIL`。
- setup-required：同一 guest 在串口标记出现后经 `/input` 路径按住 B 两秒，固件随后
  联网并完成 HTTP GET，判 `PASS`；同一镜像不输入时判 `PARTIAL`
  （`no_network_activity`）。
- offline：镜像不含 Wi-Fi 栈，窗口内无网络尝试，判 `NOT_USED`。
- 每个会话的最终 pcap 只含租约地址与 `10.0.2.2` 之间的流量，`non_fixture_addresses`
  为空；对端在停止后 `released=true`，会话以 `purge=0` 停止。

判定只来自对端事件、控制器 WPA 跟踪和 pcap，不读取固件串口文字。

## 早期失败（保留）

- `matrix1`：同一批镜像，Core2 与 StickC Plus2 的 good/setup 判 `FAIL fixture_rejected`，
  bad 判 `PARTIAL`。数据面断言全部通过，原因是经典 NIC 未开启共享 WPA 跟踪，
  `wifi_auth` 缺少控制器证据。为 review-sta 的经典 NIC 开启后，`matrix2` 全部重跑。
- `probe1`：StickS3 setup 在串口标记之后、按键之前因事件字段名冲突抛出 `TypeError`，
  判 `PARTIAL`。已修复并加回归测试。
- `smoke1`：首次 Cardputer good 运行的夹具路径与控制固件约定不一致，判 `FAIL`；
  运行器夹具已按 `review_contract.h` 对齐。

## 范围

- 这是 virtual-device validation，不涉及 RF、功耗、物理硬件或 browser-WASM。
- 未覆盖 WPA3、企业认证、对真实服务的 TLS 和任意公网。
- 审查服务侧的 11 条 `E_NETWORK_PARTIAL` 任务重跑为 `NOT RUN`，需要审查服务改为
  使用 `review-sta`。
- Tab5 报告 `network=unsupported`，当前没有 review-sta 模型。

完整身份、逐例断言、镜像与 pcap 哈希见 [summary.json](summary.json)。控制固件源码与
运行方法见 [tests/network/review_sta_controls](../../../tests/network/review_sta_controls/README.md)。

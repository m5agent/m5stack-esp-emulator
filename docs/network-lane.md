# 网络诊断 lane

日期：`2026-10-23`

## 定位

`platform/tools/network_lane.py` 是基于 `esp-emu` 的独立诊断 lane。它适合：

- 尚未迁移到 QEMU unified profile 的固件；
- WiFi/BLE 启动 blocker 分类；
- 固件自建 SoftAP 和 provisioning portal；
- DNS、TCP、UDP、HCI 或异常网络行为排查。

它不是完整设备验收路径。network session 不提供板级 framebuffer、input、
QOM 或同一个 guest 的设备状态。完整设备结论应使用
`runtime=qemu-unified` 和 [统一设备运行时契约](unified-device-runtime.md)。

当前设备状态见 [项目当前状态](project-status.md)，未完成项见
[项目 Backlog](project-backlog.md)。

## 运行方式

通用诊断：

```bash
PYTHONPATH=.work/py python3 platform/tools/network_lane.py \
  --profile generic-observe \
  --chip esp32s3 \
  --firmware /path/to/firmware.bin \
  --timeout 120 \
  --out-dir /tmp/m5-network-diagnostic
```

错误密码负向用例：

```bash
PYTHONPATH=.work/py python3 platform/tools/network_lane.py \
  --profile esp-idf-wrong-password \
  --chip esp32s3 \
  --firmware /path/to/http_throughput.bin \
  --password '<wrong-password>' \
  --timeout 35 \
  --out-dir /tmp/m5-network-wrong-password
```

该 profile 只有在认证尝试、错误密码拒绝、至少一次重试、无 DHCP、无 HTTP
进度和最终失败标记全部成立时才 PASS；“连不上”单独不算通过。

固件自建 SoftAP 和 provisioning portal：

```bash
PYTHONPATH=.work/py python3 platform/tools/network_lane.py \
  --profile generic-observe \
  --chip esp32s3 \
  --firmware /path/to/provisioning.bin \
  --firmware-ap-password '<firmware-ap-password>' \
  --hostfwd tcp:127.0.0.1:18080-:80 \
  --timeout 120 \
  --out-dir /tmp/m5-softap-provisioning
```

上述命令中的密码和端口仅为格式示例。不要把真实凭据写入仓库或公开记录。

Device Service 使用同一能力：

```json
{
  "device_id": "sticks3",
  "firmware_id": "<firmware-id>",
  "runtime": "network",
  "network": {
    "profile": "generic-observe",
    "timeout_seconds": 120,
    "expected_markers": ["PROVISIONING_READY"],
    "firmware_ap_password": "<firmware-ap-password>",
    "hostfwd": [
      {
        "protocol": "tcp",
        "host_port": 18080,
        "guest_port": 80
      }
    ]
  }
}
```

`hostfwd` 的 host address 固定为 loopback，最多 8 条。TCP 可到达固件
SoftAP 门户；UDP 当前只覆盖 station path。实际接口与错误码见
[Device Service API](device-service-api.md)。

## 已验证范围

- StickS3/CoreS3 及 C6 的 scan、association、DHCP、DNS、TCP/UDP；
- 受控 HTTP 下载；
- UIFlow2 `BLEUARTServer` 和 ESP-IDF coexistence 的 HCI/外部 GATT；
- 固件 self-SoftAP 的 join 与 loopback portal 转发；
- 基于日志、配置和 marker 的启动 blocker 诊断。
- 错误密码的认证拒绝、重试、无 DHCP/HTTP 负向证据；
- QEMU unified 会话的 pcap 流/DNS/DHCP 摘要；
- StickS3 guest WLAN 主动断开叠加 QMP `wifi0` link-down/up 后的重新 DHCP
  和前后两次受控 HTTP。

S3/C6 的完整设备路径另外已经在 QEMU unified profile 中完成，不依赖本
lane 的 framebuffer/板级结果拼接。

## 证据边界

PASS 只证明本次运行时列出的数据面。它不证明：

- 真机 RF、天线、距离、功耗或干扰；
- 稳定访问任意公网服务；
- TLS 证书固定或云端业务正确；
- WPA3-SAE-only、hidden SSID 或所有安全模式；
- Bluedroid、Classic Bluetooth 或任意手机互通；
- 固件安全、租户隔离或恶意行为不存在。

`user,restrict=yes` 和 loopback `hostfwd` 不是恶意固件沙箱。不可信固件需要
disposable VM 或独立 network namespace，并阻断 workstation LAN、host
filesystem、cloud metadata 和内部服务。

Linux worker 可以使用 `network.policy.isolation=namespace`。隔离 runner
先创建 private network namespace，并拒绝存在外部路由；无法创建 namespace 时
拒绝启动。受控 HTTP/BLE peer 在同一个 namespace 内运行，默认没有外网路由。
Linux arm64 已用同一 QEMU 源码重建运行时，并在 private namespace 内实跑
StickS3 guest：受控 `/unified` HTTP PASS，公网 DNS 查询无响应，pcap 中没有
global/slirp-redirect 目标。宿主 macOS 仍不直接执行该隔离路径。

`esp-emu` 的 `user` 网络不提供 Ethernet pcap；`network.capture_pcap=true`
会明确拒绝。pcap 证据应使用 QEMU radio runtime，随后由
`platform/tools/pcap_summary.py` 生成 flow、DNS、DHCP、ARP、egress scope
和 payload hash 摘要，不保存 payload 明文。

## 什么时候改用 QEMU unified

以下场景不应继续使用 network-only lane：

- 需要同一 guest 的显示、输入、音频、摄像头或板级外设证据；
- 需要单 lease 的完整设备 PASS；
- 需要把网络行为与 QOM、设备状态或 USB/I2C/SPI 状态关联；
- 目标是公开发布或固件上架审核。

改用：

```json
{
  "device_id": "sticks3",
  "runtime": "qemu-unified",
  "network": {
    "profile": "uiflow2-sticks3-unified"
  }
}
```

可用的 unified profile 和证据字段以 Device Service 的
`GET /api/v1/devices`、[统一设备运行时契约](unified-device-runtime.md)
和 [网络模拟方案](network-simulation-plan.md) 为准。

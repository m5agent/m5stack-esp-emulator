# Core2

- SKU：`K010-V11`
- 分组：`ESP32 LX6`
- 外壳：`核心主控`
- 运行时：`reference-ready`
- 外设仿真：`simulated`
- UIFlow2：`支持`，m5ui：`支持`
- UIFlow2 固件：v2.5.3 / `1897200000000003470`

## 硬件档案

| 项目 | 值 |
| --- | --- |
| SoC | ESP32-D0WDQ6-V3 |
| 架构 | xtensa-lx6 |
| Flash | 16 MB |
| PSRAM | 8 MB |
| 机身尺寸 | 54 × 54 × 16.5 mm |
| 重量 | 45.1 g |
| 显示 | 320×240 ips，2"，ILI9342C / ILI9342E，触摸 |
| 控制 | Touch, PWR |
| 外设 | imu:mpu6886, rtc:bm8563, microphone:spm1423, speaker:ns4168, power-monitor:ina3221 |

## 模拟状态

reference-ready：真实固件、画面和输入已打通。

- 验证：`display-input-peripherals-wifi-ble-pass` (2026-10-25)
- 详情：官方 UIFlow2 v2.5.3 在同一 m5core2 guest 内通过 320x240 显示/触摸、AXP2101、INA3221、MPU6886、PCF8563、NS4168 扬声器、SPM1423 麦克风、OpenMAC WiFi DHCP/HTTP、example.com IPv4 DNS/HTTP 和 stock firmware 外部 BLE GATT；确定性 TCG/icount 调度下 10/10 次无重试首轮启动通过，QOM 注入不暂停 guest。规范 Device Service profile `core2-native-hci` 在五个独立 lease 中通过 HCI-4：frame、27 节点 QOM、WiFi/公网、外部 NUS GATT、pcap 和 evidence 同包，且 gdb_bridge=false。m5core2 machine 现以 8 MiB PSRAM device 和 DRAM1 32 KiB MMU 页映射运行；三个独立 esp_himem lease 在同一个虚拟窗口切换两个不同物理块并反向校验，QOM 8 MiB，正常 heap 仍为架构允许的 4 MiB 直接映射窗口。0005 恢复 nested guest call 的 caller-saved sregs，并把 HLI allocator/callback 注入限制在 halted/idle vCPU；两批独立 5×10 秒运行合计 10/10，3 个 60 秒 hold 为 3/3，2 个 120 秒 hold 为 2/2，另 2 个 active-BLE 600 秒 hold 为 2/2。3 个独立 lease 分别完成 20、30、60、120 轮 scan/connect/NUS GATT/disconnect；当前参数上限为 121 并拒绝 122。一百二十轮每 lease HLI 3377/3377、events 2297、ACLs 1080，HLI/meta/TX queue、错误和 panic 均为 0，连接/L2CAP/GATT 池回到 3/9/3，三次 frame SHA256 一致。600 秒 active-BLE hold 时 peer 未关闭，HLI 45/45，队列与错误为 0。另一次 7200 秒 active-BLE WiFi/公网/GATT 保持由 hash-freeze runner 完成 artifact-bound 功能门禁：首 lease 前绑定 firmware/ELF/QEMU，运行期无资产漂移，frame/pcap/网络/GATT/HLI health 均 PASS，结束 HLI 45/45 且队列、错误和 peer-close 为 0。QEMU host RSS 从 744160 KiB 增至 1202176 KiB；后续 vmmap 把增长定位到未限容的 TCG translation buffer，`tb-size=128` 的 120 秒复测稳定，最终两小时限容复测 PASS：RSS 323536→252992 KiB、phys footprint 250880→188416 KiB，资产与工具哈希无漂移。旧 `core2-native-vhci` 的 repeated lease 为 1/2，仅保留为 GDB 诊断/兼容路径。121 轮第一次运行完成 29 轮后暴露固定 180 秒 readiness 预算缺陷；第二次完成 121/121 后又暴露 reconnect-only accelerator 采样缺失。两处 harness 问题修复后，3 个独立 lease 均完成 121/121 artifact-bound PASS：bounded_tcg_cache、WiFi/公网、NUS GATT、frame/QOM、pcap、evidence 和 cleanup 均通过，每 lease HLI 3405/3405、events 2316、ACLs 1089，队列、错误、dropped、peer-close 和 panic 均为 0。随后 3 个连续 ready session 在 HTTP/BLE companion 仍活跃、BLE peer 仍处于 linger 时被 DELETE；每次 stop 均为 stopped/无错误，companion 进入 terminated，BLE/QEMU PID 回收，worker lease 归零，下一 session 继续通过 frame/QOM、DHCP/DNS/HTTP、外部 NUS GATT、pcap 和 evidence。四实例首批 4×120s 实际达到并发 4 但为 1 PASS / 3 FAIL：一个 lease 完成可见功能但仍有 hli-errors=1 与 hli-prealloc-failures=2；另两个在 READY 前于 NimBLE ble_hs_hci_process_ack 的 0x402630cc 处 panic，前序已有 HCI ACK timeout/reset，PC=0 仅为 reboot 后次生故障。物理 cache/PSRAM、四实例及更多实例稳定性、长时并发/吞吐、其他 teardown 模式与 Espressif BT baseband/controller bit-exact 执行仍未完成。
- 内存验证：The m5core2 machine now exposes a QOM-effective 8 MiB PSRAM device. Normal ESP32 DRAM1 remains a 4 MiB directly mapped heap window; a dedicated ESP-IDF esp_himem probe passed in three independent Device Service leases, mapping two different 32 KiB physical blocks through the same virtual MMU window and verifying both after remap (4,456,448 bytes himem capacity, 262,144-byte reserve). Guest sustained stress remains PASS in three independent 120-second leases (35/35/35 checks, 105 MiB total) and one 600-second lease (179 checks). Physical PSRAM/cache timing remains NOT RUN.
- 并发验证：Two independent two-instance no-stagger 4x120s gates pass 4/4 each (8/8 total), and two independent three-instance 3x120s gates pass 3/3 each (6/6 total). Patch 0008 preallocates real guest HCI-event buffers and ACL mbufs while CPU0 is idle, so QEMU can fill those guest objects without nested guest calls when CPU0 is busy. Every lease records all 36 events and 9 ACLs on the fast path, two spare objects of each type, HLI 45/45, hli-errors=0 and no scheduler reset or panic. Three-instance startup exposed and closed harness-only issues: the BLE peer scan window now follows session readiness within 40-120s, and the sustained PSRAM floor uses hold/5. Trace-bound Command Status delivery latency falls from about 3.660s to 0.328s. One four-instance 4x120s batch then reached real concurrency 4 and failed 1/4: attempt 2 had hli-errors=1 and hli-prealloc-failures=2; attempts 3/4 panicked before READY in NimBLE ble_hs_hci_process_ack at 0x402630cc after HCI ACK timeout/reset. Four-or-more-instance stability, sustained throughput and teardown modes beyond active-stop remain OPEN.





## 文件

- `device.json`：设备中心与页面使用的完整档案
- `firmware.json`：UIFlow2 固件定位与缓存约定
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用

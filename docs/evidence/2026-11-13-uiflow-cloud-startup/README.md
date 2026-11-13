# 2026-11-13 UIFlow2 原版启动与云端配对

后续交付已完成：源码 `8598b1f603ae6638a3f6d27824431781429b9e49` 已合 main，
完整平台 2098 项（1 项跳过）、前端契约、四项验证器与远端 CI 通过。更新后的
两个执行角色完成八次原版配对及一次本地编程复验，旧历史保留、会话全部清场。
逐次证据和一次观察脚本失败见[固定发布后记录](https://github.com/m5agent/agent-work-logs/blob/1d3fae72bd990be3ddda105e4185f665916c8e7d/records/esp-emulator/2026-11-13-uiflow-cloud-startup/followups/2026-11-13-published-source-paths/README.md)。
下文及 `summary.json` 保留部署前独立验证的当时状态，不覆盖原始记录。

本轮为 **virtual-device validation**。最终独立 Device Service 的六款原版
固件已收到真实 MQTT 配对响应，并保存原生 framebuffer、网络证据和停止历史。
最终六帧已逐张确认官方页面显示可读六位 Access Code，原生路径为 **PASS**。
真实网页的 CoreS3、StickS3 官方入口也分别通过；常驻部署尚为 **NOT RUN**，
因此本记录的完整交付状态仍为 **PARTIAL**。
逐镜像、运行时、源码、帧和 ZIP 身份见 [脱敏摘要](summary.json)。

## 根因与修改

原网页把 UIFlow2 参考选项解释成本地编程环境：启动时安装 UART REPL bootstrap，
默认 `runtime=qemu`。这条路径没有运行原厂开机菜单的自动联网与显示逻辑。
旧入口对照获得全黑 framebuffer，REPL 本身可用；因此“刷入 UIFlow2”不能被
等同为已经进入官方云端配对界面，也不能据此判断原版固件有缺陷。

新增明确的“官方 UIFlow2 · 云端配对”和“本地 MicroPython 编程”入口。
官方入口只接受广告中固定 SHA 的本地原版参考镜像，使用真实 `qemu-wifi`。
合法 NVS 包含完整官方字段及类型为 `u8` 的 `boot_option=1`；复用原有会话
NVS overlay，保留应用、`boot.py`、`main.py` 和 filesystem 原始字节。
该 NVS 与官方生成器 `0.3.0` 的结果逐字节相同，服务不提供或伪造配对码。

原版 BIN 通常省略尾部已擦除空间。初次新 API 验证中的 CoreS3、StickS3、
Core2 因完整 Flash 长度检查而失败，三份失败记录保留在摘要中。修复复用既有
Flash padding helper，仅补尾部 `0xff`，把原始和规范化镜像存为独立 artifact，
不改写同 SHA 已有固件 manifest。最终请求仍绑定原始 BIN SHA，回执另给出
完整 Flash SHA；原始、规范化、NVS 三份 artifact 均被会话保留。

模式默认关闭 HTTP fixture、保留 pcap，调用者合法网络策略仍执行原有准入和
隔离检查。参考 pin 不符、与编程/上传/NVS 字段冲突、虚拟 AP 覆盖均被拒绝。
Core2 广告另检查专用 radio runtime，避免仅普通 QEMU 可用时误报云端能力。
创建幂等绑定原始请求；历史恢复保留模式、双 SHA 与来源信息。

## 最终原版路径

| 设备 | DHCP / DNS / SNTP / MQTT | 原版 framebuffer | 清场 |
| --- | --- | --- | --- |
| CoreS3 | 实际配对响应已收到 | 官方六位码 PASS | stopped、lease 释放、历史保留 |
| StickS3 | 实际配对响应已收到 | 官方六位码 PASS | stopped、lease 释放、历史保留 |
| Core2 | 实际配对响应已收到 | 官方六位码 PASS | stopped、lease 释放、历史保留 |
| AtomS3R | 实际配对响应已收到 | 官方六位码 PASS | stopped、lease 释放、历史保留 |
| StopWatch | 实际配对响应已收到 | 官方六位码 PASS | stopped、lease 释放、历史保留 |
| Cardputer ADV | 实际配对响应已收到 | 官方六位码 PASS | stopped、lease 释放、历史保留 |

每例均使用未改应用的原版参考 BIN，通过新 `uiflow_startup` API 建立原生会话。
同会话 pcap 记录 DHCP、DNS、SNTP 请求/对应响应，以及 MQTT CONNECT/CONNACK、
订阅、配对请求和携带非空六位数字 `data.code` 的下行响应。公开摘要只保留
协议计数和布尔值；下行 topic 项仅验证规定前缀，不冒充设备身份逐字匹配。
`running`、`M5Things.status()==2`、INFO 日志或非黑像素均不单独作为配对成功判据。
固件 INFO 日志可能被关闭，不要求出现固定 `New AccessCode` marker。

Core2 同时补上既有真实 eFuse controller 的 drive 接线。独立 IDF 探针在
`qemu` 和 `qemu-wifi` 两个会话中，通过三条 guest API 读回正确、非零、不同
的会话身份，并验证 ROM CRC、停止与重启历史；见
[Core2 身份证据](../../../tests/firmware/esp32_efuse_identity/evidence-2026-11-13-core2.json)。
此前 #224 对 Core2 未接线的历史结果保留，C6 身份接线仍不由本轮覆盖。

## 复现与验收边界

1. 配置支持相应主机和真实网络控制器的原生运行时，准备摘要中固定 SHA 的原版
   UIFlow2 参考 BIN；查询 `GET /api/v1/devices/{device_id}` 的 `uiflow_startup`。
2. `POST /api/v1/sessions` 仅携设备、合法 TTL/幂等键，以及
   `uiflow_startup={mode:"cloud",reference_sha256:<advertised SHA>}`。
   不同时传编程模式、上传固件或手工 NVS。
3. 读取同会话的串口、原生帧和 evidence ZIP，核对实际配对响应与官方画面；
   先保存 evidence，再 `DELETE /api/v1/sessions/{id}?purge=0`，确认停止与 lease 释放。
4. 网页选择官方入口重复执行；另选本地编程入口，实际 Run 绘图/串口代码，
   分别验证输入方式和后端生命周期，不能只检查页面控件或 HTTP 201。

最终真实网页的 CoreS3、StickS3 官方入口均看到六位码、收到实际配对响应，页面
无错误且停止完成。本地编程对照则在真实 guest 执行代码，观察到串口 marker
和蓝底 `Local code OK` 绘图，完成停止；该例发生在最后一次独立 artifact
helper 调整前，编程路径没有变化，摘要明确单列其阶段，不冒充最终源码重跑。
常驻服务更新及更新后的原路径复测为 NOT RUN。
原生服务经网页控制不等于 browser-WASM 获得公网数据面；浏览器 WASM 联网、
物理硬件/RF/功耗/电气/声学均 NOT RUN。其它型号、固件和长期在线稳定性不继承。
本轮未提交 Burner。

原始截图、串口和 pcap 可能含配对码、凭据与设备身份，仅保留在私有原始证据中。
这里不发布原帧、连接端点、会话标识或报文内容。后续最终确认只追加相同 SHA
对应的状态，不删除旧入口对照或首次失败。

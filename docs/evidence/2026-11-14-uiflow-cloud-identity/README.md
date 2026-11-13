# UIFlow2 云端身份与 WebREPL 心跳

日期：2026-11-14。验证类型：**virtual-device validation**；宿主协议诊断单列。

## 根因与边界

原版 UIFlow2 的 MQTT 配对码和 WebSocket WebREPL 是独立通道。此前配对码
获取通过，不证明账号绑定、WebREPL 持续连接或远程代码执行通过。

同一 CoreS3 原版 BIN
`5847a2bcae33d6bb8942de1c3ae92295a8441b6a3424c78e444fc748c9508ded`，
标准尾部补齐后的镜像
`480ca4a24c1c1b56deef1218f8533bf5b00c9e33a98f3b3f705e2569b53051c0`，
运行于 Xtensa
`5ce7d9f5ce397ce87935626c0284955714e0ed286fcce0cd91ca47f4f326040c`。
原版应用未改动，只有正常 cloud NVS 配置和 NIC/eFuse 身份夹具。

| 对照 | 真实观测 | 结论 |
| --- | --- | --- |
| 原会话随机身份 | 约 68 秒 20 次有效 HTTP 101；1 次 `mac_not_found`、19 次 `mac_not_bound`；20 次服务器主动 FIN | 云端身份拒绝，不是握手或 TLS 证书失败 |
| 授权身份 | 同 BIN、同运行时；收到匹配的 `deviceConnected`、5 次完整文本心跳往返；4 个 control Ping、0 control Pong | 身份被接受，但长期连接 **FAIL** |
| 授权身份长窗口 | 距 SYN 151.354 秒 guest 主动 FIN；串口出现一次 `no PONG` / `120 seconds` 超时 | 原固件协议心跳超时，与身份拒绝分开 |
| 独立宿主标准协议 | 同端点单连接发送空载及 nonce control Ping、文本 PING；12 秒仅有文本 PONG、无 control Pong | 故障无需模拟器即可复现；此行不是 guest 验证 |

两份 guest 的 MQTT、WebSocket、eFuse 身份均一致，TCP 重组无缺口或冲突。
第六个文本 PONG 在 guest FIN 后才到达，未计入完整往返。原始 PCAP、串口、
帧与身份只保留在私有证据中；公开摘要仅保留协议类别、相对时序和哈希。

## 平台改动

- Cloud 默认使用按虚拟板型持久化的身份，跨会话及服务重启复用；普通上传
  会话遗漏新字段仍使用独立会话身份。
- 显式 `device_identity` 可指定命名 key 或已授权 MAC；同一活动身份按最终
  MAC 排他，停止清理完成前不释放。实际 NIC 与 eFuse 使用同一冻结值。
- 网页云端入口可输入一次性授权 MAC，空值使用持久虚拟身份，不预置真实
  地址、不写浏览器存储。
- 独立显示配对码获取、云端身份拒绝、登记回执、文本心跳和断开。诊断来自
  同 guest 的有界 PCAP 重组，不更改原固件、不伪造 Pong、不隐藏串口错误。
- 项目自有 COI Worker 重建 HTTP 204/205/304 时使用空正文，保留隔离响应头、
  原有生命周期和真实网络失败。第三方原始文件、来源 SHA 与 MIT 许可证不变。

接口与限制见 [Device Service API](../../device-service-api.md)。新生成的虚拟
身份仍须通过真实云端绑定；持久化本身不创建云端 deviceId。跨服务或实体
设备的同 MAC 占用无法由单个服务完整检测。

## 当前执行证据

- [原版身份及长窗口诊断摘要](diagnostic-summary.json)：保留两个不同失败原因，
  包含 BIN、运行时、PCAP、ZIP 和帧 SHA；宿主控制 Ping 对照单列。
- [持久身份真实设备会话摘要](persistent-identity-summary.json)：三个不同 guest
  会话跨越一次服务重启，实际 MQTT/WebSocket/eFuse 身份保持一致；活动会话
  的命名身份和显式 MAC 别名均拒绝并发使用。所有 owned guest 已停止并释放
  Flash，云端未绑定仍诚实报告 `identity_rejected`。
- [Core2 原版身份与取码](classic-identity-summary.json)：经典 ESP32 的真实
  MQTT 身份与 eFuse 一致，取得云端配对码。该旧参考固件没有发起 WebSocket，
  因而显示 `not_observed`，不把没有该通道报成 WebREPL 通过。
- [网页失败与复核纠正](browser-failures-summary.json)：保留首次长窗口的 UI
  误判、独立复核纠正及短窗口的 910 次真实取帧失败。最初判断的收据明确由
  stdout 重建，不声称存在未经改动的原文件或原文件哈希。
- [COI 浏览器控制矩阵](coi-browser-controls-summary.json)：13 项真实浏览器
  HTTP/Worker 控制，包含原 Worker 的 4 项失败反例、修复后的条件响应与
  原注册更新接管；这些是宿主测试，不是固件执行。
- [最终独立候选网页验收](browser-final-summary.json)：同原版 BIN、同运行时、
  授权身份，经真实网页启动并在首握手后观察超过 195 秒。UI 与身份链路
  **PASS**，云端长连接 **FAIL**；常驻服务交付与线上 Pages 发布另行验收。

首次候选客户端早于服务就绪被拒，未分配 guest；第一次并发控制检查晚于
前一 guest 停止，正确成为顺序复用。该会话通过原幂等请求恢复、补齐实际
活动占用拒绝与 ZIP 后清理。两次测试设置问题均保留，不算产品失败或悄悄重试。

## 网页条件取帧故障与修复

首次网页长窗口虽然完成取码和心跳，截图仍出现 `Failed to fetch`，并将仍在
运行的 guest 显示成“运行未完成”。原验收只检查 `pageerror`，不足以证明 UI
正常，已将该次 UI 结论由 PASS 更正为 **PARTIAL**。独立短窗口进一步捕获
910 次 `/frame.png` 的 `net::ERR_FAILED`；服务端没有对应的 500/503 或异常。

真实 Chromium 对照将问题定位到 COI Worker：网络 304 的 body 可表现为
非空的空流，而 `new Response(body, {status: 304})` 禁止该正文。第三方
Worker 的重建操作因此失败。无 Worker 的四组 cache/redirect 组合均正常，
原 Worker 的四组均失败，修复后四组均正常；没有靠更改缓存或重定向策略
绕过条件请求。

最终独立候选中，5,859 次条件取帧 304 成功，运行期 API 网络失败、API HTTP
错误、错误横幅和运行错误状态均为零。页面分别显示配对与 WebREPL 观测，
停止后明确显示末次观测。真实取码、云端登记以及授权输入、会话、eFuse、
WebSocket 查询身份的一致性均通过，业务身份拒绝为零。

同一 guest 仍有 7 次心跳往返、6 次协议 PING、0 次协议 PONG；约 156 秒
断开、160 秒重连，ZIP 串口保留一次 `no PONG`。网页修复没有改变这一
**FAIL**。ZIP 的 10 项文件长度和 SHA 校验通过；证据在停止前采集，guest
进程退出、Flash 释放、活动会话归零且浏览器关闭。停止操作之后的一次
`ERR_ABORTED` 是主动取消，不计为运行期故障。

## 复现

在独立 Device Service 中读取设备的 cloud capability，使用原始参考 SHA
创建 `uiflow_startup.mode=cloud` 会话。记录真实 MQTT 回包、WebSocket
升级和业务帧；运行超过 180 秒以覆盖协议 PONG 超时。ZIP 采集后再停止，
保留历史并释放可变 Flash。授权身份对照应单实例、顺序进行，不能把具体
真实地址写进脚本或公开记录。

`uiflow_cloud_status.read_uiflow_cloud_status()` 可从私有 PCAP 生成无身份的
固定枚举摘要。诊断超限/不完整时明确降级，不能把缺少证据当成通过。

前端合同使用 `npm run --prefix platform/tests test:contracts`；本次最终版本
已通过。独立 Worker 浏览器控制使用
`node platform/tests/test_public_coi_worker_browser.mjs`，默认使用 Playwright
Chromium，可用 `PLAYWRIGHT_CHROMIUM_EXECUTABLE` 指定浏览器。真实 guest
验收还必须记录运行期请求失败、HTTP 错误、错误横幅和 runtime 状态；不能
仅以 `pageerror` 为空判定 UI 通过。

## 尚未通过的范围

云端 control Pong 处理尚未修复，原 BIN 无公开配置接口关闭该超时。
远程 REPL 指令往返、物理硬件和 browser-WASM 云端联网均 **NOT RUN**。
纯 browser-WASM 没有这条原生云端网络执行路径；原生结果不授予浏览器联网
能力。Pages 连接外部 Device Service 时共用条件取帧与 COI Worker，但其
部署和实际线上路径必须另验，不能据本报告宣称纯 WASM 或 Pages 已修复。
没有提交 Burner。

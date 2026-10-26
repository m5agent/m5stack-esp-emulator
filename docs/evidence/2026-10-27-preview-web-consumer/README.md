# Preview Web 消费者与完整文件包

日期：2026-10-27。API 1.43，`UNIT-HOST-34` 的限定 Web 验收通过。
本块是 virtual-device validation；physical hardware / AIFlow 消费者仍 NOT RUN。

首次启动初始化 UIFlow2，此后 complete checkpoint → Preview Run 经同一 guest 的
UART REPL 部署和执行。文件写入 guest VFS，不重新构建或刷入完整固件，也不重启 VM。
当前脚本入口为 main.py，支持纯字节码 MPY 依赖、模块和资源；独立 main.mpy
入口、native/IRQ/timer/thread 完整清场、SSE、GC、保存开机与热插拔没有因此完成。

## 结果与范围

- 最终 [r4/report.json](live/r4/report.json)：CoreS3 PIR / Relay 两个可见 session，
  分别 5 / 6 次实际 execution，同 PID、固件和 VM nonce；初始化、外部 API 完整包、
  Web 加载并编辑、连续 Run、取消后恢复均通过。
- 537 份直接 HTTP response 的状态、原始 bytes、headers 和 hash，1317 条浏览器
  HTTP 记录保留。无页面错误，托管 mutation 没有回退到旧 session program/input/
  unit-input/renew/reset 路由。复位明确禁用；续租和关闭走 Preview。
- 编辑 main.py 后全部非入口文件逐字节保留，含真实 mpy-cross 生成的 helper.mpy、
  普通/namespace 模块及 RGB PNG。每个包 Run 的实际 execution START 之后，独立
  解析新鲜 UART READY/SAMPLE JSON，核版本、helper/init/logic、Unit 和计算结果。
- PIR 可信 DOM 1→0 输入经 Preview receipt、实际 guest 原 PIRUnit 驱动与独立 raw
  QOM 核对；Relay 原驱动输出 true 经 QOM 和 UnitPanel 读回。二者不构成物理电气测量。
- Run 帧五个身份/hash 头与实际 PNG bytes 校验；蓝→绿应用帧及 Web 模型屏幕选定
  像素通过。同 Run 的不同 capture 允许 hash 不同；不称整张同一 PNG 逐字节映射，
  也不把 Unit、串口、设备态和帧称为原子快照。
- 两份停止前 ZIP（59 / 70 个成员，含 manifest）逐成员 CRC、大小和 SHA 核验；
  Preview 自动 before-close ZIP 另有 captured 收据。保留历史和末帧，stop/purge=0，
  mutable Flash 释放、原 PID gone、active session / lease 均为 0。
- 390 / 768 / 1024 / 1440 的表单、状态、长 hash 和键盘焦点可用且无页面水平溢出。
  390 / 1024 的默认 3D 构图存在外缘裁切，按 UNIT-HOST-35 保留；截图中的 sticky
  顶栏位置是整页捕获的限制，不授予完整视觉验收。

固件 SHA256：`0ede40601c1e37b7ba32c87a3ca55e4da7a448f6cf52957f005763bc7c7c78e8`。
QEMU SHA256：`b8de32a39be06162ae8ce8529b218370038936059dba067b9a7109a470e067d2`。
服务 generation 34，runtime qemu / CoreS3。其它主机、Unit 或固件不继承本次 Web PASS。

## 客户端与 API

一个 SessionVisual 共享一个 PreviewClient 给程序、Unit 和主机控件。权威 Preview /
Run GET 决定 generation、owner epoch 和输入/帧上下文；不明请求不自动重放，取消独立
于慢保存/准入回执。Cancel 冻结当刻逻辑请求，只按精确 generation/revision 定位，
不会取消后来出现的本地或外部新 Run。

旧请求、解码、输入队列、held intent 和运行观测在 Run 变化时失效。短暂失去确认后，
必要 release 仅可在新鲜同一上下文恢复后补偿；未知补偿不循环重放。销毁面板时先给
原 Run keepalive release 发出机会，共享客户端 drain 最多等待两秒。真实浏览器
pagehide 的宿主 HTTP 测试通过；不保证浏览器进程硬杀后仍发送请求。

新增只读 `GET /api/v1/program-revisions/{revision_id}/files` 返回完整 canonical
base64 mapping、原 metadata 和 limits；原 metadata GET 不变。Web 校验完整内容后
编辑 main.py 并保留其余文件，外部 revision 与本地草稿冲突需要明确加载/合并，
轮询不覆盖草稿。创建 Preview 需要控制 Token；未知创建结果保留幂等 key/body，
刷新与重试不产生新创建意图。共享 Bearer principal 不等于多租户隔离。

## 验证与失败保留

- Python 平台 1110 项 PASS（含文件 API 18 项）；共享客户端 22 组、ProgramPanel
  27 组、UnitPanel 23 组（含真实客户端/真实 pagehide）、Run 帧/主机控制 22 组、
  创建/恢复 9 组通过。旧程序 13 组、旧 Unit 34 组、audio 和 3D mount 回归另列。
- 文件 API 独立复跑 18 项；OpenAPI 348 个本地引用全部解析，实际 MPY/二进制/
  Unicode envelope schema 验证和非法 utf8 下载别名负控通过。
- [r1](live/r1/report.json) 在创建前发现初始无 Token 的 devices 401 无法经保存 Token
  恢复；修复真实页面目录重载并加负控，没有通过预置 Token 绕过。
- [r2](live/r2/report.json) 是 runner 将 raw-paste 前缀误当纯 START 行而超时；guest
  实际包/MPY/新 READY/蓝帧已存在，失败 ZIP 和 closed/Flash 清理保留。只修解析
  协议前缀后的精确 execution marker，不把该轮改成整体 PASS。
- [r3](live/r3/report.json) 完整数据链 PASS；视觉检查发现 ready 后创建按钮旧文案，
  修正文案并加 ready/pending/enabled 断言后完整重跑最终 r4。
- ACK 丢失、销毁松键丢失、只读失败提前消耗 release attempt、取消慢回执等旧行为
  负控、独审脚本和实际失败均在 verification 保存。样式审计原有 27 项保持，增量 0。
- 无 C/QEMU 改动，完整外设矩阵 NOT RUN；没有授予硬件、低秒级 SLA 或 AIFlow 接入结论。

完整索引见 [manifest.json](manifest.json)，源码与来源方式见
[source-freeze.json](source-freeze.json)。早期源文件如由保留编辑重构，明确标记，且
必须匹配当轮实际记录 SHA；不冒称当时另做了源码拷贝。独立审计位于
`verification/preview-unit-panel-20261027/root-live-independent/`，其 JSON 给出逐门禁结果。
不复制独立固件/ROM/编译器二进制；原始 HTTP JSON 中的完整程序包和 ZIP 字节保留。

# 外壳更新与公共程序 checkpoint

日期：2026-10-27（开发及实测2026-10-26；归档与独审收尾2026-10-27）。归属 `UNIT-01`。
本页只报告对应固定源码与实际运行；
hardware validation：NOT RUN。整体 AIFlow Preview/Run 与 Unit 工作流仍进行中。

## 固定外壳与浏览器范围

公开模型固定至 `3681a6482aff96501d44659ba5a1603246f1fe1f`：14 主机、113 视觉
Unit、687 JavaScript 文件、287 许可 PNG。旧 65 PNG 字节保持；新增 guide 使用
精确路径/SHA 白名单，176 个文档引用闭包已核，不导入原始照片、CAD、固件或依赖目录。
来源、许可证、闭包、敏感模式扫描和全部 vendor SHA 见 [sync 冻结](visual-sync/final-freeze.json)。
视觉数量不扩大内部协议准入：28 款注册控制器保持，85 款仅有外壳。

[旧 vendor 完整基线](browser-old-baseline/report.json)与
[新 vendor 首轮失败](browser-new-r1-failed/report.json)分别保留。首轮在 AudioPlayer
固定蓝色 LED 的通用 RGB fixture 断言失败，不能作为完整通过；随后 census 检查
113 款公开接口，覆盖固定色及 MiniToF90 brightness-only 等差异，测试适配真实
接口而未改模型。各轮 runner/helper 的精确 SHA 与恢复后的原始字节见
[fixture 冻结](browser-fixture-freezes/file-manifest.json)。

[最终独立完整 r2](browser-new-r2-final/report.json)从头验证 14 主机、113 Unit、
287 PNG：278 层五类 printed-artwork 纹理就绪及归属、196 LED 与 44 joint 的
逐个输出/零输入回声、59 context 全关闭，零 page/resource 错误；保留触摸、按键、
帧、attach race、nested HUB、销毁与 fallback 检查。Fader slider 输出 bridge
明确 UNSUPPORTED；83 项 catalog 配置逐项 NOT RUN，默认配置不外推配置变体。
完整 PNG 解码不证明光学对位、机械尺寸或电气功能。另人工查看
[代表渲染](verification/rendered-models-contact.png)，完整原图保留于最终轮目录。

## 实际 guest 与 Web 复测

新 pin 下 [默认同色灯反馈](live-uniform/report.json)重新执行两个 CoreS3 可见
session，每组 A/B/C/D 四次程序，在同一 PID、固件及 VM nonce 下运行原 I2C/RMT
驱动。14 颗 mounted 灯组件的 56 次材质状态、新鲜 UART、独立 raw QOM、应用帧、
浏览器 503/unknown/恢复和零回声分别核验。HUB 视角有自然遮挡；Encoder 两灯的
光学可读性尚未验收，材质断言不代表 14 灯同屏无遮挡。

[Scroll 实际 Web](live-scroll/report.json)另以一可见 CoreS3 session 验证网页按压、
源计数输入、原 ScrollUnit 读回、RGB 与应用像素；未单独采集逐leaf raw QOM，
通用ZIP QOM有节点截断，不能当作完整raw快照；不授予轴角、方向或机械标定。
两条真实复测均冻结 service generation 32 / 实际 QEMU SHA
`b8de32a39be06162ae8ce8529b218370038936059dba067b9a7109a470e067d2`；
固件 SHA、接线、程序身份和采样时间各自保存在报告。功能只经 8787 Device Service，
先 evidence ZIP，再 purge=0 停止；独立核历史/末帧保留、owned PID 消失与 Flash 释放。

## 程序执行及公共 API

首次初始化一次 UIFlow UART REPL，随后在同一 MicroPython VM 内传输、编译和
运行 `.py`；纯字节码 `.mpy` 可作依赖。每次编辑不重新 compose 固件或启动 guest。
[执行链交叉复核](execution-cross-review/report.json)重新核验既有四主机的实际
source/package 证据；其审计未执行新 guest，也不自审公共 checkpoint API。
独立 `main.mpy` 入口仍为 `UNIT-HOST-33` OPEN。

API `1.41.0` 增加 `POST /api/v1/program-revisions`、对应 metadata GET，以及既有
同步 `/sessions/{id}/program` 的互斥 `revision_id` 引用。完整 package ID/文件 SHA
及首次 created_at 不变，引用执行不再 create revision。公共保存不触碰 guest；
真实限额和 `gc_enabled=false` 公开。旧 `source`/`files` 请求保持兼容。
[宿主冻结](checkpoint-host/host-freeze.json)记录真实 HTTP/store/故障测试；
[最终OpenAPI检查](verification/openapi-final.json)核 240 内部引用、59 schema 和正反请求例；
独审发现/program缺少500/503文档响应后已补齐，修前检查及YAML原字节也保留。
首次验证脚本把 server 前缀重复拼进 paths 的失败单独保留，产品未因此变更。

坏 ID、未知/损坏包、混字段、stale 以及已知 native/损坏 bytecode 在新执行分配前
拒绝；guest 的实际 MPY 版本/small-int 不兼容仍可能在同步中断旧程序后才发现，
须保留 failed execution 收据。START 不是应用 READY 或首张新应用帧。

[CoreS3 PIR](checkpoint-live-pir/report.json)与[Relay](checkpoint-live-relay/report.json)
各以一个可见session连续执行12次（含预期失败）；公共A/B/C在创建session前保存、
重复POST及GET保持原ID/created_at。有效A/B/B-recovery/C-recovery只提交revision_id、
expected_execution_id和timeout_seconds；保留原语法、guest兼容性及目录篡改负控的
legacy路径。每例8种引用拒绝后都有新的串口byte窗口证明B继续，ZIP顶层恰好12个
execution。两例983条HTTP响应逐条保存实际status、完整有序header pairs、body和SHA（本批无重复header项），
见[运行摘要](checkpoint-static/live-summary.json)；先ZIP后purge=0，历史/末帧、PID退出
及Flash释放已分别核验。原驱动程序函数AST与HEAD相同，默认plan不访问网络；
19项runner离线测试与972项完整平台测试、七项前端fixture均通过。

[另一审查者的API与实际字节复核](checkpoint-cross-review/review.json)保留原P3发现、
修复收据和[真实运行复核](checkpoint-cross-review/live-byte-review.json)：另核983条
主流程HTTP及4份停止后GET、168个ZIP成员、11份执行源SHA。停止后末程序状态是
interrupted，不能写成独立Run取消完成；本块未实现该取消资源。

串口读取改为按 offset seek 后只读有界窗口；16 MiB 稀疏日志的原版失败与新版
通过分别保留于 verification。缺失/空文件、offset clamp 和停止历史保持；任意
byte 切片的 replace 解码未改，不能声称解决了 UTF-8 分片。

新pin实际Web的[独审](visual-live-cross-review/review.json)对Uniform限定范围给PASS；
Scroll因本批缺独立raw QOM给PARTIAL，同时保留其API/串口/PNG/材质及清理通过。
该PARTIAL不被作者runner的成功状态覆盖，也不拼上一轮raw证据冒充本轮齐备。

## 剩余边界与来源

本块没有实现 Preview/Run、latest-wins、保 VM 独立取消、SSE、后台订阅采样、
AIFlow 端接入、GC、hotplug、开机保存或 native/IRQ/thread 完整清场。
`UNIT-HOST-29/33/21` 继续 OPEN。未改 QEMU/C 控制器，完整矩阵本块 NOT RUN；
上一独立完整轮的 Core2 IMU marker 缺口不由本块结果补成 PASS。

归档以 [file-manifest](file-manifest.json)保留原字节与来源；代码/原始 Markdown
追加 `.txt`，不修改内容。仓内不包含固件、ROM 或 compiler 可执行文件。

本块实现提交 `19f2bdeb23c26e039b8d4d2a8df582ebca723433` 后重新 fetch/merge
`origin/main@f2061759897955e6017d4aa2a41bd5ba962c35b6`，结果 Already up to date，
工作树干净、8份验证源码SHA保持，见[同步收据](integration.json)。跨日时索引首页日期
未同步曾使文档检查失败，原48项轮次保留；修正日期后的独立48项文档检查通过。
整体UNIT-01仍进行中，后续执行顺序只在Backlog维护。

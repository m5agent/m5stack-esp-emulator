# 同 VM Preview / Run 控制面验收

日期：2026-10-27。基线 `3af10724`，本目录保留此次源码冻结与原始证据。
归属 `UNIT-01`，不关闭其它 Unit、AIFlow 编辑器接入或物理硬件工作流。

1.42 API 在不可变公共 checkpoint 上增加稳定 Preview 和异步 Run。首次准备
可见 UIFlow session，后续同 VM UART 执行；单 worker 串行传输、latest-wins、
独立取消、输入 permit/drain、Run/execution 帧门禁和 managed session 防绕过。
SQLite WAL/FULL ledger 在 UART 前提交身份/意图/幂等原收据和 revision pin。
控制 Bearer 验证后共享 `local-control`，不接受 body owner，不声明多租户。

CoreS3 PIR、Relay 两个独立会话均完成有限初始化、A、突发 B/C/D、运行中
取消 D、取消后再运行 C。每例 6 个 Run 意图、4 次实际 execution；B/C 都在
触及 UART 前被 superseded。A/D 的取消均确认实际 fresh raw prompt；不得把
这两个 queued supersession 样本外推为任意传输阶段的取消 PASS。

两例固件 SHA256 均为
`0ede40601c1e37b7ba32c87a3ca55e4da7a448f6cf52957f005763bc7c7c78e8`，
QEMU runtime SHA256 为
`b8de32a39be06162ae8ce8529b218370038936059dba067b9a7109a470e067d2`。
各自同 PID/固件/VM nonce，完整文件包、资源和真实纯字节码 `.mpy` 依赖；
PIR false/true/false、Relay false/true/false 都核原驱动 typed UART、独立 raw
QOM 和 Unit 状态；A/C PNG 核资源像素及五个身份/hash header。
每个 UART 样本位于其确切 execution START 后的原始字节窗口。

PIR 419 条、Relay 368 条主 HTTP 记录；各 evidence ZIP 46 成员，核完整成员
索引、每项 size/SHA、session/execution/revision、原始包字节、guest 部署库存、
原始串口窗口、Unit/QOM 和导出 C 帧。关闭前另自动保存独立 evidence ZIP，
随后 closed、PID gone、mutable Flash release、历史/末帧和零 active lease 均核实。

## 部署事务进行中取消

额外CoreS3 PIR可见会话经1234条HTTP核验：先有限程序写入仅RAM中的VM nonce，
再提交262303B完整包。真实execution处于submitting/writing，已确认pad.dat完成
131072B后取消；最终仍未verified/published/activated，没有该execution START或
应用标记。随后实际新raw prompt的53B窗口与串口offset/SHA吻合，同PID/固件/VM
继续运行C包、官方编译MPY依赖和PIR false/true/false；UART/QOM/PNG、重放不重跑、
31成员ZIP与自动关闭前ZIP/历史/Flash/PID/零lease均通过。
此为包部署事务中的取消，不证明任何chunk恰好中断或tail字节是否全部写入；
last-confirmed per-file进度不是guest磁盘全部字节的原子观察。范围和原始请求见
`live-inflight/`；独立复核与生产探针分别保留，不能转授其它主机/固件或所有阶段。

## 宿主负控与边界

- 冻结源码全平台 1107 项、相关 runner 44 项通过；五个 catalog/coverage/profile/
  snapshot 检查通过。AST/compile 与产品 diff-check 通过；原始快照/REPL的3文件空白警告保留原字节。本机无 Ruff，未运行 Ruff。
- 原生 UART/prompt 协议、SQLite 并发/重放/恢复、取消/迟到结果、输入 drain、
  momentary 乱序与部分 QMP 失败、帧切换、shutdown/expiry/close、续租与分配、
  bulk/manual/cache 保留分别验证。宿主 mock 不继承为 guest 或硬件 PASS。
- 独立审查发现的 8 项协调器/HTTP 问题、输入校验污染及 retention 语义损坏
  漏根均保留原失败负控与修复后复验。保留旧算法的两个 momentary race 负控。
- 第一轮全平台日志混入审查期间新增的 retention 红测试及旧 snapshot，保留为
  失败记录；接受结论只使用源码冻结后的 `preview-platform-full-r2`。runner r1
  误指定不存在的 test module，修正命令后的 44 项通过，未修改测试来接受失败。
- 新接口无配置控制 token 时 503；幂等 key 不同内容、重复 header、stale epoch/
  generation、已过期输入、managed legacy mutations、坏输入和旧 Run 帧均拒绝。
- START 不等于应用 READY；interrupt-only 不清空全部 native/IRQ/timer/thread。
  `main.mpy`、保存开机、hotplug、SSE/后台采样、AIFlow target/事件接入和 GC 仍开放。
  Live sessions未识别managed，旧mutation会409、Run帧fence未接；UNIT-HOST-34 OPEN。
  retained closed/failed 也计入 128 Preview、每 Preview 256 Run 的固定上限。
- 本块无 C/controller 改动，完整外设矩阵 `NOT RUN`；物理硬件 `NOT RUN`。

## 复核入口

| 内容 | 入口 |
| --- | --- |
| 实际 PIR / Relay / 部署取消 | `live-pir/`、`live-relay/`、`live-inflight/` |
| 宿主协调器 / 原 UART 实现 | `host-coordinator/`、`host-runtime/` |
| 输入与保留 | `host-input/`、`host-retention-initial/` |
| 非作者审查与原失败 | `coordinator-independent-review/`、`coordinator-additional-boundaries/`、`retention-independent-review/`、`openapi-independent-review/`、`live-independent-review/`、`inflight-independent-review/`、`ui-boundary/` |
| 精确服务加载与回归日志 | `verification/` |
| 该次源码 | `source-freeze/` |
| 归档逐文件 size/SHA | `file-manifest.json` |

源码和原始 Markdown 以追加 `.txt` 保存，bytes 不变；固件/ROM/compiler 不归档。
本地测试控制 token 不入归档。敏感信息检查覆盖正文及 ZIP 成员中的密钥、MAC、
私钥、URL userinfo 和本次实际控制 token；该检查不代表通用隐私分类已经完备。

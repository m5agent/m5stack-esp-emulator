# 外部 Agent 源码 API 与首批 Unit

日期：2026-10-26。类别：virtual-device validation；hardware `NOT RUN`。
外部 agent-work-logs 按用户要求 `SKIPPED_BY_USER`，仓内证据保留。

新增 `POST /api/v1/firmware/uiflow` 后，外部 Agent 可以提交 UIFlow2 Python
文本，由服务在准入 reference 的真实 LittleFS 中打包，再以 firmware ID 和
caller-source SHA pin 创建可见 session、配置 Unit，并通过网页交互和
serial/frame/units/evidence 接口观察同一 guest/controller。调用方法见
[指南](../../unit-agent-api.md)及[API 契约](../../device-service-api.md)。

## 实际结果与来源

先 checkpoint `ca8245e`，再合入 `origin/main@f206175` 的 21 个提交，merge
为 `c53950a`；本批在隔离分支继续开发，没有覆盖主工作目录。
服务为 gen11，固定 Xtensa runtime：
`29d8f6ecdc83f4cbd2ca013291b05bc9ef44fb438a115b0ca97f7b5d46d8d28d`；
CoreS3 UIFlow2 base：
`1324f12d3ddd5392f47a9eff537f9ce0b01a8e6e36d829b6bd22cdf82d2c1264`。
每个 session 都有直接 PID/executable/worker 证明；固件、caller/effective
source、各文件、ZIP 和冻结工具 SHA 保存在原始响应及运行报告。

| 批次 | 实际路径 | 结果 |
| --- | --- | --- |
| [独立 Button 预检](batches/button-smoke-r1/batch-result.json) | 源码 HTTP、真实 Web 按下/释放、GPIO 和新串口 | PASS；1 session |
| [五例批次](batches/five-r1/batch-result.json) | Button、Relay、ENV III、RGB、Encoder；新源码固件逐例启动 | PASS；5 独立 session |
| [逐字指南](batches/guide-r1/batch-result.json) | Button；HUB + ENV III + NCIR | PASS；2 独立 session |

合计八会话、七种 Unit。HUB 为被动接线，验证的是拓扑及两个 leaf 的实际
I2C 数据面，不虚构 HUB 自己的 I2C 地址或事务。五例保留原 driver/probe
断言；RGB 独立重放完整帧→短帧不改灯色且 incomplete 递增→第二完整帧，
并检查真实 RMT threshold/refill/completion 计数。

指南的两个 caller payload 都只有逐字 `main.py`，没有本地构建或上传 BIN，
服务生成的 24-byte `boot.py` 单独标为 generated。caller CAS 不含该文件，
effective CAS 包含它。运行时指南全文 SHA 为
`ab01086d32920a3b47c98c8a2a5a39830539136fc06bc6eb89a48397f113f737`；
后续只更新结果说明，两个源码片段字节保持一致。Button 的 PRESSED/RELEASED
帧及 HUB 最终 `28.5 C / 61.0 % / 100800 Pa / 37.5 C` 原生帧已目视核对。
网页、QOM、串口和帧分别采集，不声明原子同帧或所有视觉状态通过。

每次写入前记录真实 serial cursor，检查后续 fresh guest 数据；HUB 两个 leaf
分别检查独立事务/读写/输入计数，输入其中一个不得改另一个的物理输入。
所有会话停止前下载 ZIP，随后 `purge=0` 保留历史和最后帧；owned PID 已退出、
mutable Flash 默认释放、服务 active session 数回到零。

## 契约、负控和检查

源码路径穿越、便利入口携带 kind、不支持主机、base SHA 漂移，以及 session
缺失/错误 source pin 均 fail closed。相同 image 可来自 generated/显式 boot
两种 caller 声明；source pin 会拒绝已被另一声明替换的 metadata，不误绑
来源。session 与 ZIP 只保存 hash provenance，不附源码正文。

HTTP 整个 JSON body 和 helper 解码后的累计源码分别限 1 MiB；还限制 128
个文件、每文件 256 KiB。JSON 转义/路径等也占 HTTP body；临时 HTTP fixture
验证过限请求在 builder 调用前返回 413 且不发布对象。LittleFS 不自动格式化，
原 VFS 资源与 VFS 外字节保留；独立 remount 后实际读回验证。

[源码独审](review/source-api/review.json)、[HTTP 限额审查](review/http-limits/review.json)
及[实际批次独审](review/live-batches/review.json)、
[指南独审](review/live-batches/guide-review.json)保留逐层复核结果。
`verification/` 保存测试和检查：初轮两项 generated snapshot 新鲜度失败，
中间轮发现原样归档 Markdown 被当成新文档产生索引/相对链接错误；后续刷新
快照并按源码数据保存原文，最终检查另存，不改写前两轮日志。

现有音频 fixture 曾在固定 100 ms 单次采样时失败；未改版复跑和附时钟诊断
均通过，原失败没有采样时钟，不能宣布其根因完全证实。本次仅把测试改成
2 秒内等待实际波形，门槛仍为 `peak > 0.001`，保留每次 wall/context time，
超时仍失败；正式 113 逻辑断言 + 15 浏览器检查通过。产品音频文件未变，
原失败、诊断和修改后结果均在[音频回归](verification/audio-regression/report.json)。

## 重放与边界

`harness/` 保存五例与逐字指南 runner；原始运行目录位置分别为
`.work/unit-agent-api-live-20261026/` 和 `.work/unit-guide-live-20261026/`。
恢复脚本到相应目录后按各自 README 使用 fresh 输出目录；指南还需同目录
`source_api_common.py`。`--check` 只离线验证保存的实际 HTTP、sourcepin、
guest/QOM、DOM、ZIP 和清理证据。功能重跑必须走本机 `/api/v1` 可见 session；
不使用直接 QEMU runner。本归档不提交固件、ROM 或运行时二进制。

原样捕获的 Markdown 以 `.md.txt` 存放，避免将其中旧相对链接当作当前位置的
导航。[路径清单](transport-paths.json)记录原名、存放名和未改变的字节 SHA；
恢复到原运行目录时按该清单改回文件名，再运行原始嵌套 SHA256SUMS/`--check`。
顶层 `SHA256SUMS` 则直接核对本归档实际存放的所有文件。

源码入口仅准入 CoreS3、AtomS3R、StickS3、StopWatch 的已知 reference；
本批实际执行只覆盖 CoreS3。四 reference 离线 compose 成功不等于其它三主机
guest PASS。无运行中 hotplug；未建模接线、GPIO 并联或重复 I2C 地址仍拒绝。
原 Buzzer.once/IR、PWM 初始化、其它 HUB 拓扑、跨主机和物理等价性保持原边界。
共享 runtime 最新完整矩阵仍为 66/67，Core2 IMU 单例复测不能拼成全量通过。
该 API 子块不关闭整个 `UNIT-01`。

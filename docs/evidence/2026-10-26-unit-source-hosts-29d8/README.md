# 三主机 Unit 源码 API 验收

日期：2026-10-26。类别：virtual-device validation；hardware `NOT RUN`。
外部 agent-work-logs 按用户要求 `SKIPPED_BY_USER`。

完成前一块提交 `0fe6a013b7ca040583339ef7827d4daf8e3810dc` 后，已正式
fetch 并尝试合并 `origin/main@f2061759897955e6017d4aa2a41bd5ba962c35b6`，
结果为 `Already up to date.`，工作树干净。随后从该 HEAD 全新准备并实际运行
九个源码会话；[同步收据](sync/receipt.json)及原始 fetch/merge 日志保留。

| 主机 | 实际源码 API 场景 | 原生 PNG / guest canvas |
| --- | --- | --- |
| AtomS3R | Button、Relay、ENV III，3/3 PASS | 128×128 / 128×128 |
| StickS3 | Button、Relay、ENV III，3/3 PASS | 135×240 / 135×240 |
| StopWatch | Button、Relay、ENV III，3/3 PASS | 466×466 / 468×468 |

逐例固件、reference、caller source CAS、session 和结果 SHA 在
[机器摘要](machine-summary.json)；实际批次在
[post-sync-r1](batches/post-sync-r1/batch-result.json)。三种 reference 各自固定
实际完整镜像 SHA 与分区布局；每例只有四个原 host probe Python 文件和一个
显式生成的配置，提交真实 `/api/v1/firmware/uiflow` 后以新 firmware ID 和
`uiflow_source_sha256` 创建可见 session，没有本地 BIN 构建或上传替代路径。
探针使用 reference 内原 `unit/hardware/driver` 模块，不上传、修补或重建驱动，
也不声称独立重建了这些 bundled driver 的上游版本。

原 `HOSTS`、`validate_case`、`validate_bundle` 保留。Button 的四次 Web
边沿与 guest IRQ counter、Relay 两种 guest GPIO 输出、ENV III 外部双芯片
扫描及两组温湿压输入均验证；板载 BMI270 identity 在初始化前后及外部操作后
继续从内部总线读取。每次输入保留新串口的下界和下一输入的上界，实际
DOM/HTTP、QOM、直接 PID/固定 `29d8f6ec…` runtime 与 gen11 worker 均绑定。
停止前取 ZIP，`purge=0` 保留 source/history/最后帧，mutable Flash 释放、
owned PID 退出，最后服务与 worker lease 均归零。

作者离线检查与独立作者审查在 `harness/`、`review/authoring/`；实际运行独审
随后收入 `review/live/`。根目录核验与原始日志放在 `verification/`，不会改写
原准备产物或原执行结果。网页、串口、QOM 和 framebuffer 分次采集，不声称
原子快照；显示可读性仅覆盖人工看过的捕获帧。

`copy-provenance.json` 逐文件保存原字节 SHA；捕获 Markdown 只改存放后缀为
`.md.txt`，对应关系在 `transport-paths.json`。恢复原文件名后可重放原嵌套
SHA；顶层 `SHA256SUMS` 直接校验归档存放名。未归档固件、ROM、运行时或
编译产物。以下命令只做公开归档离线核验，不依赖原 `.work` 运行目录：

```sh
PYTHONPATH=.work/py312 /opt/miniconda3/bin/python3.12 -B \
  docs/evidence/2026-10-26-unit-source-hosts-29d8/audit_archive.py --repo-root .
```

恢复 `harness/` 到 `.work/unit-source-hosts-expanded-20261026/`，将
`batches/post-sync-r1/` 恢复到该目录下的 `live-post-sync-r1/` 后，可按原 README
运行 `--check`。新的功能执行仍需显式 `--execute`、当前 source context commit
和全新输出目录，统一走 Device Service 可见 session；不复用旧会话身份。

这九例只新增三主机各 Button/Relay/ENV III 的源码运行证据；其它二十四种
Unit 不从 CoreS3 的选定场景继承。运行中 hotplug、ADC/Thermal 准入、原
IR/Buzzer、PWM 初始化、视觉/机械映射、共享完整矩阵和物理等价性仍按各自
Backlog 与门禁处理，未关闭整个 `UNIT-01`。

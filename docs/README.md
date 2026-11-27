# 文档导航与新鲜度规则

日期：`2026-11-27`

从[项目首页](../README.md)开始。这里按任务列出常用入口。
每份文档的职责、适用范围和复核日期见[完整登记](document-register.md)。

## 五分钟阅读顺序

1. [项目当前状态](project-status.md)说明已有能力和风险。
2. [项目 Backlog](project-backlog.md)是未完成需求的执行队列。
3. [自动项目快照](project-snapshot.md)列出设备、运行时、任务和文档统计。
4. [验证证据台账](validation-ledger.md)记录日期、原版固件身份、实际运行路径和结果。
5. [工程交接总览](engineering-handoff.md)、[工作流总台账](workstreams.md)和[代码地图](code-map.md)用于接手维护。

## 入口索引

| 任务 | 文档 |
| --- | --- |
| 浏览器体验与发布 | [Pages 部署](pages-deployment.md) · [浏览器运行范围](browser-runtime-feasibility.md) |
| 本地服务安装 | [部署与运行时资产](deployment.md) · [macOS 托管 Linux 审核 Worker](macos-linux-review-worker.md) |
| 创建会话、输入、取帧和取证 | [Device Service API](device-service-api.md) · [OpenAPI](device-service.openapi.yaml) · [后端迁移](esp32sim-migration.md) · [Arduino 文档和库缺陷](arduino-docs-defects-2026-11-27.md) · [虚拟设备功能测试](device-functional-test-workflow.md) |
| 审核原版或应用分段 BIN | [固件审查工作流](firmware-review-and-simulation-workflow.md) · [FirmwareManifest](firmware-manifest.md) |
| 确认模型、内存和控制器能力 | [设备适配矩阵](qemu-device-adaptation-matrix.md) · [运行时模型缺口](runtime-model-gap-register.md) · [统一设备运行时](unified-device-runtime.md) |
| 查 PSRAM、Wi-Fi、BLE 与 Worker 边界 | [Core2 native HCI](core2-native-hci-backend.md) · [网络模拟方案](network-simulation-plan.md) · [网络诊断](network-lane.md) |
| 在 macOS 上做无命名空间的同 guest 网络审查 | [控制固件与运行方法](../tests/network/review_sta_controls/README.md) · [证据](evidence/2026-11-24-review-sta-portable/README.md) · [驱动初始化与条件步骤](evidence/2026-11-25-review-sta-activity/README.md) |
| 验证 S3-watch 原版的 WPA2 热点和 HTTP | [执行用例](../tests/network/native_s3_watch_wpa2/README.md) · [原生对端设计](plans/2026-11-23-s3-watch-native-wpa2-design.md) |
| 主机、Unit 与物理引脚 | [设备目录](../devices/README.md) · [外设仿真架构](peripheral-simulation-architecture.md) · [设备与 Unit 研究](unit-research/host-runtime-compatibility.md) |
| 接入 Agent | [Skill 安装](../skills/README.md) · [Agent Skill 分发](plans/2026-10-29-agent-skills.md) |
| 构建、补丁与回归 | [测试入口](../tests/README.md) · [补丁索引](../patches/README.md) |

## P0 与模型缺口的权威入口

- 待办、依赖和验收使用[项目 Backlog](project-backlog.md)。
- 设备能力及其限制使用[项目当前状态](project-status.md)和[模型缺口登记](runtime-model-gap-register.md)。
- 测试条件、证据与发布批次使用[验证证据台账](validation-ledger.md)。

## 新鲜度台账

在[文档登记与复核](document-register.md#新鲜度台账)可查到所有当前与历史文档。
复核日期说明文字与项目入口最近对齐的时间。实际运行时间以对应证据为准。
旧记录通过原链接或固定提交追溯。

## 更新规则

维护者先读[仓库规则](../AGENTS.md)及[文档维护](AGENTS.md)，再按工作目录查看
[服务工具](../platform/tools/AGENTS.md)、[浏览器与模型](../platform/web/AGENTS.md)、
[设备目录](../devices/AGENTS.md)、[运行时测试](../tests/AGENTS.md)与[补丁](../patches/AGENTS.md)。

- 能力变化更新项目当前状态、首页及相关专题。开放验收条件写入 Backlog。
- API 变化同时更新接口说明、OpenAPI、实现和契约检查。
- 新验证追加到台账或专题证据，保留固件、运行时和输入输出的身份。
- 新增或复核页面更新文档登记。生成统计使用 `python3 platform/tools/project_snapshot.py --write`，再执行 `--check`。

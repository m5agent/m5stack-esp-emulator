# CoreS3 Unit 源码 API 扩展验收

日期：2026-10-26。类别：virtual-device validation；hardware `NOT RUN`。本归档只保存已结束会话及离线复核，不启动设备服务、guest、QEMU 或诊断编译。

本批 **25 个独立 session**：**22 个功能 PASS、1 个 Thermal 缺 fixture 负控 PASS、1 个原版 IR `REVIEW_REQUIRED`（单次协议 PASS、风险 OPEN）、1 个原版 Buzzer FAIL**。不能把后两例升级为原驱动 PASS。逐会话固件、caller source CAS、runtime、ZIP 和分类见 [machine-summary.json](machine-summary.json)。

与[首批 8 会话](../2026-10-26-unit-source-api-29d8/README.md)合并，累计 **33 会话：30 个功能 PASS、1 个负控 PASS、1 个 review、1 个 FAIL**；所选场景覆盖 catalog 中 27 种 Unit，其中 **25 种走原驱动，IR／Buzzer 两种走显式 custom caller 驱动**。这是确切 SHA 和场景的覆盖，不代表 27 种原版固件全面通过，也不代表跨主机通过。[root 独立计数](verification/root-count-audit.json)保存每个原始 result 的 SHA、分类和集合复算。

## 本批证据

| 批次 | 同一 session 的实际路径 | 分类 |
| --- | --- | --- |
| [sensors-r1](batches/sensors-r1/batch-result.json) | Color、ToF、NCIR、Heart、TVOC、Ultrasonic I2C、Thermal；原负控、guest I2C 数据与输入变化 | 7 功能 PASS |
| [controls-v2-r1](batches/controls-v2-r1/batch-result.json) | Joystick、8Encoder、CardKB、RFID V2；原完整控制断言及明确的 display-only CoreS3 profile | 4 功能 PASS |
| [io-default9-r1](batches/io-default9-r1/batch-result.json) | PIR、Dual Button、Limit、Key、Angle、Light、Fan、RS485、HUB | 9 功能 PASS |
| [custom2-r1](batches/custom2-r1/batch-result.json) | IR callback GC 引用与 Buzzer SoftTimer 参数适配；仅生成的 caller wrapper 副本变化 | 2 custom 功能 PASS |
| [thermal-negative-r1](batches/thermal-negative-r1/batch-result.json) | 无 raw fixture 时真实 I2C NACK，禁止温度输出，QOM raw-fixture-ready=false | 1 负控 PASS |
| [original-risk2-r1](batches/original-risk2-r1/batch-result.json) | 原 IR forced-normal-GC/RMT 路径单次协议成功；原 Buzzer natural timer zero 未在 TIMER_DONE／手动输出前出现 | IR REVIEW_REQUIRED / Buzzer FAIL |

每个运行都使用真实 `POST /api/v1/firmware/uiflow`，随后携带 caller source SHA pin 创建可见 session；保存真实 Web 操作、DOM/HTTP 读回、guest 串口、控制器／QOM 和原生 framebuffer。停止前请求 evidence ZIP，之后 `purge=0` 保留 history／最后帧，释放 mutable Flash，并检查 owned PID 退出、service session 与 worker lease 归零。固定 runtime 为 `29d8f6ecdc83f4cbd2ca013291b05bc9ef44fb438a115b0ca97f7b5d46d8d28d`，本批 worker generation 11；CoreS3 base 为 `1324f12d3ddd5392f47a9eff537f9ce0b01a8e6e36d829b6bd22cdf82d2c1264`。

普通传感器各自保留 initial 加两次输入变化；Thermal 保留原 raw-frame initial 加一次变化、768 个有限值和九点。CardKB 独立复算 187 字节、401 个输入步骤和 413 次 Web POST；三组真实双击均锁定、解锁。RFID V2 每个 4／7／10 字节 UID 的全部正负控必须在当前输入到下一输入的封闭 fresh 窗口内完成，禁止跨 UID 借用 marker。8Encoder 保留有符号 int32 边界、set/reset、0x42 地址、八路 increment 和九组 RGB 寄存器。Angle 绑定合成 ADC fixture 和原曲线 oracle；Light 证明 raw/digital，不继承 read_uv 结果。Fan 的五个 100% duty 样本仅证明 2.532 秒采样区间内图形角度活动，不证明全部阶段、转速或实物旋转。

[独立审查](review/final/)保留准备脚本和 terminal 批次的复核，包括 [IO9](review/final/io-live/review.json)、[controls4](review/final/controls-live/independent-actual-evidence.json)、[sensors7](review/final/sensors/offline-review-results.json)、[custom2](review/final/custom/review.json)、[原 IR 风险](review/final/original-risk/review.json)及 [Buzzer 失败说明](review/final/original-risk/original-buzzer-note.json)。退出 PID 不能离线重新采样；重放核对的是执行时 direct-PID 记录及实际 stop/history/idle 响应。

## 研究与开放边界

[上游复核](research/upstream/README.md.txt)固定官方 commit `3a86d8f611b3639cca755a933e01a5a829771ef1`，保留公开源码、fetch receipts、SHA、最小 patch 和比较结果。所检查源码仍具有 Buzzer callback 参数不匹配及 IR callback 未保活模式；源码研究没有运行最新发布固件。原 IR 的本次单次成功不关闭历史 GC lifetime 风险，custom PASS 也不转授原 wrapper。

[LED 公开研究](research/led-placement/report.md.txt)、[findings](research/led-placement/findings.json)和[公开来源](research/led-placement/source-index.json)保持 U003／U135 电气序号到物理位置映射 `OPEN`／`null`。Encoder 照片相对冻结模型位置的定性差异单独记录，不校准左右电气顺序。只归档公开报告、公开官方资料及收据；`internal/`、MCP 原始请求／反馈标识、客户端和无关照片整树排除。原研究 checker 含内部反馈核对依赖，原样保留为历史源码；公开子集由本归档 audit 独立核对，不需要该内部依赖。

[GPIO／LEDC route 诊断源码](host-pwm-route/diagnostic.c)及[历史 receipt](host-pwm-route/receipt.json)复现宿主 C fragment 的路由写入与 observer 顺序缺口。此归档不包含、不编译或运行该诊断 executable；离线片段结果不是 guest runtime PASS，也没有实施修复。

## 原样运输和重放

`harness/` 保存四类实际 runner、common、contract、fixture、patch 来源及 CLI 说明；每个 batch 的 `source-request.json`、caller `.py`、source snapshots、原始 HTTP 和 serial 都保留原字节。服务 compose 需要受准入的 reference firmware／runtime，它们的 hash 已保存，二进制不入仓。

在相同 repository/context 中，把 `harness/sensors`、`harness/controls`、`harness/io`、`harness/custom` 分别恢复到 `.work/unit-source-sensors-expanded-20261026/`、`.work/unit-source-controls-expanded-20261026/`、`.work/unit-source-io-expanded-20261026/`、`.work/unit-source-custom-io-20261026/`；batch 证据恢复到原相对运行目录。按各自 README 使用新的 output 目录。离线 `--check` 不触网；原版 IR/Buzzer 的 review/FAIL 由其独立审查重放，不能给原 runner 强行改 PASS。实际功能重跑仍须显式选择本地 Device Service 可见 session。

除本 README，捕获的原始 Markdown 均运输为 `.md.txt`，原内容不清洗、不重写链接。[transport-paths.json](transport-paths.json)记录原相对名、新名、原 SHA 和 `byte_changes=false`。恢复文件名后可以复核原嵌套 SHA 清单；本归档顶层 SHA 清单直接对实际存放名。[copy-provenance.json](copy-provenance.json)逐文件绑定来源和字节 SHA；[exclusions.json](exclusions.json)记录整份私有／可执行输入的省略，不隐藏原清单对省略文件的引用。

执行以下命令只读审计本归档（需要 Pillow；不调用 API／guest／编译器）：

```sh
PYTHONPATH=.work/py312 /opt/miniconda3/bin/python3.12 -B \
  docs/evidence/2026-10-26-unit-source-api-expanded-29d8/audit_archive.py
```

追加 root 的平台／generated 检查原始日志后，用同一脚本 `--write` 更新 [audit-report.json](audit-report.json)及顶层 `SHA256SUMS`。`verification/unit-tests-final.log` 是 194 项 Unit 离线 package／准备测试记录；这些测试会生成本地临时镜像，但镜像未归档，不增加功能会话或跨主机运行结果。root 后续验证另存，不改写原始日志。

共享完整矩阵、跨主机、真实光学／声学／机械／电气行为、物理等价及整个 `UNIT-01` 工作流均保持各自门槛；本批实际执行仅限 CoreS3 源码 API。

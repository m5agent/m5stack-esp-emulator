# S3 LEDC 读回与 Buzzer 浏览器试听

日期：2026-10-26。类别：virtual-device validation；hardware `NOT RUN`。
外部 agent-work-logs 按用户要求 `SKIPPED_BY_USER`；仓内证据继续保留。

## 结论与范围

`0037` 为现有即时 duty 模型补 ESP32-S3 DUTY/DUTY_R 低 19bit 读取。
固定公开源码、七层 patch 冷构建得到 Xtensa
`29d8f6ecdc83f4cbd2ca013291b05bc9ef44fb438a115b0ca97f7b5d46d8d28d`；
旧 `a8fe15db…` 未覆盖。106 个源文件与独立七层正反重放一致。
这只关闭已完成 set+update 并稳定采样的 getter 缺支；pending/current-cycle、
latch、fade、其它时钟来源与物理时序仍未建模或未验证。

| 验证 | 结果 | 证据 |
| --- | --- | --- |
| 同 SHA guest 的 getter/MMIO A/B | PASS；两边固件均 `3ce76c8033131c6e0773406475c4b7342ae5f46d1e22240d690e6e61f9bba251`，各 60 sample、480 channel raw | [基线](getter/baseline/report.json)、[修复后](getter/readback/report.json)、[独审](replay/getter-independent-review/review.json) |
| 原始 getter | 六档均 0；QOM 有真实六档输出 | [严格分析](analysis/baseline-analysis-r2.json) |
| 修复后 getter / DUTY_R | 0、16384、32768、49152、65535、0；resolution=13，整数计数 0、2048、4096、6144、8192、0 | [严格分析](analysis/readback-mmio-analysis-r1.json) |
| 浏览器试听 | PASS；真实 GET/QOM 驱动原生 AudioContext，六档、默认静音、用户启用、停止关闭；无额外产品 POST | [运行报告](audio/pass/report.json)、[浏览器 receipt](audio/pass/audio/receipt.json) |
| 最新完整矩阵 | FAIL：66/67 case，270/274 check；Core2 IMU frame marker 缺失 | [原始完整轮](regression/full-r1/cases/summary.json)、[聚合](regression/aggregate.json) |
| Core2 IMU 单独复测 | PASS；与完整轮分别保留，不能拼成一次全量 PASS | [独立复测](regression/targeted-core2-imu-r1/summary.json) |

A/B 每边独立绑定实际 PID、可执行 SHA、固件和 worker generation（9/10），
停止前取 ZIP，`purge=0`，Flash 已释放、PID 已退出。getter 量化按真实 timer
resolution 判断，没有用 host 赋值补读数。97 条 QOM 中，基线仅 76 条、修复后
仅 75 条落在同 sample 的 1..8 稳定窗口；各 4 条 phase-only 过渡均被排除。
原始全部观测保留。controller、浏览器、ZIP 和历史的帧分别采集，不作原子同帧声明。

## 试听固件与失败尝试

试听通过使用单独固件
`43e0be7bad319a9f76f7efcd0583d0f3397b626997ad28bc2e60dc7473c87deb`：
PWM 构造后显式执行一次真实 `duty_u16(0)`，再保留 20 秒静音准备窗。
固件、源快照和 flavor 均与 getter A/B 分开。这不关闭原发布 Buzzer.once 的
callback 问题，也不代表实物音色、声压或短于 500ms 采样窗的所有脉冲都能试听。
本轮只验证固定 2000Hz 下占空比变化；动态频率另有 fixture 检查。
浏览器验证静音输出 sink，检查实际原生音频节点/波形及生命周期，不测量扬声器。

`attempts/` 保留输出目录拒绝、漏首零/终态异步误判，以及初始化 QOM 为 0Hz
导致固定频率断言失败的尝试，结果均保持 FAIL。初始化 READY 后 QOM 仍未刷新
的现象单列 [UNIT-HOST-20 原始核验](audio/harness/initial-qom-observation-review/receipt.json)；
显式 setter 是此 custom 诊断的可见步骤，不是对旧证据的修补。

## 可复现入口

[七层重放 receipt](replay/receipt.json)、[冷构建 manifest](build/build-manifest.json)、
[源码冻结](build/freeze.json)、[实际服务切换](service-transition/receipt.json)、
[官方资料与实现](implementation/final-source-inputs.json)、[解析器](analysis/analyze.py)
和各运行的 source-snapshot 均保留。运行时/ROM/固件镜像不入库；原文件哈希仍
保留以绑定输入。功能重跑必须使用 Device Service `/api/v1` 可见会话；
`regression/` 是仓库共享控制器回归，允许直接 runner，不能冒充产品 Live session。

完整回归门禁仍开放。此子块不关闭 Unit 全批次、其它主机、原固件风险或真机验证。

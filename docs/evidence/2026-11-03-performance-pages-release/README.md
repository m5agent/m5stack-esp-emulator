# 性能优化合 main 与 Pages 更新

日期：`2026-11-03`。类别：**browser virtual-device validation**；物理硬件 NOT RUN。

性能优化 [PR #163](https://github.com/m5agent/m5stack-esp-emulator/pull/163)
合入 `189dc01a5ee42a23ac7e246f8390c2acfe471ffa`，构建路径修复
[PR #164](https://github.com/m5agent/m5stack-esp-emulator/pull/164)
合入 `10788607feefb9e532c2dd1fe4679adcd6aa0fc2`。
新构建源 `1b86ed6f7edcc36deafc4834b45a28c6a6017c79` 与后一个 merge 的
Git tree 均为 `9158da43530d82d0eaf5472eff15f831e82666e8`。
保留单一 C/QEMU/TCI，没有引入实验 JIT 或第二套 SoC 后端。

## 新运行时的完整本地门禁

同一项目子路径导出的 **19 板、20 固定示例、552/552 检查全部通过**。
22 个 VM 的 102 个 pthread 和 22 个 engine target，合计 124 个实际 CDP
目标均在各自正常 Stop 的两阶段门禁内归零，fallback 为零。
逐例固件 SHA、真实输入、原生帧/模型纹理、LED 控制器、暂停恢复及 source/runtime
绑定见 [admitted-summary.json](admitted-summary.json)。它是功能回归，不是十九组提速测量。

原始 wrapper SHA：`8281af8207f2b036eb33f0269e28adc880a5a650d7968e592c974c1a47617d95`。
安全摘要 SHA：`947ae11865a4659e7bd6453ba2ba7e6e130f5f766501a9139efca484d625f054`。
原始日志、帧序列和运行标识保留在 ignored 输出，不随源码分发。

## 发布身份

| 项目 | SHA-256 |
| --- | --- |
| 站点 manifest | `c5991d737d4b20c4b1ae96b71587cec907a1e72f3c57fe2fee63c08e23daf323` |
| runtime manifest | `897114f09d5e0c695e44e665611fec4fa98aa62856cddce6eb1cbb906d21071c` |
| WASM | `3c6b249002d83118e0ddcbd82e4ee6336223293b98566fc7709d5087d9df4567` |
| 对应源码包 | `3bf6ee4fe907aff960ace53ae4622356345960055e0cb1cc1dee964ff6fc09b0` |
| source lock | `b9b137e52e77078cc67cb5b25433622f62d70cc3cbed8f92ee6699eed3389a1b` |
| producer recipe | `f69cd135c8d5bb6c1efe920eb2ec54070798267b304c1333b9397fbde18770fc` |
| prepared tar.gz | `d4be918692aa7d63cdf6f6360da2cfc2c3337b2f07ad96fce011f1d3bfe2fe4a` |

构建使用固定 Emscripten 3.1.50，8 个依赖与 QEMU 全新构建，保留 72 补丁和
160 个源文件 postimage。编译器路径映射、GLib 逻辑安装路径及依赖策略在生产者端
消除本机路径，没有事后改写 WASM。旧 `0bd94787…` 因路径问题撤回，部分四例不作
新包准入；新包重新执行完整门禁。构建与实际 Cardputer-ADV 证据见
[固定 producer 记录](https://github.com/m5agent/agent-work-logs/blob/2c4f5fcf9469ac8f6935a29359489003705cc76e/records/esp-emulator/2026-11-03-qemu-producer-paths/report.md)。

## 正式流程的保留失败与边界

正式 [run 41617152984](https://github.com/m5agent/m5stack-esp-emulator/actions/runs/41617152984)
使用另一 WASM `e9d10ae8…`；构建、ABI、Canvas 控制通过，第三个 CoreS3 e950
案例的 engine target 超时未消失，因此 gate FAIL、部署 SKIPPED。
该次 guest exit0、五个 pthread 关闭和 normal owner 确认均不替代 engine 回收，
context teardown 才消失也不能反填 PASS，见
[独立失败摘要](regular-ci-failure-summary.json)。根因仍未定位。

本轮采用已有的 prepared-preview 应急流程；它不授予 hosted regular publication
PASS。官方 Factory 浏览器 WDT/异常、任意固件兼容性、长期稳定性及物理属性仍未关闭。
历史性能测量保留自己的运行时、配置与缓存条件，见
[前一阶段性能证据](../2026-11-03-emulator-performance/README.md)。

## 部署后真实 HTTPS 固件结果：PARTIAL

[prepared 部署 41629045946](https://github.com/m5agent/m5stack-esp-emulator/actions/runs/41629045946)
成功，上传的三个资产重新下载逐字一致。正式地址为
[公开模拟器](https://m5agent.github.io/m5stack-esp-emulator/)。
[交付摘要](release-summary.json)与 [HTTPS 回读](https-readback-summary.json)记录实际
48 次 GET、49,173,223 bytes，全 200、无重定向，与冻结出口相同；只核验这 48 个路径，
没有把 manifest 声明的 2,127 个资产全部写成线上逐项下载。

随后从该 HTTPS 地址依次执行，未启动本地服务或替换后端：

| 固件与阶段 | 实际结果 | 证据 |
| --- | --- | --- |
| CoreS3 原始 `78961297…`，两 VM | 49/49；真实 touch/PIR、四次 typed 双 ROI、帧及正常退出通过 | [CoreS3](online-cores3-summary.json) |
| StackChan 默认 `407f6260…` | 24/24；原触摸/串口计数、frame/texture、暂停恢复及正常退出通过 | [默认示例](online-stackchan-reference-summary.json) |
| 原始跳舞 `c854d3ac…`，两次 20 秒窗口 | 两轮通过；ready `5.320070/3.982515 s`、首非黑 `5.337945/3.998710 s`，像素更新 `26.696/26.348 /s`；UART 包增量 `169/166`、位置变化 `163/161`、cue `30/30`，真实 render 绑定通过 | [跳舞](online-dance-summary.json) |
| 同 `c854d3ac…` 的独立 8 秒触摸阶段 | **启动 FAIL**：ready 前 Core1 `LoadStorePIFAddrError`；没有帧或输入，触摸及严格 derive **NOT RUN** | [首次失败](online-touch-startup-failure-summary.json) |

[四阶段总摘要](online-summary.json)绑定全部 runtime/source/firmware、原始报告 SHA、
实际执行的工具与资源回收；其 SHA 为
`394a4f86f95ccb85aaafe0427a7fa3ba7d639ef1c277afe71c63d531abae7d15`。
六次 VM 尝试的 36 个 QEMU Worker 目标均正常归零；失败启动的资源回收通过
不能转成固件功能通过。没有普通重试、没有借用旧 R6 触摸结果，也没有把默认
`407f…` 的输入和 `c854…` 的跳舞拼成一个固件的完整 PASS。

失败的 PC `0x40001c38`、EXCCAUSE `0x0f`、EXCVADDR `0x40001c34` 均保留；
两个 reset 通知不是两次独立重启。故障发生在启动早期，120 秒是 ready 等待超时，
不能解释成网络加载时间。根因尚未确定，不能直接归为此前的 PSRAM/OOB 事件，
也不能声称已证实不是回归。

首次观测表示新 browser/guest/module；预校验会预热 CDN，不是冷网络。线上时序
不能和旧本地 R6 当作同网络条件的 CPU 比率。像素更新不是完整应用 FPS；各窗口
的最大 frame/render/state 间隔仍完整保留，不能据平均或 p50 宣称全程无卡顿。
CoreS3 的 `557.5/562.47 ms` 只是回调后检查点到首次匹配 ROI 的观察间隔，
不是精确 input-down 或 guest-callback 延迟；原 650 ms 手势协议保持不变。

## 复现

固定 producer 源与完整配方见上述 producer 记录；完整本地门禁使用
`platform/tests/test_public_qemu_admitted_boards.mjs`，以项目子路径导出、系统 Chrome
和 `M5_WASM_GPU=hardware` 执行。它验证本次 artifact，不能用 native 结果替代。
线上 CoreS3 使用原 `platform/tests/test_public_qemu_guest.mjs`、
`M5_PUBLIC_URL=https://m5agent.github.io/m5stack-esp-emulator/` 与
`M5_QEMU_EXAMPLE=stock-reference`。后三阶段使用精确保留原算法和断言的
HTTPS transport adapter，来源、父文件及全部 15 个文件 SHA 写入四阶段总摘要。

新 producer 的 19 板固定功能门禁通过、两 PR 合并、部署和资源回读已经完成；
线上同一跳舞固件的启动稳定性及独立触摸证据仍为 PARTIAL，按项目 Backlog
继续，不将本次交付写成整个性能/兼容工作流完成。

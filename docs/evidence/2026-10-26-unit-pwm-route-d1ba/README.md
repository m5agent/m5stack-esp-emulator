# PWM 初始化路由修复与完整回归

日期：2026-10-26。类别：virtual-device validation；hardware `NOT RUN`。
外部 agent-work-logs 按用户要求 `SKIPPED_BY_USER`。

`0038` 修复 GPIO matrix 路由建立后未刷新 Unit PWM 观察值的问题：路由变化时
只重算现有 LEDC 寄存器，按相同 SoC 布局通知端点，不重放 MMIO 写入、不由
Python 补造 Unit 状态。独立冷构建、八 patch 正反重放和18组实际C片段通过。

| 同一固件、无后续 PWM setter | 旧29d8 / gen11 | 新d1ba / gen12 |
| --- | --- | --- |
| 实际 Unit QOM，8个新鲜串口夹窗 | 0Hz / 0% | 2000Hz / 0% |
| guest 只读 getter | 2000Hz / 0% | 2000Hz / 0% |
| 初始化结论 | `FAIL_REPRODUCED` | `PASS` |
| 实际 Web actions / Unit input POST | 0 / 0 | 0 / 0 |

固定固件 SHA 为
`81187ab008f53f2dd6385110fba727f4ee340be8a49e0fa05e19106d1a7fda11`，
caller/effective CAS 为
`9466b7607d32aea64bc0cfdb704d950d2a42bb6d24ef593609a567f94b82478b`。
请求、五个caller文件及派生固件相同，运行时分别为
`29d8f6ecdc83f4cbd2ca013291b05bc9ef44fb438a115b0ca97f7b5d46d8d28d` 与
`d1ba0063f80f6f8bdeeaa831f0d16ce4004ff3692a2d0587663e121bb93f45ff`。
真实源码入口、source pin、直接PID/worker、HTTP/DOM、新串口与QOM、停止前ZIP、
history/最后帧、Flash释放和owned PID退出均留证并通过独审。
[旧轮](acceptance/baseline-r1/result.json)、[候选](acceptance/candidate-r1/result.json)、
[机器摘要](machine-summary.json)保存精确身份。

共享控制器的仓库回归先通过CoreS3设备组7/7，再单次通过原完整矩阵
**67/67 case、274/274 assertion**，无重试、未拼接targeted结果。
[完整原摘要](regression/full-r1/summary.json) SHA为
`0d518bee9a554c91f185fe55d78728639aa604b5072fe3f94eb6f97a08ed5d91`。
独审重算388份冻结输入、204份最终Python源码、134份PNG/PPM与PCM/RMT/SD等
数据面证据。Core2 IMU原完整轮的after.ppm实际绿色，旧29d8的66/67不改写，
偶发根因不因此关闭。[回归独审](review/regression/review.json)。平台652项
全通过、零跳过及四generated checks通过；旧候选日志的22skip/2snapshot失败
仍保留。[根环境测试结果](candidate/root-platform-tests.json)。

结果只覆盖实际采样与捕获帧：每组8窗口约4秒guest时间，位于60秒hold内，
不代表整个60秒或上电首瞬间连续覆盖。候选 `output-transitions=1` 是属性变化
计数，不是物理PWM脉冲；generic ZIP的QOM受node limit限制，逐窗口frequency/duty
来自冻结UnitRegistry的真实 `/units` 查询。原Buzzer.once、完整周期/latch/fade、
其它固件和物理声学/电气行为不继承。

完整矩阵起始有388份source hash和预期Xtensa pin及既有冷构建manifest，但没有
完整all-ROM/C6全轮起始freeze；中途、C6阶段前及终态观测按真实时点分别保留。
PaperColor RGB原summary.command被WS2812 checker覆盖，profile命令仅能按冻结
源码静态重构，不能称实际launch trace。六个IR例最终mutable Flash hash与stdout
初始hash不同，最终Python源码逐字相同，未推断具体改写原因。

原始证据逐字节复制；捕获Markdown仅改运输后缀为 `.md.txt`，由
`transport-paths.json`恢复。`copy-provenance.json`、顶层SHA及原嵌套SHA可核对，
`omissions.json`记录每项省略的hash/size；固件、ROM、Flash镜像与编译产物不入库。
PCM、RMT和binary servo UART完整保留，PPM只在与PNG逐像素一致时省略。
独立只读审计不需要原 `.work`、设备API、QEMU或编译器：

```sh
python3 audit_archive.py --archive-dir .
```

在本归档目录执行，需Pillow；`--repo-root`可额外比较仍存在的原件。

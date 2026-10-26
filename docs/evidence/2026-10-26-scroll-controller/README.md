# Scroll 限定控制器与真实 Web 闭环

日期：2026-10-26。限定范围：**virtual-device validation PASS**；完整共享矩阵 **66/67，未全绿**；hardware validation **NOT RUN**。
本块承接`662ca4e4`同guest文件包，不改变其入口/字节码边界。功能测试全部经过8787可见Device Service session；直接runner只用于仓库控制器回归。

## 实现与固定来源

独立`CONTROL_SCROLL`经主机GPIO matrix、I2C控制器和实际I2CBus执行，不复用Encoder协议。
内部FW固定`ae60717a4b9315cd12ac56389992fc2b7576d0aa`，UIFlow固定`3a86d8f611b3639cca755a933e01a5a829771ef1`。
[来源与callback oracle](build-and-audit/audit.json)和[范围审计](build-and-audit/audit.md)保留寄存器、原API和未闭合链路。
原driver getter读4字节但暴露低16位；setter仅Python偏移，未改写成I2C setter。

`0043-unit-scroll-controller.patch` SHA256为`03f34ee350be9d7fade560c3fe94ed8e6914209350348dd44c8ac4ef4d1c16ea`。
从固定公共QEMU与九patch建立全新源码/构建目录，[冷构建](build-and-audit/build-manifest.json)、
[106文件比较](build-and-audit/unit-scroll-final-build-comparison-20261026.json)、
[source check](build-and-audit/unit-scroll-final-source-check-20261026.json)与真实forward/reverse检查均保留。
相对旧d1ba源清单，只有`m5_unit_i2c_controls.c`变化；现役旧binary未被覆盖。
最终Xtensa运行时SHA256：`b8de32a39be06162ae8ce8529b218370038936059dba067b9a7109a470e067d2`。
离线实际C片段6组和3个故意错误负控通过，不把这些离线检查称为guest PASS。

## 最终可见会话

| 范围 | 结果与证据 |
| --- | --- |
| Scroll四主机 | [独立新cohort](hosts/provenance.json)：CoreS3、AtomS3R、StickS3、StopWatch各22次有限程序，共88次，同PID/固件/worker/VM nonce；[逐例](hosts/) |
| 原驱动与raw I2C | count/int32部分写与低16位getter、Python setter偏移、有限TX循环与跨STOP/跨程序续读、选择增量即snapshot/清零、旧snapshot保留新增量、reset保留物理source、AB/物理方向、按键、静态RGB、改址/恢复及恢复应用帧 |
| 明确拒绝 | 大步/域越界/int32溢出不变状态；混合source+pressed请求400在任何QOM写前拒绝；FC/FD/地址0缺口不伪造bootloader或成功改址。完整帧callback error不冒称wire NACK |
| CoreS3真实Web | [最终cache入口](web/report.json)：原ScrollUnit无限loop；可信canvas按放、源计数3/-2四次单字段POST，5个fresh UART窗口；原guest RGB写回实际mounted Led material/glow，实际PNG采样像素进入mounted Display；[按下截图](web/pressed-browser.png) |
| 零回声 | Web 1600ms观察13次共享frame读取，无新增物理事件或POST；不把有限观察推断为无限时间或所有客户端保证 |
| 旧控制器回归 | [四主机Encoder/8Encoder/Joystick](controls-regression/provenance.json)各5次预期execution结果，含故意错误与恢复，限定HUB拓扑与原driver；不关闭Encoder默认灯位/轴角binding的UNIT-HOST-29 |
| 取证与收尾 | 每个自有会话先ZIP再`purge=0`，history/末帧保留、Flash释放、owned PID退出，见[独立收尾核查](cleanup-verification.json)；[ZIP成员/大小/SHA](zip-index.json) |

真实Web对实际PNG做全图颜色比例检查，并对模型屏幕的3个对应坐标核RGB；不是全framebuffer逐字节等同性。
只读字段拒绝、两种销毁顺序、迟到响应、完整canvas framing等额外负控属于[7组无guest fixture](visual-fixture/report.json)，
不冒充真实guest故障注入。旧入口Web报告另存[web-before-cache](web-before-cache/)；最终`20261026f`入口单独新会话通过。
88次Scroll程序只覆盖上述正常操作/显式缺口；中断清理仍不保证native、IRQ、timer或thread完全清场。

## 部分模型边界

物理`source-count`限定[-32768,32767]，对应TIM16=0x8000+source且不rollover；单事件差分≤32767，
logical count/increment的int32溢出明确拒绝。guest counter写入/reset不移动物理source，也不伪造轴动画。
原固件TIM3 IRQ/NVIC可达性与AB反转后的wrap补偿未闭合，不能换成理想modulo并声称等价。

RGB为同步quiescent/latest-value子集。官方固件写入当前多槽队列、推进index，main loop才显示并重置index，
保留各槽旧内容。因此burst、跨槽partial与LED调度未模拟；partial oracle只在slot0静止复用前提下成立。
没有可靠count/方向→机械角度标定；bootloader版本/执行、配置Flash持久化、地址0单播及真实电气/机械均未完成。
`implemented`仅表示实现可准入，`model_completeness=partial`保持；不会因静态RGB和按钮通过而关闭完整Scroll。

## 完整矩阵与保留失败

[新独立完整轮](regression/matrix-r2/cases/summary.json)为66 PASS / 1 FAIL、270/274 checks。
Core2 IMU串口已有目标accel/gyro，实际PPM成功marker仍黑；已有UNIT-HOST-21继续OPEN。
[同参数旧d1ba/新b8de各一次A/B](regression/core2-imu-ab/report.json)均为绿帧PASS，只说明本次未重现，
不确认根因或修复，不拼回原完整轮。旧probe本来只门禁x/y；旧A/B最后gyro-z=0，新与原完整轮为30，差异单列保留。
原完整结果、二进制、ROM、输入和工具前后hash不变；无重试、无改阈值。独立C6使用自己的runtime/ROM收据。

[第一完整轮](regression/matrix-r1-infrastructure/)因child加载3.9 ABI LittleFS依赖而全例基础设施失败，
没有QEMU/guest执行；原67 FAIL摘要未改写。第二轮显式固定3.12依赖后才得到上述66/67。
[早期Scroll](earlier-attempts/)也保留旧verifier/初版probe，以及全局source版本256配额导致的429中断；
最终四主机全部来自新cohort，没有把旧CoreS3 PASS拼接进新批次。

source容量现可显式配置1..4096，默认256、满额仍429，不自动删除源码；本地测试以1024启动，
原256记录逐一hash保留。[配置测试](verification/program-revision-config-tests-final-20261026.txt)与服务启动收据分别核验。
自动引用保留/有界回收仍OPEN；包存储与guest staging的独立配额没有被绕过。

## 重放与文档

```sh
PYTHONPATH=platform/tools:platform/tests:tests/units:.work/py312 python3.12 tests/units/run_live_scroll.py \
  --execute --device cores3 \
  --expected-runtime-sha256 b8de32a39be06162ae8ce8529b218370038936059dba067b9a7109a470e067d2 \
  --out-dir /tmp/m5-scroll-new
```

其它主机分别替换device，不继承CoreS3接线/结果。默认不加`--execute`无HTTP或guest副作用。
真实Web显式`M5_UNIT_SERVICE_E2E=1`，并设置`M5_EXPECTED_RUNTIME_SHA256`、新`M5_SCROLL_LIVE_BROWSER_OUT`运行
`platform/tests/test_live_scroll_service_browser.mjs`；纯fixture另用`M5_SCROLL_VISUAL_OUT`。
源码冻结、最终验证与仓内索引见[source-snapshot.json](source-snapshot.json)、[verification.json](verification.json)。
原始HTTP逐往返留本地`.work`；归档保留独立报告、源码、串口ZIP和帧，不包含firmware/ROM/compiler binaries。
外部agent-work-logs按用户指示SKIPPED_BY_USER；本块不授予Preview/SSE/AIFlow接入、SLA或真机结论。

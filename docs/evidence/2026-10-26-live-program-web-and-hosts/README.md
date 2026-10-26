# UIFlow 直接创建与同 guest Web 实时编程

日期：2026-10-26。分类：**virtual-device validation PASS**；hardware validation **NOT RUN**。
本批通过本机 8787 Device Service 创建可见 session，未直接启动 QEMU。

`program_mode="uiflow-live"` 从准入 reference 一次初始化 UART REPL；之后源码通过
`POST /sessions/{id}/program` 在该 guest 内编译执行。每次修改不重组固件、重启
guest 或替换设备进程。手动 composer/bootstrap 入口仍兼容。程序替换是
interrupt-only，不保证 native 模块、IRQ、timer 或 thread 完整清场。

## 范围与证据

| 验证层 | 结果与入口 |
| --- | --- |
| 四主机实际 guest | CoreS3、AtomS3R、StickS3、StopWatch 各自 PIR/Relay，共8组合、40次程序；[cohort](cohort.json)、[逐例目录](hosts/) |
| 最终 runner 收尾复核 | AtomS3R + Relay 另5次程序；[report](runner-final-check/report.json) |
| 真实产品 Web | CoreS3 + PIR/Relay 两例，真实页面创建/提交、输入/输出、实际 guest PNG 到模型屏幕、SyntaxError 与恢复；[report](browser/report.json) |
| Web 并发与布局 fixture | 13组程序面板与实际页面编排回归；[report](web-fixtures/report.json)、[截图](web-fixtures/sessions-program.png)，此层不执行固件 |
| picker 负控 | 修复前切换主机发送旧 `custom` 端口，实际409；[原报告](negative-control/picker-before-fix.json)，对应 `UNIT-HOST-27` |
| 取证与停止 | 停止前11份 ZIP；[成员与SHA](zip-index.json)，[历史保留/Flash释放/原PID消失](cleanup-verification.json) |

每个 host case 在同一 PID/固件内执行：有限 VM nonce、无限循环 A、替换 B、
故意 SyntaxError、恢复程序。nonce 放入 VM 内存的 `sys.path`，后续程序核对；
新 globals 不等于新 VM。PIR 从显式 false fixture 开始，逐次以新串口 offset
验证 true/false/true；Relay 由固件自带 `RelayUnit` 写 GPIO并读回实际 QOM输出。
程序 A/B 有不同应用帧，旧循环的中断由 raw REPL同步确认；ZIP保留每次源码与revision。

Web 测试只追加 `window.__liveProgramProbe={state,SessionVisual}` 以读取现有对象，
不替换产品方法或API数据。实际guest PNG经独立canvas解码后，与模型display角落
像素对照，避免将RGB565量化后的颜色与源码24位常量直接比较。PIR网页checkbox
进入同guest GPIO/驱动；Relay程序输出经controller读回再进入Unit面板。
两种初始化picker返回次序另有fixture覆盖，不以mock替代真实Web两例。

全部会话在取ZIP后用 `purge=0` 停止，保留metadata、serial和最后帧；不保留
完整mutable Flash。ZIP逐一CRC检查、成员唯一性、路径、大小和SHA核验，无ROM或
firmware `.bin`。运行证据不证明RF、电气行为或物理硬件。
平台824项测试、四项当前状态校验、固定外壳检查和归档扫描见
[verification.json](verification.json)与[原始校验输出](verification/)。

## 版本与可重放身份

实际QEMU由macOS `proc_pidpath`读取session PID定位，并直接计算文件哈希：
`d1ba0063f80f6f8bdeeaa831f0d16ce4004ff3692a2d0587663e121bb93f45ff`。
不是从启动环境变量推断当前执行文件。服务加载源码收据见
[service-start.json](service-start.json)，归档时与生产文件哈希再次核对。

| 主机 | 初始bootstrap固件 SHA256 |
| --- | --- |
| CoreS3 | `0ede40601c1e37b7ba32c87a3ca55e4da7a448f6cf52957f005763bc7c7c78e8` |
| AtomS3R | `0c70da2a56102dc812f380ac24fcb0a75bd3cb0c70e5380d97c11baeca935323` |
| StickS3 | `7b0c04bae8ce7bcd3e7f14f87d8336766b251f36c13f40b9b5823e05186236e1` |
| StopWatch | `2cc6fd6e86e6f91bd10ea9963bd8cc286e3111fa6574fade4adec41eb3141e7f` |

最终源码快照和边界见[source-snapshot.json](source-snapshot.json)及[sources](sources/)。
八例初批在runner清理收尾增强前执行；生成源码、传输和功能断言未变，但不能声称
它们来自最终runner的逐字节版本。最终runner另用AtomS3R+Relay实际复核。
旧picker负控记录修复前源码哈希，不代表最终版本仍失败。

服务已使用本仓库构建的准入reference与QEMU启动时，可重放：

```bash
PYTHONPATH=platform/tools:tests/units:.work/py312 \
  /opt/miniconda3/bin/python3.12 tests/units/run_live_program.py \
  --expected-runtime-sha256 d1ba0063f80f6f8bdeeaa831f0d16ce4004ff3692a2d0587663e121bb93f45ff \
  --device cores3 --unit pir --out-dir /tmp/m5-live-cores3-pir
M5_UNIT_SERVICE_E2E=1 \
M5_EXPECTED_RUNTIME_SHA256=d1ba0063f80f6f8bdeeaa831f0d16ce4004ff3692a2d0587663e121bb93f45ff \
M5_LIVE_PROGRAM_BROWSER_OUT=/tmp/m5-live-browser \
  node platform/tests/test_live_program_service_browser.mjs
node platform/tests/test_program_panel.mjs
```

其它三款主机及Relay需分别运行，使用各自返回的冻结GPIO；不只改设备名后
沿用CoreS3接线。单源码最多64KiB，guest运行时编译；二进制`.mpy`上传、
多文件/assets同步、保存开机程序、Preview/Run编排、共享帧生产者、SSE与AIFlow
消费端接入仍待实现。首次初始化/提交确认计时不能称为完整编辑到首帧SLA。
Scroll/Roller485此次仅新增视觉模型，不能创建功能附件，见
[外壳更新](../2026-10-26-visual-refresh-48667b7/README.md)。

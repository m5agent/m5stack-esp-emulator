# 同 guest 完整文件包与 detent 事件

日期：2026-10-26。文件包分类：**virtual-device validation PASS**；hardware validation **NOT RUN**。
所有功能测试均经本机8787 Device Service可见session，未直接启动QEMU。

完整文件包经原guest UART raw REPL写入暂存目录，逐文件核验大小/SHA与完整目录集，
发布后切换cwd/sys.path并清理托管来源模块。原source API与哈希语义保留。
同revision复用仍重验guest可变文件；此实现不重刷固件、重启VM或暗中换guest。
仅支持`main.py`入口、Python模块、纯字节码`.mpy`依赖及资源，不支持native emitter、
二进制入口或保存为boot；interrupt-only仍不保证native/IRQ/timer/thread完整清场。

## 最终实际范围

| 范围 | 结果与来源 |
| --- | --- |
| 四主机×PIR/Relay | CoreS3、AtomS3R、StickS3、StopWatch八个可见session，各12次execution尝试，共96次预期结果；[cohort](cohort.json)、[逐例](hosts/) |
| 同一VM | 每例PID/固件/VM nonce不变，ROM与bootstrap各一次；A/B/C相同main.py，helper.mpy、普通/namespace模块、JSON及RGB图片变化 |
| Unit与显示 | 原PIRUnit经GPIO读取0/1/0；原RelayUnit写GPIO输出，fresh串口窗口、独立QOM与实际图片颜色分别核验，非原子同帧快照 |
| 失败与恢复 | stale身份409不产生新execution；故意SyntaxError在START前失败、原B复用恢复；mpy版本/整数不兼容、额外空目录与文件篡改均拒绝，再由新C恢复 |
| 原始文件证据 | 每份ZIP保留canonical source、revision、原始file bytes、guest inventory和全部execution；[ZIP成员/大小/SHA](zip-index.json) |
| 清理 | 全部先ZIP后purge=0停止，metadata/最后帧保留、Flash释放、八个owned PID已退出；[独立复核](cleanup-verification.json) |
| 服务与冻结 | gen24服务加载源码与前后快照一致；[start](service-start.json)、[source-before](source-before.json)、[source-after](source-after.json)、[冻结源码](source-snapshot.json) |

96次尝试包含预期失败，不能称96个应用均正常完成。另有40个预期409请求，其中
8个stale请求未产生execution。实际QEMU均经PID读取路径后计算SHA：
`d1ba0063f80f6f8bdeeaa831f0d16ce4004ff3692a2d0587663e121bb93f45ff`。
各主机使用各自的bootstrap固件SHA，精确值在cohort；不混成同一个镜像。

官方MicroPython compiler固定`78ff170de9e32c79db6e64d3e33d2bd60002bdcd`，
与固定UIFlow gitlink一致。compiler receipt、真实编译语料、10k确定性突变与parser
验证见[compiler](compiler/)；编译器/固件/ROM二进制不入库。容器检查不是VM栈/类型
验证或沙箱，不承诺任意源码与任意mpy均可运行。目录回执新增最大合法路径/Unicode
宿主回归，避免合法包超过旧64KiB；guest空间预检仍是估算，ENOSPC会终止并留暂存。

## 图片路径问题与原失败

[六格同guest实验](image-path-diagnostic/report.json)使用相同97B、24×24 RGB PNG：
drawImage/drawPng的bytes各576红像素，106字符绝对路径及16字符相对路径四格全黑。
最终runner使用真实open文件后调用官方bytes接口，图片放在圆屏有效区域。
固定官方源码中的boxed长度与CWD缺口见[源码审计](image-path-research/audit.md)，
未做当前dirty binary符号级跟踪，不称所有源码分支均已实际执行或路径问题已修。
它与原palette/tRNS图像差异分开，登记为UNIT-HOST-30 OPEN。

[earlier-attempts](earlier-attempts/)保留不支持int.bit_length的smoke失败与修复后smoke，
路径API导致的CoreS3失败，以及r2两例StopWatch图片放在圆屏裁切区的harness失败。
最终八例来自修正显示scaffold和inventory上限后的独立新批次，不拼接旧六例PASS。

## detent事件的限定结果

真实vendor的8Encoder latching switch切换后，wrapper down事件现在携带position。
[旧负控](detent-negative/report.json)、[最终7项fixture](detent-final/report.json)覆盖可信
canvas pointer、重复输入源、release/cancel/blur/dispose、两种显式极性及零回声；
[全模型](model-regression/report.json)和[Panel](panel-regression/report.json)回归通过。
极性是synthetic fixture，无真实guest电气闭环或默认binding；UNIT-HOST-29仍OPEN，
不把该事件修复升级成Encoder/8Encoder完整灯/旋转动画PASS。入口资源版本已更新。

## 重放与边界

```sh
PYTHONPATH=platform/tools:tests/units:.work/py312 python3.12 tests/units/run_live_package.py \
  --execute --device cores3 --unit pir --mpy-cross /path/to/official/mpy-cross \
  --expected-runtime-sha256 d1ba0063f80f6f8bdeeaa831f0d16ce4004ff3692a2d0587663e121bb93f45ff \
  --out-dir /tmp/m5-live-package
```

分别更换device/unit重放；不沿用其它主机GPIO。帧oracle只核图片颜色与尺寸，
不将scaffold文字布局称为全部UI可读性验收。原始HTTP往返保留在本地工作目录，
归档包含独立报告、ZIP、帧和源码；未修改实验数据。离线/文档/generated检查见
[verification.json](verification.json)。本块未改QEMU/controller，完整外设矩阵NOT RUN；
不授予AIFlow接入、Preview/Run/SSE、其它Unit/固件、性能SLA或物理硬件结论。

# 浏览器 QEMU 性能与逐设备准入

日期：`2026-10-29`。结果类别为 **browser virtual-device validation**。
性能、正常时钟候选及四板五示例的实际公众 UI 均已取得限定通过证据。
本页不声称新版本已经部署到生产 Pages，也不授予物理硬件结论。

## 根因与改动

旧网页一次采帧结束后再等待 `750 ms`，显示传输上限约 `1.33 FPS`；
每帧经 QMP screendump、MEMFS PPM 和颜色转换。旧 SDK 3.1.50 的
`__syscall_poll` 还忽略 timeout，使 QEMU 主循环在暂停时空转。
CoreS3 板名、单 ROM、16 MiB Flash、320×240 帧和 PIR 曾写在桥接代码里。

本轮保留原客体 CPU、板级控制器、DMA、面板和固件驱动：

- `0014` 从真实 QEMU display surface 发布有界共享 RGB565 快照；浏览器
  校验元数据与像素序列，丢弃写入中的快照，只传实际 dirty update。
- `0015` 对无就绪 fd 的 host pthread 进行有界等待，保留立即就绪、零 timeout、
  有限/无限等待与错误语义；不改变 guest 时钟、WDT 或 vCPU 指令执行。
- 通用 registry 描述各板 ROM/eFuse/Flash、物理帧和输入。公开状态必须来自
  单板证据；`compiled_profiles` 本身不授予公开准入，候选导出不能发布。
- CoreS3 原始 `78961297…bd3f` / div8 及旧分享链接保留；另提供明确的
  `e9500994…9554` / div1 / SDK Python 调度候选。只对完整 Flash SHA
  一致的候选覆写时钟，不把候选当成 stock SDK 修复。

QEMU 使用 `43` 层固定补丁、`146` 个锁定修改文件，从完整源码重建；
新 WASM 为 `9c94a9407893fa7d953d1bf1932769ff52e90b3b1455f98a90185ff2bf05cba1`。
主线已同步至 `32213028`；功能 context port 仅移植 `0068`/`0069`。
冻结 classic SPI 已延后并只消费一次 panel DMA，未套用不同 preimage 的
`0074`，也不继承其它 native/controller 测试。来源、构建与报告完整 SHA 见
[机器摘要](summary.json)。ROM、Flash、原始帧、轨迹和日志未进入源码 Git。

## 同固件对照

顺序运行，停止编译及其它 agent guest；同一 M4 Pro、Chrome 156、实际
ANGLE Metal renderer，同一 `78961297…bd3f`、div8、6 次触摸。
CPU `100%` 表示一个逻辑核。早期 SwiftShader 或与编译并行的样本没有用于此表。

| 测量 | 旧基线 | 新共享帧 + 等待修复 |
| --- | ---: | ---: |
| 运行 CPU 平均 | 132.05% | 49.95% |
| 暂停 CPU 平均 | 105.60% | 4.78% |
| 停止 CPU 平均 | 3.02% | 2.62% |
| 静态画面请求/s | 1.30 | 30.99 |
| 静态画面传帧/s | 1.30（重复画面） | 0（无重绘） |
| 触摸松开到计数像素，中位数 | 1317.66 ms | 966.82 ms |
| 触摸松开到 guest 回调，中位数 | 698.00 ms | 658.53 ms |

运行 CPU 约减少 `62.2%`，但旧慢放固件的输入仍有明显延迟。静态帧不搬运
像素不代表设备停止；新请求和实际画面变化分别统计。输入阶段新传帧约
`11.11/s`、实际像素变化约 `2.67/s`，不能称为任意应用的动画 FPS。
进程 RSS 求和约从 `1,452,547` 降到 `1,062,566 KiB`；共享页可能重复
计算，此数值不是单标签页的独占物理内存，也不是最低运行内存要求。

所有性能样本的 actual worker target 均从 `5` 到 `0`，guest 自然 exit `0`，
dispose 没有强制终止残余 Worker。帧请求中位数从约 `10 ms` 降到约 `0.08 ms`。

## 正常时钟动画：不同工作负载，单列结果

`e9500994…9554` 包含持续 LVGL 动画和显式 SDK 候选，不能与静态旧示例
混作同固件性能对照。20 秒稳态观察得到：

- 传帧约 `9.30/s`，实际像素变化约 `8.90/s`；星标 ROI 变化约 `8.55/s`。
- 星标轨迹速度 `99.77 px/墙钟秒`，源码目标为 `100 px/guest秒`；
  guest/host `0.999711`，LVGL/host `0.999766`，本窗口调度错误为 `0`。
- 运行 CPU 约 `161.97%`，触摸松开到回调中位数约 `867 ms`，到计数
  像素约 `1247 ms`。动画恢复正常时间推进，但触摸没有更快，也不是低开销或
  `30 FPS` 承诺。

现成输入记录中，QMP/channel RPC 中位往返约 `35 ms`；较长延迟在 ACK
之后到 UART 观察到 guest release 之前。该证据仍包含控制器、guest 读取、
LVGL 和 UART 观察，不能唯一归因到其中一层。此范围继续开放。
独立严格功能回归及其明确边界见
[LVGL 正常时钟候选](../2026-10-29-browser-lvgl-wallclock/README.md)。

## 验证与复现

公开准入现为 CoreS3、Core2、AtomS3R、StickS3。CoreS3 单独执行旧 div8
和正常时钟候选，其余三板的固定屏幕/输入示例使用 div1。AtomS3R/StickS3
经实际模型按键送入 guest；Core2 经实际 DOM 触摸，均核对串口计数/松开、
同帧 marker 变色、暂停恢复及自然退出清理。AtomS3R 既有面板映射仍有
2 行偏移，共享帧与同 guest QMP 逐字节一致，不能宣称像素坐标完全校准。

最终公开 v4 的四例门禁通过 `84` 项，新增 Core2 在公开 v5 单独通过 `17`
项。两次导出的执行 JS、WASM/runtime 和其余 `1929` 个资产身份相同；
仅 registry、板型元数据及 Core2 专属 boot 发生变化。这是分别绑定两个
site manifest 的 `101` 项检查，**不是一次 v5 全聚合执行**。后续发布
workflow 每次重新构建均强制运行全部五例。各板完整 Flash/profile、
输入/串口/帧/清理及报告 SHA 见[板型准入摘要](board-admission-summary.json)，
性能、构建和全部门禁索引见[机器摘要](summary.json)。

Core2 首次 fixture 重装固件已占用的 UART0，导致 main 未执行；修复仅用
专属 boot 保留固件原 console，新旧 Flash SHA 分开记录，没有将失败记为
guest WDT 缺陷或借用其它板型结果。

Host wait 的真实 SDK `poll`/pipe/pthread 控制共六项通过；原 poll 30 ms
请求实耗约 `0.364 ms`，新有限等待约 `31.23 ms`，立即就绪约 `0.083 ms`，
另一线程可唤醒有限和无限等待。确定性 C 测试另覆盖短 deadline、大值和 EINTR。
它们不是 guest 或物理硬件测试。

```sh
python3 -m unittest discover -s platform/tests -p 'test_wasm_poll_wait_patch.py'
python3 tests/browser-qemu/poll_wait/build.py --emcc /path/to/emcc \
  --node node --out-dir .work/poll-control-new

# 按 pages-deployment.md 构建完整 runtime/LittleFS，再使用测试子路径导出：
python3 platform/tools/build_public_site.py --output .work/public-site \
  --base-path /showcase/ --qemu-runtime .work/qemu-browser-runtime \
  --littlefs-runtime .work/browser-littlefs
M5_PUBLIC_SITE=.work/public-site M5_PUBLIC_BASE_PATH=/showcase/ \
  node platform/tests/test_public_qemu_admitted_boards.mjs
M5_PUBLIC_SITE=.work/public-site M5_QEMU_PERF_GPU=hardware \
  M5_QEMU_EXAMPLE=stock-div8 M5_QEMU_PERF_OUT=.work/perf-stock-new \
  node platform/tests/test_public_qemu_performance.mjs
M5_PUBLIC_SITE=.work/public-site M5_QEMU_PERF_GPU=hardware \
  M5_QEMU_EXAMPLE=wallclock-candidate M5_QEMU_PERF_SAMPLE_MS=20000 \
  M5_QEMU_PERF_OUT=.work/perf-candidate-new \
  node platform/tests/test_public_qemu_performance.mjs
```

benchmark 的硬件模式会核对实际 renderer，拒绝软件回退；资源采样只适用于
本机/本负载，不能外推手机或其它浏览器。具体工具链、frame/input/serial、
退出、报告哈希和原始曲线哈希在摘要中，完整原始材料保存在 ignored/local archive。

仍未覆盖长期稳定性、C Timer 第一层 coalescing、其余六个 Xtensa 候选、RISC-V C6、
P4 闭源后端、Linux ARM64、网络/音频/其它 Unit、任意固件与物理硬件。

# 2026-11-27 esp32sim 与封存后端对照

## 运行身份

本轮在 macOS ARM64 上执行 **virtual-device validation**。原生组逐个通过
Device Service `/api/v1` 运行。浏览器组使用同一份混合静态导出，Chrome
`158.0.8127.37`，每轮创建新的 BrowserContext。两组分别计时。

| 工件 | SHA-256 或 Git commit |
| --- | --- |
| Device Service 源码 | `16faae71c3ee67f5158431dbe78c27e726e67d3d` |
| esp32sim 源码 | `4e257b6be8ee0ed706c2e509d8f31ef7472a424b` |
| esp32sim 原生（含服务控制补丁） | `f1f478b8a0da96941640f0ccb18709864555fcc6f448ad177d081756271392ae` |
| esp32sim P4 原生（含服务控制补丁） | `b00f8559401bfca5fa9487823d798b23bef13aafe64303ff4a542f9641602e82` |
| esp32sim 服务控制补丁 | `0d85265fde04f6e24d1eb61059b8132f7387f0f15f5ffb7bb233c75611042f78` |
| 封存 QEMU Xtensa | `04abc3ba8cb115919e7faebd55425c802f4f6e40b10bc3cc422c51700add728e` |
| 封存 QEMU C6 | `69493c4edccaab5bc24961982ddb9097dda11c9b3418f9cdc0aaa2b27ae865a4` |
| 封存 Tab5 esp-emu DSI | `633a35f993300a765634ed78a2dbcfd5ffcd5c3f2f354a2dddabeb6108240828` |
| 混合静态导出清单 | `8d5721a8e7e0aa4c5353b33cc257903b91629e561ae5661a0d086a51da1e119f` |
| QEMU-WASM Xtensa | `8067a6b8d599f81bfe454da0318377fcb783c8ee4198fc69d3a042c1311d2c1e` |
| esp32sim WASM | `4c61df24a2028d4d56f66c6aea599848eb5be6ad15c70a181130f6dcc257cce8` |

[封存后端恢复步骤](qemu-backend-freeze.md)和
[esp32sim 运行资产锁](../scripts/esp32sim-runtime.lock.json)说明二进制及 ROM 供给。
实验使用独立端口和状态目录。所有运行在采集末次证据后停止。

Arduino 文档例程来自固定[文档源码](https://github.com/m5stack/M5StackDocs/tree/7219cc9286c39b463da84053deee40bc234625db)，
使用 Arduino CLI 1.3.1、`m5stack:esp32@3.2.5`、M5Unified 0.3.0
及 M5GFX 0.3.0。CoreS3 与 ADV 使用[归档版本](https://github.com/m5agent/m5stack-firmware-archive/tree/829cfe6bc14cbdff40b1f4980a5e1ea4f130f66c)
的合并镜像。其余例程的输入 SHA 按用例记在样本回执。

## 采样

- **原生**。通过 artifacts 和 firmware API 上传同一个 merged BIN，每次新建虚拟
  Flash。QEMU 显式使用 `M5_SERVICE_FLASH_MODE=host-image`；Tab5 仍走其既有
  esp-emu 专用路径。原生时钟从 `POST /sessions` 前开始。观测首张非黑帧和
  第一组三张一致 RGB 帧，其中首末间隔至少 200 ms。该稳定判据可能命中
  启动画面。原版主页单独按产品画面判定。
- **原生输入**。从提交设备输入到随后观察到不同 RGB 帧。时间包含 API 调用、
  可能的按住时长以及采样开销。对自行更新的画面，变化本身不能证明输入
  因果关系。CPU 为来宾进程 `ps %cpu` 样本中位数，RSS 为同窗口进程驻留
  内存，单位 MiB。两个后端分别比较首帧与串口 SHA 的重复性。
- **浏览器**。从用户按下 Start 到 UI 标为 running 且真实 framebuffer
  在 canvas 上出现非黑 RGB，50 ms 轮询。保留输入 BIN 和加载后的 Flash
  哈希。停止后在仍打开的 BrowserContext 内检查 CDP Worker 数量。
- 相邻 run 交替后端顺序，单机串行。得到至少三个有效样本才报告中位数。
  首帧、程序就绪、硬件复位与 Worker 清场是不同检查。

## 浏览器 boot

| 用例 | 输入 BIN SHA-256 | QEMU-WASM 中位数 | esp32sim WASM 中位数 | 缩短 |
| --- | --- | ---: | ---: | ---: |
| CoreS3 Arduino Touch | `a3b1a46231ade128d44c0f1394febcadcb236d86d68ab67008fc19ab4be48c27` | 4.380 s | 1.675 s | 61.8% |
| Cardputer-ADV Arduino Keyboard | `ff5b8b152ba201852ded8684ca517bdf63ea155961ff99e9ff19fad11f4fcf78` | 5.081 s | 2.076 s | 59.1% |

每个单元格有三次独立运行。CoreS3 加载的 Flash 与输入一致，ADV 两侧
均加载 `c10160184212e0c834ae88a44468c9cd022c1496fd27f731a8007c50e4a6ef63`。
全部十二次在 Stop 后观察到零个 DedicatedWorker。首次采样的 ADV
QEMU canvas 为 135×240，后两次为 240×135。该表测量首个可见帧；
帧表现和旋转等价需要各自的检查。

### 文档 iframe #242

同一导出用于跨站的 loopback 文档夹具，父页使用主机名，子页使用
IP 字面量。父子响应均无 COOP/COEP，iframe 中明确观察到
`crossOriginIsolated=false` 和 `typeof SharedArrayBuffer === "undefined"`。
CoreS3 同一 Touch BIN（320×240）接受模型触摸并显示坐标；ADV 同一
Keyboard BIN（240×135）接受按键和 Fn 组合，并实际重绘。每次从
一个 DedicatedWorker 降至零。主文档部署、CSP 与其它文档资源仍待验收。

[PR #277](https://github.com/m5agent/m5stack-esp-emulator/pull/277)
给保留的 QEMU-WASM 路径提供 Document-Isolation-Policy 和新标签页入口。
复核时该 PR 仍 OPEN，与 `main` 有冲突。esp32sim 的上述路径无需
该策略。QEMU 的兼容路径仍由它自己的验证及托管门禁跟踪。

## 原生 Device Service

提交同一镜像后，ADV 原版 UIFlow2 首个稳定帧中位数由 3.78 s 降至
2.25 s，AtomS3 原版由 3.82 s 降至 1.61 s，Dial 原版由 5.07 s 降至
1.79 s。ADV 的 Arduino Keyboard 首稳定帧约 1.01 s 与 1.02 s。CoreS3
Touch 的首个可见帧为 0.76 s 与 1.08 s，首稳定帧为 1.22 s 与 1.08 s。
其输入到不同帧的中位时间为 0.77 s 与 0.37 s。
ADV 用两侧共同接受的 `{"kind":"keyboard","key":"a","action":"hold","seconds":0.45}`
重跑。esp32sim 的输入到不同帧为 0.37 s（3/3），QEMU 在五秒观察窗内没有
不同帧（0/3）。初次使用额外字段 `control` 被 QEMU 拒绝，保留为夹具失败。

NanoC6 为无屏设备。原版自动 REPL 提示符在 esp32sim 的中位时间为
0.62 s，QEMU 在有限窗口未观测到。其 `frame.png` 指标不适用。
PaperS3 的首稳定帧是均匀白底，记录面板初始化，应用出帧和电子纸时序
仍需独立判定。Core2 原版在两侧输出 UIFlow2 banner，esp32sim 8 秒内
未取得非黑帧。官方 Display 程序在 esp32sim 出稳定帧（1.37 s），
QEMU 有可见帧但未满足三张相同的稳定判据。原版主页出帧时间未单独采集，
其余原版在观察窗口缺少可归为同一启动条件的 REPL 提示符。

CPU 对照使用 CoreS3 的固定合成程序 `16c1047c394ada35b071fffce60a7ae3f523611dada27ace0792c8a85bbdd73d`。
以首末完整 `BENCH sec` 计算每墙钟秒的 guest 秒数。中位值为 QEMU 1.010、
esp32sim 0.987，三次重复。两侧均接近实时。设备服务在实时模式
测量，饱和执行速度由独立 CLI 诊断描述。

CoreS3 Touch 的独立 CLI 热点采样用同一 ROM、Flash 和 4.000 guest s。
JIT 与 `--no-jit` 均执行 895,924,013 条 guest 指令，输出的 PNG、串口
SHA 一致。墙钟为 10.00 / 13.01 s（89.8 / 68.9 Minsn/s）。JIT 的指令
主要落在应用页 `0x42007000`（27.18%）及 `0x42003000`（16.31%），
ROM 符号 `__udivdi3` 占 8.82%。这是单次、已启用块计数的 CLI 比较。
设备服务首非黑帧还受调度、帧生成和 API 采样影响，CLI 热点无法单独
归因该 0.32 s 差值。Core2 原版用 CLI 运行 5.000 guest s 后两种模式均有
320×240 画面，JIT 29.20 s、解释器 35.34 s，guest 指令数均为 365,816,859。
此次受计数影响的诊断支持继续检查慢速启动，未定位到 HTTP 8 秒窗口内无帧的单一原因。性能数据不支持整体更快或整体可迁移的结论。

下面是配对运行的中位数。分母为对应运行次数。 `— (0/3)` 表示三次
均未得到指标，`1/3`（不同 SHA 数）表示三份样本字节一致。
CPU 百分数可超出 100%。该列只测 guest 进程，不含 HTTP 编码和浏览器。

Tab5 冻结 esp-emu 的 DSI 准入使用归一化 Flash SHA。首次错误地提供下载 SHA，
导致落入旧 GDB 路径。改正后原版 v2.5.3、v2.5.4 和 RTC/SNTP 在 DSI 已连接
的 10–12 秒窗口都无完整帧。esp32sim v2.5.4 的 10 秒复测首稳定帧
中位数 4.03 s。首次比较的点号标签使同名文件覆盖，复测带完整逐次 ZIP，旧数值和
受限证据保留在公开回执。

| 设备 / 固件 | runtime | 停止 / 运行数 | 首非黑 s | 首稳定 s | CPU % | RSS MiB | 首帧 / 串口不同 SHA 数 |
| --- | --- | ---: | ---: | ---: | ---: | ---: | --- |
| cores3 / touch | qemu | 3/3 | 0.76 | 1.22 | 100.6 | 108.2 | 1/3 / 1/3 |
| cores3 / touch | esp32sim | 3/3 | 1.08 | 1.08 | 96.0 | 73.0 | 1/3 / 1/3 |
| cardputer-adv / keyboard | qemu | 3/3 | 1.01 | 1.01 | 103.6 | 90.3 | 1/3 / 1/3 |
| cardputer-adv / keyboard | esp32sim | 3/3 | 1.02 | 1.02 | 93.1 | 48.1 | 1/3 / 1/3 |
| cores3 / uiflow-stock | qemu | 3/3 | 3.10 | — (0/3) | 123.6 | 119.6 | 2/3 / 3/3 |
| cores3 / uiflow-stock | esp32sim | 3/3 | 2.47 | 3.75 | 40.6 | 147.7 | 3/3 / 1/3 |
| cardputer-adv / uiflow-stock | qemu | 3/3 | 3.16 | 3.78 | 50.5 | 113.9 | 2/3 / 3/3 |
| cardputer-adv / uiflow-stock | esp32sim | 3/3 | 1.83 | 2.25 | 27.5 | 66.2 | 3/3 / 1/3 |
| tab5 / uiflow-stock | qemu | 3/3 | — (0/3) | — (0/3) | 21.2 | 106.1 | 0/0 / 1/3 |
| tab5 / uiflow-stock | esp32sim | 3/3 | 5.75 | 5.75 | 94.1 | 123.1 | 1/3 / 2/3 |
| core2 / uiflow-stock | qemu | 3/3 | — (2/3) | — (0/3) | 96.9 | 322.1 | 1/2 / 1/3 |
| core2 / uiflow-stock | esp32sim | 3/3 | — (0/3) | — (0/3) | 97.3 | 51.4 | 0/0 / 1/3 |
| tab5 / uiflow-v2.5.4-original | qemu | 3/3 | — (0/3) | — (0/3) | 27.0 | 104.3 | 0/0 / 1/3 |
| tab5 / uiflow-v2.5.4-original | esp32sim | 3/3 | 4.03 | 4.03 | 96.2 | 133.7 | 1/3 / 1/3 |
| stickc-plus2 / uiflow-stock | qemu | 3/3 | — (0/3) | — (0/3) | 98.0 | 331.5 | 0/0 / 1/3 |
| stickc-plus2 / uiflow-stock | esp32sim | 3/3 | 2.35 | 2.69 | 29.8 | 68.5 | 3/3 / 1/3 |
| atoms3 / uiflow-stock | qemu | 3/3 | 2.10 | 3.82 | 26.2 | 108.7 | 1/3 / 3/3 |
| atoms3 / uiflow-stock | esp32sim | 3/3 | 1.61 | 1.61 | 13.4 | 62.9 | 1/3 / 1/3 |
| papers3 / uiflow-stock | qemu | 3/3 | 0.26 | 0.26 | 135.0 | 109.7 | 1/3 / 1/3 |
| papers3 / uiflow-stock | esp32sim | 3/3 | 0.30 | 0.30 | 97.3 | 86.9 | 1/3 / 1/3 |
| dial / uiflow-stock | qemu | 3/3 | 3.50 | 5.07 | 108.3 | 111.3 | 2/3 / 3/3 |
| dial / uiflow-stock | esp32sim | 3/3 | 1.41 | 1.79 | 25.6 | 82.4 | 2/3 / 1/3 |
| nanoc6 / uiflow-stock | qemu | 3/3 | — (0/3) | — (0/3) | 101.7 | 70.9 | 0/0 / 1/3 |
| nanoc6 / uiflow-stock | esp32sim | 3/3 | — (0/3) | — (0/3) | 21.8 | 36.4 | 0/0 / 1/3 |
| core2 / display | qemu | 3/3 | 2.08 | — (0/3) | 106.1 | 323.2 | 2/3 / 1/3 |
| core2 / display | esp32sim | 3/3 | 1.37 | 1.37 | 31.9 | 65.2 | 1/3 / 1/3 |
| stickc-plus2 / display | qemu | 3/3 | 1.54 | — (0/3) | 100.9 | 331.1 | 3/3 / 1/3 |
| stickc-plus2 / display | esp32sim | 3/3 | 0.67 | — (0/3) | 97.0 | 47.0 | 2/3 / 1/3 |
| atoms3 / display | qemu | 3/3 | 1.25 | 1.43 | 100.5 | 89.8 | 2/3 / 1/3 |
| atoms3 / display | esp32sim | 3/3 | 1.27 | 1.27 | 96.3 | 46.9 | 1/3 / 1/3 |
| papers3 / quickstart-bargraph | qemu | 3/3 | 0.26 | 0.26 | 127.0 | 103.0 | 1/3 / 1/3 |
| papers3 / quickstart-bargraph | esp32sim | 3/3 | 0.74 | 0.74 | 90.0 | 84.1 | 1/3 / 1/3 |
| dial / encoder | qemu | 3/3 | 0.99 | 0.99 | 86.2 | 90.3 | 1/3 / 1/3 |
| dial / encoder | esp32sim | 3/3 | 0.50 | 0.50 | 91.6 | 49.0 | 1/3 / 1/3 |
| nanoc6 / led | qemu | 3/3 | — (0/3) | — (0/3) | 102.2 | 64.0 | 0/0 / 1/3 |
| nanoc6 / led | esp32sim | 3/3 | — (0/3) | — (0/3) | 15.0 | 19.0 | 0/0 / 1/3 |
| tab5 / rtc-sntp | qemu | 3/3 | — (0/3) | — (0/3) | 95.2 | 107.8 | 0/0 / 1/3 |
| tab5 / rtc-sntp | esp32sim | 3/3 | — (2/3) | — (0/3) | 96.8 | 123.9 | 1/2 / 1/3 |
| cores3 / cpu-control | qemu | 3/3 | — (0/3) | — (0/3) | 97.8 | 90.6 | 0/0 / 3/3 |
| cores3 / cpu-control | esp32sim | 3/3 | — (0/3) | — (0/3) | 63.6 | 65.3 | 0/0 / 1/3 |

## 旧问题复验

| 旧项 | 状态 | esp32sim 复验与剩余条件 |
| --- | --- | --- |
| #188 / Tab5 DSI | PARTIAL | 原版 v2.5.4 GT911/ILI9881C 冷启后出现离线主页，(83,755) 触摸选择 ADC。后续稳定画面可识别 ADC 管脚。CLI 同 BIN 观察 513 次 DSI scanout、0 次 DSI read。原版未走所需的 RX FIFO 回读路径，该回读关闭条件仍开放。联网、配对待验。 |
| #226 / Tab5 USB Host | PASS（原版 HID 路径） | 同原版 Maker Fighter 1.4 经 /api/v1 到达 `ready: canvas 512x288`，接入虚拟手柄后 guest 报枚举。独立 CLI 按原时间脚本经中断端点实际传送 4 份 3 字节报告并进入 ARCADE/TRAINING 菜单，空闲对照停留标题页。本次未验 MSC，冻结 esp-emu USB 缺口保留。 |
| #242 / 外部文档嵌入 | PASS（本地） | 本地跨站、无隔离的 CoreS3 + ADV 例程与停止回收通过。Docs 部署预览、实际 CSP 和其它资源待验；QEMU 仍需独立隔离路径。 |
| RUNTIME-01 / C6 复位 | PARTIAL | 精确原版 Meshtastic SHA `ef8249ac…` 到达 boot count 1，20 s 内无 `Invalid chip id`，且未观测到原 `LP_SW_HPSYS`。esp32sim 的原复位路径保持 PARTIAL。原有 QEMU 修复状态保留。 |
| RUNTIME-02 / 802.15.4 | PARTIAL | 原版 NanoC6 light SHA `a736daf2…` 进入 `Start network steering`。独立无对端会话有 steering 失败，未见原 `Zigbee_main` watchdog。Cooja 对端复验同 BIN 在 6.145 guest s 加入；收到 5 次 On/Off，真实 LED 输出蓝/灭交替。离网、共存与新版双租约 API 对这份原版的复验仍待验。 |
| RUNTIME-07 / StamPLC 多指令 TB | NOT RUN | 按原 SHA 重建工作台 Flash。新导出未准入 StamPLC 及其 `plc-key` 浏览器输入，因此来宾复位 NOT RUN。QEMU 的 TB、TLB 与 IRQ/reset 取证条件仍开放。 |
| RUNTIME-08 / ADV WASM OOB | PASS（新 Worker） | 精确工作台 Flash 冷启执行 UART 源码，重建 Worker 后新 console prompt 再执行源码，Stop 后 Worker 归零。QEMU 原 pthread trap 栈及同路径损坏仍开放。 |
| RUNTIME-09 / AtomS3 Lite SYSTIMER PIF | PASS（新 Worker） | 精确工作台 Flash 冷启执行 UART 源码，重建 Worker 后新 console prompt 再执行源码，Stop 后 Worker 归零。QEMU 原 MMIO/region/TLB/TB 关闭条件仍开放。 |
| TCG 墙钟与 UI-04 / Pages | OPEN（冻结路径） | 本地两板速度、输入和清理已取得。Pages 的 PaperDIY reset、Atom Matrix QMP/短按与 ADV Q 键释放需要同一托管导出及原来宾的完整 72 项门禁。TCG/pthread 不进入 esp32sim 运行路径。 |
| CORE2-02 | NOT RUN | 本次冷启单会话无法验收九实例 native-HCI ACK。既有诊断须匹配 ELF 和独立 HCI transport，仍 OPEN。 |
| PaperS3 Factory GT911 | PARTIAL | 浏览器同 Factory V0.5 已读到原板型 marker 且清理 Worker。原图标区域的首次判定未满足，首轮 12 个点按均未进入。复测等待实际 540×960 图标后，原坐标 (113,347) 的 12 个点按均改变图标区域。第二次起两个黑像素计数交替为 1755 和 1910。旧 GT911 事务与跨刷新阶段采样的完整关闭条件保持开放。 |
| Tab5 其它原版 / TAB5-01 | NOT RUN | 98TAB5 的 cache、M5TabOS 的板型和网络、UserDemo 其余音频及 CSI 等各须原 BIN 对应输入，保持开放。 |
| CoreMatrix C61 | NOT RUN | 目录外的 C61 浏览器后端独立。此次 esp32sim 构建未提供 C61 原样本的 SoC/板型。 |
| RUNTIME-10 / StickS3 | NOT RUN | PM1、USB CDC、HID 和 Wi-Fi monitor 的已验子路径保留。其它构建、受保护帧、高吞吐或运动报告依然需要原固件和对应控制器观测。 |
| 其它历史原版与服务项 | NOT RUN | `#178` classic 跨板型高负载串行烧录、`#216` Nesso RFID、`#223` StackChan 原版 UserDemo/GPT I2C、未验 PaperColor 互斥、跨主机 executor 等继续按原 backlog 条件验收。当前启动基准不替代任何上述端到端路径。 |

复位分支使用另一个[逐板验收导出](validation-ledger.md#2026-11-27esp32sim-wasm-逐板验收)，
清单 SHA-256 `38cf12dcfdb8d9cdc3ecab92d7fa3cc568cf75a652a9048033031d738cadf1dd`。
首轮探针误用复位前的 UART ready marker，提前发送输入。独立复测按新的串口
偏移等待 ready 和 REPL 提示符。两次通过均只覆盖新 Worker 的重启和源码执行。



## 复现入口

使用固定服务源和独立 loopback 端口、状态目录及控制凭据。设置
`M5_SERVICE_FLASH_MODE=host-image`，按运行身份表指定 QEMU、C6、Tab5 DSI
与 esp32sim。上传后在 `/api/v1/firmware` 对同一合并镜像建立固件条目；
循环创建会话、读取 `serial` 和 `frame.png`、提交适用的 `input`、下载
`evidence`，再 `DELETE /api/v1/sessions/{id}?purge=0&retain_flash=0`。

```sh
python3.12 code/native.py "$TEST_ORIGIN" "$CONTROL_FILE" code/cases.json "$OUT" --window 8
node code/browser.mjs "$EXPORTED_SITE_URL" "$BROWSER_CASES" "$OUT"
M5_BROWSER_SITE="$EXPORTED_SITE_URL" M5_DOCS_FIRMWARE="$DOCS_FW" \
  M5_BROWSER_EVIDENCE="$OUT" node code/embedded.mjs cores3-touch cardputer-adv-keyboard
```

复现脚本、逐次测量、归一化 Flash 和原始证据哈希见[公开工作记录](https://github.com/m5agent/agent-work-logs/tree/badb2359ff969341ba33306220d7aeeaf17d7cca/records/m5stack-esp-emulator/2026-11-27-esp32sim-backend-benchmark)。物理硬件
NOT RUN。冻结后端的根因、生产网站隔离策略和完整原版应用行为分别保留验收。

# Preview 控制组、2Relay 与整装配构图

日期：2026-10-27。状态：限定 virtual-device 验收完成；hardware NOT RUN。

UIFlow2 首次初始化后，后续程序经 UART REPL 在同一 VM 部署运行。固定探针
镜像属于回归入口；本块实际验收没有逐程序重新刷固件或重启 guest。
[结论及完整 firmware/runtime SHA](acceptance.json)记录精确范围。

四款主机的 HUB + Encoder / 8Encoder / Joystick 各四Run通过：可信 Web 输入、
原I2C驱动、逐leaf QOM、2+9同色灯、Web完整包保留编辑与取消再跑。
2Relay U131 各七Run通过：官方1512B原源码/文件SHA、四组合、重复写、主机按键/
触摸、独立GPIO/两路计数、mounted两蓝灯、Run帧、取消恢复、精确历史帧及清理。

| 主机 | 2Relay Runs | Firmware SHA前缀 | 直接HTTP | 必需执行证据 | 附加浏览器采集 |
| --- | --- | --- | --- | --- | --- |
| cores3 | 7 | `0ede40601c1e37b7…` | 708 | PASS | INCOMPLETE / pending 0 |
| atoms3r | 7 | `0c70da2a56102dc8…` | 837 | PASS | INCOMPLETE / pending 0 |
| sticks3 | 7 | `7b0c04bae8ce7bcd…` | 848 | PASS | INCOMPLETE / pending 0 |
| stopwatch | 7 | `2cc6fd6e86e6f91b…` | 699 | PASS | INCOMPLETE / pending 0 |

[2Relay最终索引](relay2/final-index.json)与[HUB控制组索引](controls/index.json)
分别维护原请求/响应、串口、QOM、选定帧像素、ZIP及清理。2Relay raw响应以
ZIP逐成员原字节压缩保存；manifest可逐文件核SHA/size，压缩不改变解压内容。
四host使用同一最终探针版本；附加browser body/header存在取消/超时，明确为
INCOMPLETE，pending为0且browser关闭/最终drain都自然settled；必需的直接HTTP、
Run/帧身份、guest/controller/mounted证据未放宽。非对称逐灯和机械旋转不继承。

2Relay停止前取证ZIP，停止后history PNG与最后稳定Run帧SHA相等；Flash释放、
PID消失、active/lease归零。HUB控制组只核停止末帧保留元数据，未采历史帧字节。

- [官方研究](research/archive-index.json)：固定产品/MCP/驱动/原理图；研究不是执行。
- [相机证据](camera/index.json)：旧窄屏、初修长dt失败与最终四断点/手动视角/
  零回声回归。整装配bounds包含线缆；用户主动zoom/pan仍可有意裁切。
- [构建与宿主检查](runtime/index.json)：独立冷构建、固定源码/10-patch、逆向应用
  检查；共享旧owned静态依赖有单独SHA，无固件/ROM/QEMU二进制入库。
- [矩阵回归](regression/index.json)：CoreS3定向7PASS；完整66/67，Core2 IMU
  marker黑而UART正确，独立单例PASS不回写完整轮。UNIT-HOST-21仍OPEN；full
  中61例显式绑定新Xtensa，5例用独立RISC-V，1例为RMT分析器。
- [失败/不完整尝试](relay2/attempts/index.json)：CoreS3 r1 RGB565 oracle误拒及
  失败清理记录缺口、r2 observer无界等待/外部关闭专属Chrome、AtomS3R r1 IPC
  等EOF及短按采样缺口均保留。r2自动PASS被根降为INCOMPLETE；旧r3另标
  PASS/superseded，不替代最终r4。旧源重构与当时捕获分别声明并核原SHA。
- [早期执行源码快照](sources/index.json)：包含IPC修复前已验版本；最终四host
  以[最终源快照](relay2/hosts/sources/index.json)为准。验证元数据只在执行后更新，不冒充运行时快照。

新QEMU SHA256：
`850426a786d291ee2e50e7b36f13237873a961667196b98e3e3632885746bf75`。
U131 white=通道1、yellow=通道2；R3/R6 10K只作数字下拉。蓝灯是额定供电
假设下的pad功能指示，不表示触点、线圈时序、电流、负载或物理测量。
跨hard-reset通知计数缺口为UNIT-HOST-36；Preview reset仍禁用。

平台首轮1112项中3项因旧数量断言/生成快照未通过，修正后27项定向复核通过；
最终全平台1112项通过，runtime/peripheral/profile/snapshot生成检查通过；收尾记录
另保留初次失败和定向复核。UIFlow main.py与纯字节码依赖已有路径，独立
main.mpy、保存开机、热插拔、SSE、AIFlow调用侧、完整native/IRQ/thread清理和
其它Unit/主机仍按Backlog继续，不由本块关闭。

[最终验证记录](verification.json)保存全平台日志的原始/归档SHA、收尾契约检查、
独立文档及归档复核；[隐私检查](privacy-final.json)与[归档清单](artifact-manifest.json)
用于核对本目录内容。主线同步结果另记录于 `integration.json`，不改变执行时快照。

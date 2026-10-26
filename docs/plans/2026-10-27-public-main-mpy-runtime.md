# 公共 main.mpy 同虚拟机运行入口

日期：2026-10-27。归属 UNIT-01；状态：本块验收完成，UNIT-01整体继续。执行队列仍以 project-backlog.md 为准。
上一块为50d990ba/f51811fa，已同步origin/main@f2061759。该块固定CoreS3兼容
固件的loader诊断通过，尚未成为公共Run入口。本块连接真实loader与服务事务，
不将单个诊断或宿主字典作为能力证明。

实现路径：

- 新会话的受控program_mode bootstrap保持main不自启动；Session仍booting时，
  经独占真实UART运行官方编译的固定纯字节码canary，验if-main、真实file、
  模块缓存/导入身份及REPL owner恢复。stock语义不支持而恢复完好时仅关闭MPY；
  超时、协议失败或恢复未证实则停止启动，不能冒充已知false继续运行。
- 能力绑定session/device/固件/runtime/PID与进程身份。公共调用不能注入能力；
  restored会话不沿用未经重新证实的旧能力。手动UART/source会话不自动打断原程序
  来探测；本块自动探测仅用于服务自己的bootstrap。
- Session和Preview可显式选择已存manifest base及normalized SHA pin，复用1.45
  composer、安全/PSRAM/能力沿传与CAS保护；默认reference保持兼容。Preview
  初始配置与runtime能力分离，pending/unknown MPY提交在任何取消/分配前拒绝。
- 二进制文件经现有真实guest暂存、哈希回读、发布和依赖更新后，用官方
  override-main import执行，不改写字节码。导入前LOAD仅证明请求派发，不能称
  MPY body已进入；应用started/ready保持unknown。有限返回、异常、取消和Ctrl-C
  后须恢复真实REPL owner和模块缓存；native/IRQ/thread仍为interrupt-only边界。
- Web保持二进制checkpoint原字节，只在已验证动态能力下允许Run；stock源码、
  输入、取消、关闭不受MPY false影响。

验收包括宿主拒绝/身份/竞态负控、stock与兼容固件的普通session和托管Preview
可见8787会话、同PID/固件/nonce重复Run与依赖更新、if-main/模块身份、异常/
格式失败/取消后源码恢复、PIR或Relay实际UART/QOM/PNG与真实mounted Web。
先ZIP再stop purge=0，保留历史并核Flash/PID/lease释放。固件/ROM不入库，
源码和编译recipe、固件/runtime/程序指纹及原失败保留。硬件另验。


验收结果：gen45 CoreS3 ordinary stock/source保护与兼容固件main.mpy实际API通过；
同一个托管Preview真实Web只读包/重复Run/PIR/取消/新建源码恢复通过。三个guest共
14执行、8 main.mpy，最终ZIP86成员核验与精确历史帧/PID/Flash/lease清理通过。
宿主平台1213项通过，八个optional HTTP200空PNG体保持PARTIAL。详见
[分层验收与原始指纹](../evidence/2026-10-27-public-main-mpy/README.md)。

最终审查发现并修复OpenAPI3.1 null/公开worker投影，以及已LOAD但缺少terminal
owner恢复回执时错误沿用能力的边界；gen46另做定向会话复验，保留gen45与宿主
原失败。新增测试后先重新生成project-snapshot，再执行最终全量回归。

# 二进制 checkpoint 与下一批 Unit 协议

日期：2026-10-27。归属 UNIT-01，状态：进行中；执行顺序仍只在 project-backlog.md。

用户目标是外部 Agent 创建虚拟设备、连接 Unit、同 VM 实时运行 UIFlow 程序并
看到双向状态。源码路径已实现。本块将二进制完整包的不可变存储与固件执行
能力分开，保留旧 Python 包身份、历史记录和当前运行，不用普通 import 或字节码
重写冒充脚本入口。支持的二进制 loader 必须来自独立固定源码的兼容固件构建。

存储允许显式 main.mpy，禁止导入遮蔽；当前固件继续声明不支持二进制入口。
普通 session/Preview 在新 execution/Run/取消旧程序之前明确409，inline请求不
消耗包配额。先做旧记录迁移、API与协调器负控，再经8787逐主机验证原程序仍可
接收PIR输入、串口/控制器/画面继续前进及同VM替换恢复。ZIP必须先于关闭。

兼容固件准备限定新owned目录，固定UIFlow/MicroPython/ESP-IDF和依赖SHA；
不修改原reference、不触碰真机。首次目标CoreS3，之后逐profile独立验证；
load/execute/应用READY边界、模块身份、缓存、中断和异常恢复必须按真实loader验收。
官方override-main importer合并加载与执行，只能先确认import-dispatched，不能
冒称当前源码路径的compile-success START。新能力须绑定构建后的固件SHA及
实际guest探针，不能从store准入、宏定义或另一个profile继承。原stock reference
继续支持源码路径，兼容固件先走显式上传与UART会话验收，再决定产品选择入口。

同步核对4Relay与FlashLight官方协议、MCU/芯片、原驱动和模型映射；冲突先保留
原文并反馈，不按错误示例改造控制器或补造物理状态。研究不计Unit功能准入。

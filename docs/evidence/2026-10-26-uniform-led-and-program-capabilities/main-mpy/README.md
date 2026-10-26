# UIFlow 二进制入口可行性与实际 VM 语义

日期：2026-10-26。分类：virtual-device capability probe；hardware NOT RUN。

当前支持同一 VM 动态执行 `main.py`，以及用真实 importer 加载纯字节码
`.mpy` 依赖。普通 `.mpy` 导入不提供完整脚本入口语义，因此 `main.mpy`
仍明确拒绝。没有构建新固件，也没有为每次程序更新重刷或 reset。

固定 UIFlow `3a86d8f611b3639cca755a933e01a5a829771ef1`、其 MicroPython gitlink
`78ff170de9e32c79db6e64d3e33d2bd60002bdcd`。14 份 MicroPython 原文逐字节核对，
94 份 UIFlow patch/config blob 的下载、SHA 和相关符号搜索见清单；归档保留
全部14份关键 MicroPython 原文和8份选定 UIFlow 原文，未归档的blob可按固定URL重取。
原文按需增加 `.txt` 后缀，字节不变。

[研究原文](research/research.md.txt)与[结构化结论](research/research-summary.json)
说明 override-main 宏、builtin `__main__` 优先级、异常恢复及未来入口验收。
当前固件默认未开启 `MICROPY_MODULE_OVERRIDE_MAIN_IMPORT`；`fromlist=False`
也只作普通导入。`level=-1` 实际抛 ValueError，`marshal` 实际不可导入。
把文件命名为 `__main__.mpy` 仍被 REPL 内置 module 遮蔽，不能绕过该边界。

CoreS3 session `8218e02e1dfe43a494f2ed8e54d7f008`，generation30，guest PID70868：
初始化 → 同一包内普通 `.py` 与官方编译 `.mpy` 导入 → source 恢复，共3次执行。
两个导入均保留普通模块名、if-main为false，`import __main__`仍指向原REPL owner。
source脚本的新globals初始`__name__='__main__'`，也不会注册成应用main module。
恢复程序保留VM nonce并绘制实际`0x123456`帧，见[报告](guest/report.json)与
[帧](guest/frame.png)。

- 固件 SHA256：`0ede40601c1e37b7ba32c87a3ca55e4da7a448f6cf52957f005763bc7c7c78e8`。
- runtime SHA256：`b8de32a39be06162ae8ce8529b218370038936059dba067b9a7109a470e067d2`。
- [证据ZIP](guest/evidence.zip)：20成员，串口字节窗口、文件包和成员SHA已核验；先ZIP再stop/purge0，末帧/历史保留、Flash释放、owned PID退出。
- [初次health404](attempts/initial-health-404/report.json)未创建session，保留失败。
- [归档复核](archive-verification.json)另核22份保留原文SHA和ZIP成员；[探针源码](probe-main-mpy-capability.py.txt)、HTTP请求/响应与compiler收据可重放。

新固件启用官方 run-as-main 配置或暴露受验 loader 后，仍可初始化一次再连续运行；
须重新验证模块身份、if-main、依赖更新、错误/中断恢复和加载/START边界。
当前研究不授予新入口、任意固件兼容或native/IRQ/thread完整清场结论。

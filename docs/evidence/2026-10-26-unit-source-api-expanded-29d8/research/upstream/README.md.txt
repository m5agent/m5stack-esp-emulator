# UIFlow Unit 两处驱动问题的上游源码复核

2026-10-26 查询官方仓库，`HEAD` 与 `refs/heads/master` 均解析为 `3a86d8f611b3639cca755a933e01a5a829771ef1`。已从该 commit 的公开 URL 获取五个目标文件，HTTP 均为 200，并记录 SHA256；末尾再次查询 HEAD 未变化。

结论：这五个文件仍保留原问题模式。Buzzer 和 IR wrapper 与仓内 vendored 字节完全一致；Haptic、SoftTimer、IR native C 也与原补丁依据 `50e440780492aa847378c7d3477ab912f7063bac` 完全一致。相应最小比较 diff 均为空。

- Buzzer：`Haptic._cb(self)` 仍不接收 timer，而 `SoftTimerScheduler.update()` 仍调用 `tim.callback(tim)`；`BuzzerUnit` 没有覆盖 `_cb`。这处参数个数不匹配未在当前源码修复。
- IR：`rx_cb()` 的局部 nested adapter 没有保存到 `self`；native constructor 仍把它赋给 `static mp_obj_t ir_rx_callback`。native 对象仅保留 base/pin 字段，本模块没有该 callback 的 GC root 注册。已知 callback 保活问题的源码模式未修。此处结论限于这些确切源码，未扩展检查全部 MicroPython port GC 集成，也未运行当前版本固件。

现有两个 custom guest 补丁对当前官方源码副本均以零 fuzz 通过 dry-run；副本和仓内驱动均未修改。补丁适用不表示原版驱动获得运行 PASS。

先按 M5Stack 官方 skill 查询 MCP，并读取 bundled official Buzzer/IR 文档。精确检索返回公开 API 文档，未提供内部 callback 修复依据。具体实现结论采用固定 commit 文件，未把 master URL 当作版本固定证据。

公开 URL、commit、每文件 SHA256、精确行号、源字节比较及限制见 `report.json`、`fetch-current.json` 与 `ls-remote.txt`。`commit-summary.json` 只保留必要 commit 元数据；完整 GitHub API 响应 `commit.json` 无需归档。未发送 issue、PR、feedback 或外部人员消息。

本次只有源码研究，没有调用 Device Service、创建虚拟设备、运行 QEMU、烧录或实物测试。当前仓库源码与任何已发布固件版本的包含关系仍需单独核实。

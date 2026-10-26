# AtomS3R / StickS3 / StopWatch：九组合 gen9 证据

2026-10-26 的九个独立可见 Device Service session，按 AtomS3R → StickS3 →
StopWatch、每台 Button → Relay → ENV III 串行完成：**9/9 严格功能 PASS，0 失败、
0 重试**。runtime SHA 为
`a8fe15dbe7299c5be4b52eeac68a6d0012578950d267287630760bf8bec7d047`，
worker generation 为 9。每个组合绑定同一 session、firmware、直接 PID executable
hash、控制器与真实浏览器证据，停止前取得 ZIP，随后以 `purge=0` 保留 history。
批次结束 `active_sessions=0`。这是虚拟设备证据，物理硬件 **NOT RUN**。

Button 验证原驱动 GPIO 电平、IRQ counter 与四次可信 Web POST；Relay 验证 guest
输出两种电平和 QOM/面板 readback，浏览器没有伪造输入 POST；ENV III 验证外部
`0x44/0x70`、六次字段 POST 与两组 guest 温湿压向量。三种探针均在外部操作前后
重读内部 BMI270 `CHIP_ID=0x24`，使用 firmware 自带的未改写 Unit driver。

九张 native frame 均完整：AtomS3R 128×128、StickS3 135×240、StopWatch 466×466。
StopWatch guest canvas 为 468×468、rotation 0，与 native 尺寸分开断言。
Button/Relay 的六张浏览器截图完整；**三张 ENV 浏览器截图的 framing 为 PARTIAL**，
全局 sticky header 遮住 session card 标题/顶边。StopWatch 显示主体可见，输入、
控制器字段和串口仍可读。此缺口不改变九个功能/DOM/PID/ZIP strict PASS，也不能
称为完整视觉验收。未新建 session、未重拍或替换原始截图。

执行前冻结明确列出 25 个命名源文件，遗漏两个直接打包 helper：
`tests/units/run_control_cases.py`、`tests/units/run_sensor_cases.py`。后续独立审核
只能补充 archive-time hash 与早期 CoreS3 冻结副本的连续性比对，不能将其描述为
执行前冻结。该审核及 canonical27 selection 由独立 validation audit 归档；本页
不提前宣称审核完成。

每台主机的 canonical27 范围仅有上述 3 项已运行，其余 24 项 **NOT RUN**；整体
inventory 仍为 **PARTIAL**。九组合不覆盖 ADC fixture、其他 Unit、其他固件 SHA、
物理电气行为或完整发布门槛。历史 `1880891d…` 无 Unit boot control 是独立证据。

公共归档只脱敏九份 `runner.stdout.txt` 中的个人绝对仓库路径，并重算外层 report
对这些日志的 artifact hash；原始内部证据保持不变。controller JSON、ZIP、Web
report 与 PNG 保持原字节。归档排除 firmware/ROM/Flash/eFuse 二进制。
`SHA256SUMS` 覆盖本目录全部文件（自身除外）。

- [功能汇总](summary.json)
- [native contact sheet](native-frame-contact-sheet.png)
- [browser contact sheet](browser-contact-sheet.png)
- [视觉复核及 PNG hashes](visual-review.json)
- [公共脱敏 provenance](public-redaction-provenance.json)
- [执行前 source provenance](batch-source-provenance.json)

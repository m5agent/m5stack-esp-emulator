# CoreS3 标量读数：11 款跨批选择

日期：2026-10-26。仅为虚拟设备验证，物理硬件 `NOT RUN`。

本目录显式选择 eleven-r1 的 ENV III、Relay、Color、ToF、NCIR、Heart、TVOC、
Ultrasonic-I2C、PIR 九款，以及 light-thermal-r2 的 Light、Thermal 两款。
这是 **9+2 的跨批选择**，不是一次十二款全绿执行，也不关闭整体 UNIT-01。
原批 Light 计数失败和原 Buzzer 读数阶段失败不在此选择中，原报告没有改写；
原 Buzzer 的 once 自动关闭边界仍需独立处理。

11 份报告的原 guest/controller 断言、当前只读严格 Checker、同固件/直接 PID/
ZIP/历史均核对。27 个阶段逐项使用阶段入口之后的真实产品 GET 与原 HTTP body；
25 份 guest 向量按输入前串口 offset 重建实际新鲜前缀。停止前取 ZIP，停止后
保留历史并释放 Flash。跨通道观测异步，不声称 LCD 与 DOM 是原子快照。

Light 恰有五次产品 POST，初始 digital=false 在第一 POST 前由真实 GET 观察；
未变化的 checkbox 不额外发送 POST。Thermal 两组不同原始帧均经过 guest 的
768 有限像素与九个样本计算；rail 两阶段仍可同为 control-word=6401 与
raw-fixture-ready=true，仅代表控制寄存器和模型就绪状态，不是温度图。
Heart 只验证原始 IR/red 样本，不升级为心率或血氧。

两批 source-freeze 原文与各自355份文本源快照按 SHA 原样保存；每批28个既有
参考图、抠图和Logo（合计28个唯一资产、56条批次引用）采用精确 baseline
eff1561 Git blob 引用，未复制图片 body。每项记录 commit/blob、原路径、原
扩展名、实际图片格式及未复制原因。图像metadata存在本身不意味着敏感信息；
这是归档白名单边界。没有重编码、清理metadata或改写原始证据。

111张磁盘 PNG 全部完整解码，另核验11个 ZIP 的111个成员及其原生帧。
其中20张额外 annotation/terminal fullPage 图为18.2–26.9M像素，超出当前
Checker.png 用于 ZIP/native 和 before-evidence 图片的16Mi像素上限。
原 Checker 未修改，其实际验收范围11款均通过。这20张只证明完整解码，
不授予整页构图、文字可读性或所有UI状态的视觉验收。

独审 receipt-r1 保留其扩展规则失败：首次审核将上述16Mi上限额外套到全部
fullPage图，得到6通过/5超尺寸边界；不是PNG损坏或原runner失败。
receipt-r2 明确用途区别后完成11款独审，r1原文继续保留。详见 reviews/。

selection.json 是固定选择；archive-provenance.json 记录原始来源、逐字节
复制及排除范围；SHA256SUMS 覆盖本目录除其自身以外的所有文件。
固件/ROM/ELF/运行时二进制、Python字节码、凭据和私有绝对路径未纳入。
本目录不是外部工作日志归档，也不扩大主机准入或物理硬件结论。

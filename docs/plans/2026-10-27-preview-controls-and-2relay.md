# Preview 控制组与 2Relay 数据面

日期：2026-10-27。归属 UNIT-01 / UNIT-HOST-29 / UNIT-HOST-35，状态：限定验收完成。
执行顺序仅在 project-backlog.md 维护。

以首次启动 UIFlow2 后同一 VM 连续部署执行程序为产品路径。本块补充 HUB +
Encoder / 8Encoder / Joystick 的托管 Preview 实证，并接入 U131 2Relay 双 GPIO
驱动与两个蓝灯的只读反馈。不得用主机写继电器结果或 Python 返回值替代 GPIO
控制器，也不把 pad 高低电平称为触点机械、电气或负载测试。

2Relay 依据固定官方产品、原理图及 UIFlow2 2.5.3 Relay2Unit：port tuple 的
white 是通道 1，yellow 是通道 2，高电平在额定供电假设下使对应驱动与蓝灯有效。
两路分别记录输出与 transition；不增加并不存在的 Unit 物理输入。保留原单 Relay
路径。新增 QEMU patch 使用独立源树/构建，记录补丁、源码和二进制 SHA。

先做契约与宿主负控，再通过 8787 可见会话按主机逐一验收：同一 guest 内四种
双路组合、原驱动与独立 pad/QOM、mounted 蓝灯及真实帧；HUB 控制组验证可信
Web 输入、原 I2C 驱动、全灯同色和取消后再运行。所有运行先 ZIP 再关闭，保留
历史/末帧并核 Flash、PID 和 lease 清理。失败尝试保留，不转授其它主机或固件。

窄屏默认相机按整装配 world bounds 安全 fit；resize 保留用户方向、相对缩放和
pan，帧与状态轮询不能复位相机。先保留旧算法可执行裁切负控，再验收四断点、
主动视角及既有输入/挂载回归。此项不修改共享 vendor。

QEMU 修改先做定向回归，并按共享控制器/构建里程碑门禁执行完整矩阵；不能用
功能 session 代替矩阵或真机验证。独立 main.mpy、保存开机、SSE、AIFlow 调用侧、
逐灯排列/轴向标定和 native/IRQ/thread 完整清理仍留在既有 Backlog。

实际四主机HUB控制组、U131同VM七Run与相机限定验收完成，见[本块证据](../evidence/2026-10-27-preview-controls-and-2relay/README.md)。完整矩阵66/67，Core2 IMU既有问题未关闭；所有失败/不完整轮与取证器修复保留。整体UNIT-01及AIFlow接入工作继续。

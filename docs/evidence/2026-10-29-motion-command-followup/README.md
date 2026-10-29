# 舵机命令边沿与经典 Atom/Stick 后续验证

本轮整体为 **PARTIAL，尚未部署**。最终 native v7 全矩阵和固定浏览器导出的
StackChan 五条严格动作路径通过；自然 PWR 已使 guest 正常关机，但独立 CDP
仍观察到一个 engine Worker target，完整清理断言失败。四款经典 Atom/Stick
的 v7 默认参考入口正在独立验证，不能用之前的本地固件上传结果替代。

`0096` 修复重复相同 torque 重启动作计时，以及官方 PWM→位置模式分步恢复
角限被拒绝；控制器 C 回归保留两项旧版失败负控。`0097` 修复 S3 GPIO 复位后
软件 I²C 探测桥未重新交接，保留事务和外部 SDA 所有权边界；`0098` 实现 S3
IDF RXFIFO 复位脉冲，实际 UART/S3/Fifo8/SCS 源码回放覆盖旧 ACK 清除、应答、
中断和逐字节读取。`0098` 与旧轮孤立 `ReadPos=-1` 的因果关系仍未证明。

原生与 WASM 均从独立源码目录完整重建，正向、逆向及最终源哈希校验通过。
native v7 为 `6b79becc…`（53 patch / 130 源文件），WASM 为 `d65cb046…`
（62 patch / 158 源文件）；两者使用各自的固件和运行证据，不能互授 PASS。
准确身份见 [summary.json](summary.json)。本地 v12 导出 manifest 为
`962697a2…`，2115 个资源、19 public / 0 candidate，不捆绑固件/ROM，
服务地址为空。静态资源审计通过不代表部署或全部浏览器功能通过。

最终 native v7 单轮 **68/68 PASS、278 项原始检查**，耗时 956.3 秒，每项仅
一次、无重试。132 份探针源码、两份 runner 和二进制保持不变，证据文件哈希
逐项绑定，结束后本轮 QEMU 残留为零。其中五项 C6 使用独立的既有完整 13 文件
runtime，不继承 Xtensa 补丁。见 [原生有界摘要](peripheral-v7.summary.json)。
最终 Python 平台检查为 **1613 tests OK、10 skipped**；被跳过项目不计执行
PASS，日志 SHA 在主摘要中保留。

[StackChan v7 浏览器有界摘要](stackchan-v7.summary.json)绑定同一 WASM、导出、
各自固件 SHA、UART/QOM/帧和独立模型几何。SCS 命令边沿、NVS 校准/RESET、
生命周期、三段显式扭矩 Dance 和原样未开扭矩的负控五项均通过；每项在关闭
浏览器 context **之前**达到零 live CDP Worker，累计精确观察 30 个 Worker。
原样 Dance 的负控 PASS 表示目标变化而实际位置不动，不表示它已正常跳舞。

同一导出的正常 DOM PWR 测试实际按住 6011.285 ms，guest 发出 SHUTDOWN，
exit0、iframe 数量为零、五个 pthread 已退出、无错误提示；但等待 30 秒后仍有
一个 `public-qemu-engine` target，附着后的常量求值也在 5 秒超时。因此该项
仍为 **FAIL**，owner 的 self-close 意图及最终强制关闭浏览器均不能授予退出
PASS。修复仍在评估，需另取新结果。实际 guest 反向目标间隔为 3082 ms，
不能表述为已验证 100 ms 中途反向。

Atom Lite、Atom Matrix、Atom Matrix v1.1 与原 StickC Plus 的既有本地上传
证据继续保留各自旧 runtime 身份。范围限固定 RGB/USER 或显示/BtnA 示例；
Matrix 仅验证 25 灯同色输出，IMU 轴向的参考源码尚未绑定到所测 stock 二进制，
不能据此认定 backend 或 SDK 缺陷。设备仍为 partial。v7 默认参考入口结果
待最终汇总，不从上传路径继承结论。

PM1 的默认 CFG1 `0x2a` 选择单击复位，450 ms 也超出默认 250 ms 短按窗口。
完整回归原轮与 100 ms 定向跟进的失败分别保留；定向跟进实际触发了板级复位。
按钮 IRQ 测试需由 guest 真实 I²C 明确禁用单击复位，再等待按键事件。C6 的
首轮五项在 dyld 阶段缺少冻结副本旁的依赖库，未执行 guest，归类基础设施错误。
后续修正夹具与依赖的结果独立记录，不改写原轮。此前 v6 的孤立 ReadPos
fallback、v7 attempt1 原样 Dance 的 WASM 越界和旧 PWR 清理失败也完整保留；
后续通过不证明它们的根因，也不构成可靠性保证。

可重建的 [Arduino 运动探针](../../../tests/firmware/stackchan_motion_contract/README.md)
包含固定官方 BSP 的生命周期、真实 NVS/RESET 与独立 SCSCL 协议路径。
原始镜像、ZIP、完整串口、Flash、帧系列和浏览器响应留在忽略存储，不进入源码
Git。速度控制曲线、PWM 机械行为及物理硬件不由定时位置模型的通过结果覆盖。

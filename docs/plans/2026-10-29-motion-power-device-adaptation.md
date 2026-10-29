# 设备运动、电源与复位链路修复

日期：2026-10-29。用户要求继续适配剩余设备，并报告 Arduino StackChan
跳舞只有屏幕、各型号长按电源和复位没有真实动作。

## 目标与约束

从最新主线与已有 Atom/Stick 接入复用控制器，优先补齐固件到外壳的舵机输出、
板级供电行为与同 guest 复位；不以网页动作替代控制器响应。
仅使用隔离工作区、自有 Device Service/静态端口，不访问用户 8787/8830 服务。

## 执行

1. 同步主线，核对 Arduino BSP、UIFlow2、PMIC/板级原理图与原有设备证据。
2. StackChan：原 UART1 SCS 控制器产生只读 present-position/torque/power
   快照，网页按明确标定映射到关节；分开屏幕 FT6336U 与顶部 Si12T 输入。
3. 电源：按 AXP2101、AXP192、M5PM1、Plus2 HOLD/USB 拓扑分别实现真实
   寄存器命令、计时和状态；不能把所有长按统一成 shutdown。
4. 复位：模型实际 RESET 控件进入固定 QMP system_reset，同实例保留 Flash；
   与重新创建会话、清空 Flash 和页面重载分开。
5. 剩余设备：先用 AtomLite 最小 MMIO/PC 实验验证 classic touch 启动假设，
   同时核验原 StickC Plus 准确镜像，不借用 SE/Plus2 固件。
6. 在新独占 QEMU 源码与构建目录完成 native/WASM 构建；逐路径收集相同
   guest 的输入、串口、帧、QOM 与正常退出证据。已知未实现行为保留 blocker。
7. 更新唯一 Backlog、当前状态和有界台账后提交 PR；正式站部署遵从用户授权。

## 验收

Arduino/UIFlow 分别保留准确镜像和驱动身份；舵机实际寄存器状态与模型读回一致，
扭矩/供电禁止运动的负控有效。复位有同 guest 新启动证据和 Flash 保留；
电源行为按具体供电拓扑核对，不从按键计数推导关机。虚拟与物理结论分开。

## Arduino 上传复现与当前收尾

用户已授权自行判断、修复后直接部署 fork Pages，不再追问固件来源。原样固定
StackChan-BSP `e2f3b02d` 的 Dance、仅增加观测的版本与显式开启 torque 的版本
已通过浏览器上传对照：前两者目标变化但 torque=0，显式开启后 actual position
变化。这个结果不推定用户未提供的固件有相同原因；网页需显示实际供电、UART、
torque 与机械显示范围状态，不能在网页上自动启用舵机来掩盖问题。

独立 Arduino/ESP-IDF NVS 探针排除 BSP 后，在旧 native `79ec2ace` 与 WASM
`3880086c` 均复现 set/commit 成功、重新打开和复位后读取失败。实际 Flash
字节已经写入，而 guest `esp_partition_read` 的摘要对应实际地址 +2 字节。
16 MiB 板选择 ISSI Flash，其 QIOR mode/dummy phase 为 3 字节；S3 旧桥接
硬编码 5 字节。当前修复必须按实际 Flash 模型选择相位，并保留 CS1 PSRAM
边界；随后以同一探针、实际 Flash 摘要、NVS 重开及同 guest 复位闭环。

本轮先验证 StackChan 默认示例、Arduino 上传、NVS 和复位/关断并更新预览。
其它新板只有独立 runtime/firmware 浏览器证据满足后才能新增公开准入；完整
共享控制器回归、更多固件和物理机械行为继续在唯一 Backlog 中维护。

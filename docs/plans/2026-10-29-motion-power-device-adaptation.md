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

## 部署后的追加验证

追加深测还定位到 S3 soft-I2C bridge 在硬件接管后未随 SoC RESET 恢复的
缺口：官方 M5GFX 用 GPIO bitbang 重验缓存板型时无法收到 ACK，落成 unknown。
需新增最小 bridge reset 修复，保留板端寄存器与 NVS，重新构建独立 native/WASM
运行时，并重跑共享控制器完整回归。舵机 RESET 边界先暂停读取实际位置，
区分复位本身与 BSP 随后初始化时的整数往返量化。

已合并最新 `origin/main` 至本工作分支；后续仍使用独立测试端口。
本次执行范围为经典 Atom 三板与原 StickC Plus 的原生及浏览器证据、
StackChan 三段官方舞步与中途换目标、扭矩重复写及模式切换回归。
协议检查已经复现重复写相同扭矩会重新计时，以及官方分步恢复角限被拒绝的
两项控制器问题；需在独立源码目录修复、锁定及重建后重新验证。
动画库自身的时间推进与机械模式缺口分别记录，不能通过网页插值隐藏。
Dial 和新增板型只有完成同板的浏览器验收才准入公开站，未通过的轴向或
输入时序检查继续留在唯一 Backlog，不从其它板的通过结果推导完成。


追加实际执行已完成 v6 原生单轮完整 68/68、278 项检查；每项一次、无重试。
最终浏览器三协议、校准及三段官方舞表实际运动均已通过，生命周期首次捕获
一次 SDK ReadPos=-1，同镜像低负载复核通过，保留首次失败且不据此归因负载。
真实源码回放另确认 S3 UART RXFIFO_RST 未清硬 FIFO 的数据面缺口，0098 仅补
该 S3 复位路径；已在独立 v7 完整构建后复验，不把 -1 直接说成超时或唯一根因。
自然关机已获得 SHUTDOWN/exit0 与 pthread 退出，但 engine target 仍在 CDP
存留，正在对 self.close/owner terminate 做有界隔离；未取得销毁证据前不授资源
回收 PASS。v7 原生最终完整回归 68/68、278 项检查通过；严格浏览器五组
测试通过，Stop 后在 context.close 前累计验证 30 个 Worker 全部销毁。
最终自然关机仍有一个 engine target 残留，作为已知限制进入 Backlog；
本轮冻结 v12 预览并如实交付，不将控制实验通过当作稳定修复。四板默认
参考入口继续用 v7 独立取证，不从旧上传路径或 v6 运行时继承。

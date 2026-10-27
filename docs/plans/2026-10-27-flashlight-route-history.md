# FlashLight GPIO 路由历史与状态恢复

日期：2026-10-27。归属 UNIT-01 / UNIT-HOST-38；状态：限定路由历史验收完成。
执行顺序仍以 project-backlog.md 为准。本块从 b3196cdf 开始，上一块已
fetch/merge origin/main@f2061759；不改旧 7c898 runtime 或原始失败证据。

当前复现是：Torch 或 Flash 已受验后，GPIO256→unsupported→GPIO256，
没有新的 EN 边沿或复位，旧内部资格会再次暴露。现有 getter 只检查当前 route，
不能表示 route 的生命周期。原失败已保留；本块通过新runtime的独立C、四host
八lane168执行与CoreS3 mounted13阶段闭合限定修复，见[证据](../evidence/2026-10-27-flashlight-route-history/README.md)。

实现约束：

- 从真实 SoC GPIO OUT_SEL 寄存器提交通知 Unit；保持原 LEDC 刷新语义，
  只命中相同 SoC layout、相同 EN pin 的 FlashLight 实例。
- 路由不再受支持时，立即撤销内部 known/active/qualified/ready，取消
  reset/settle/timeout 三个定时器和旧 deadline，更新 epoch 并清除旧 low 起点。
  getter 保持纯读；不能靠首次读属性才触发失效。
- 回到 GPIO 本身不能恢复旧资格，也不能增加边沿、脉冲或解码计数。
  本块保守要求重新观察真实 EN 高→低以及连续大于 500us 的低区间，
  然后通过既有数字状态机恢复。冷路由无边沿的 UNIT-HOST-37 保持独立。
- 不合成 LEDC/RMT EN 波形，不改动态 S1、原驱动长闪编码、完整 PWM、
  硬 reset 观察或光电/热/电气边界。资格 unknown 是模型边界，不是物理关灯结论。
- 新补丁置于 0045 后，使用精确候选树导出并验证 reverse check；最终 runtime
  从完整固定 patch stack 的新目录冷构建，不修改历史补丁或受验源树。

依据来自已固定的官方 AW3641E datasheet、U152 原理图、UIFlow2 原驱动及
M5UnitUnified AW3641E 实现，原始来源、指纹和边界保存在前块研究/证据中。
UIFlow2 程序还须先查 bundled flash_light/pin/display 等 API 文档。

验收：

- 独立 C 检查必须走实际 GPIO MMIO commit→route callback→内部状态链，
  包括 Torch、Flash deadline 前、PROGRAMMING、READY_LOW、RESET_PENDING、
  OUT_INV、其它 pin/layout、重复写入、旧 low/timer 不能跨 route 授资格、
  短低与 500000/500001ns 边界、真实新 low-reset 后恢复。原失败另存不覆盖。
- CoreS3、AtomS3R、StickS3、StopWatch 的 Flash/Torch 经 8787 可见会话，
  用真实 guest API/寄存器操作路由，核 serial→QOM→frame 及恢复；不能以
  QOM 写假数据替代 GPIO 控制器。每份证据绑定固件、profile、runtime 与源码 SHA。
- CoreS3 另做真实 mounted Web：亮灯→unsupported/unknown→回 GPIO 仍 unknown
  →实际 reset/新程序恢复；不能把隐藏贴图或空 HTTP200 body 当作状态证明。
- 修改共享 GPIO 控制器后，先窄检查，再运行受影响设备组/本块完整回归门禁。
  Xtensa 新构建与未重建的 C6 runtime 分开记录，不继承源码来源或物理结论。
- 功能先导出 ZIP，再 stop/close purge=0；保留历史末帧，核 PID、Flash、lease
  清理。归档原始指纹、文本/PNG、构建/测试 recipe，固件/ROM/原 ZIP 不入库。
- 最后生成 snapshot，运行平台/契约/目录 validators，更新状态、缺口与台账；
  只有对应层级证据通过才关闭 UNIT-HOST-38，不关闭整个 Unit 或 PWM 工作流。

本块完成后显式 whitelist 提交，再 fetch/merge 最新 main；不 push。

最终平台1220项、窄检查24项通过；共享控制器完整轮为66 PASS/1 Core2 IMU
FAIL，不补跑拼接，不关闭UNIT-HOST-21。UNIT-HOST-22命令记录另有旧/新负控
及实际PaperColor结果。37冷route、36hard-reset、S1/PWM/OEN/IOMUX和硬件不继承；
当前额外fall是保守观察策略，非芯片协议要求，后续依据留在同一证据根。

# FlashLight 冷初始化与 GPIO pad 连续观察

日期：2026-10-27，复核：2026-10-29。归属 UNIT-01 / UNIT-HOST-37；状态：计划验收完成。
本块从 `356d4ae2` 开始，前块已提交并 fetch/merge 最新 main，无冲突、未 push。
工作顺序仍由 project-backlog.md 维护，本页记录本项实施契约。

目标是让原 UIFlow2 FlashLight constructor 保持 EN 低后自然完成芯片复位，
不要求程序额外制造高→低。TOFF 是连续低电平时长，不是边沿前置条件；
新资格只能从实际控制器取得可信 low 的 t0 开始计时，不能借用未知区间。

## 数据面与实现边界

- 固定官方 AW3641E datasheet/U152 原理图及原 UIFlow2 driver；再以固定
  ESP32-S3 TRM/IDF 源码核对 GPIO OUT、ENABLE、matrix OEN 和 IO_MUX。
- 在真实 GPIO 控制器建立 per-pin before/after observation，覆盖 MMIO
  OUT/ENABLE/PAD_DRIVER/route、IO_MUX、external input、force、direct open-drain
  及 reset；相同写入、其它 pin 或 layout 不制造边沿或重置稳定低区间。
- legacy out listener 与新 observer 分开，避免 soft-I2C 对自己 ACK 的回声。
  新事件在 storage commit 后、可能产生嵌套写入的旧 listener/IRQ 前派发。
- snapshot 明确 pad level、known/conflict、route、OE、open-drain、mux、
  external source、board bias 和 reset epoch。默认兼容输入值不当作已知来源。
  R1 改为独立的 board pull-down，不再以 set_input 覆盖外部输入。
- S3 OUT_SEL=256 同时选择 GPIO_OUT/ENABLE；OEN_SEL 两值等价，OEN_INV
  反相 OE，OUT_INV 反相 data。按实际解析值更新 get_line/IN 与 observer，
  不把反相引起的真实 pad edge 当成旧的“无边沿路由往返”。
- IO_MUX 普通 GPIO function=1；准确存储/读回普通配置与复位值。未实现的
  peripheral waveform、sleep/RTC/hold 路径和无法解析的冲突保持 unknown，
  不由正常 GPIO 验收授予完整控制器或电气等价性。
- AW3641 只消费组合事件，不同时挂 legacy edge/旧 route hook。基线采样与
  真实边沿分开；失去来源时立即撤旧资格/三 timer/旧 low。重新可信 low 后
  从新的 t0 计满 >500us，仅先取得 known-off；active 仍须实际新程序。
- reset observation 在本项内需撤销 AW 资格，但不因此关闭整个 UNIT-HOST-36
  的其它 Unit 跨 hard-reset 计数问题。动态 S1、EN PWM 和物理光电/热另验。

## 验证

先做真实 C/controller 函数的正负控：冷 route→ENABLE→mux 无 pad edge，
500000/500001ns、短暂 high/source 中断、晚到 timer、重复写、其它 pin/layout、
低来源转换、OEN_SEL 等价与 OUT_INV/OEN_INV 真实边沿、reset/unknown 撤权。
保留旧实现失败与新实现结果，不能用独立 Python 假模型替代控制器数据面。

之后导出新 patch，使用完整固定栈的新源/新对象构建，不改旧运行时及其证据。
共享 GPIO 修改按项目门禁运行针对性与独立完整回归；已有 Core2 IMU 偶发失败
继续独立记录，不拼单例成全量 PASS。

通过 8787 可见 Device Service 运行四 S3 主机的 Flash/Torch：原 constructor
低保持，不附加人工下降沿，随后原 driver 程序/取消再 Run/Unit 状态和帧；
CoreS3 另验实际 mounted Web。微秒级边界由 C 证据判断，HTTP 分次采样不能
替代它。先 ZIP 再 stop/close，保留历史末帧，核 PID/Flash/lease 清理。

更新 authority、机器元数据和 snapshot，明确旧/新固件/runtime/source 各自范围。
仓内保存可复现文档和证据，外部 agent-work-logs 仍按用户豁免不做。
大块完成后显式 whitelist 提交，再 fetch/merge 最新 main，不 push。

## 本轮收尾

用户要求处理当前bug后收尾，不再扩展新Unit或AIFlow工作。0047 C实现、
完整源码重放/冷构建、软I2C上拉修复、22项受影响回归及平台1226通过已留[仓内记录](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-27-flashlight-cold-pad/README.md)。
后续新 `e318b2b7…` 已完成四 S3 主机原厂 constructor、100%/220ms Flash、
off Run 替换与原驱动读回；四台均从 `ready-low` 到 `flash-active` 再回
`ready-low`，保持同一 PID。CoreS3 actual QOM snapshots 已通过真实 mounted
Unit panel replay，见[四host证据](../evidence/2026-10-29-flashlight-cold-route-four-host/README.md)。
`UNIT-HOST-37` 的 cold constructor/低基线因此关闭。实时 Web 轮询、动态 S1、
EN PWM、完整 OEN/IOMUX、bit-exact 时序、光度/热/电气/真机仍独立；本页旧轮
准备包不替代这些结果。

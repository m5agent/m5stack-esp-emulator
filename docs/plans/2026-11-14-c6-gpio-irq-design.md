# C6 普通 GPIO 中断最小修复设计

日期：`2026-11-14`。本页记录已确认的实现方案，不授予 guest 或完整 GPIO
中断能力 PASS。当前基线是 `a5990e720a8c79310456bf5868141f4cfd50afe8`；
主分支、常驻服务和浏览器候选冻结，工作在独立分支推进。

现有 GPIO 可以解析输入、输出和共享 pad，但既未生成 GPIO IRQ，机器也未把
该输出连接到已有中断矩阵 source 30。矩阵本身已有其他外设的 level 路径，
因此修复只补 GPIO 数据面与连接，保留 PI4IOE/FT 的原共享 GPIO3 仲裁。
不重写 PLIC，也不通过 Python 或直接调用 ISR 绕过控制器。

实现将 raw `STATUS` 与 `PCPU_INT` 分开：前者捕获配置的边沿/电平事件，
后者根据各 pin `INT_ENA` bit 0 路由已锁存事件。W1TC 清除边沿事件；若电平
仍有效则重新断言。修改 mask 不丢原 pending；修改 type 不制造边沿。
reset 清中断状态/配置并拉低普通 IRQ，保留外部 I2C 器件实际驱动的 pad。
仅 C6 子类开启 31 pin 模型，其他子类默认保留原行为。

另两种方案——先重写整个中断矩阵，或把板级输入直接投递到 CPU/回调——
都会扩大范围或绕开真实驱动，故未采用。NMI source 31、wakeup、filter/同步
时序、BMI270 IRQ 状态机和 FT6336 脉冲模式各自保留明确边界。普通 `Pin.irq`
通过不能替代这些控制器功能，也不能替代电气或物理时序测量。

验证先做固定源文件的前后回放和 sanitizer 控制，再独立重放补丁/构建 C6。
随后分别通过公开 ESP-IDF GPIO ISR 和原版 UIFlow 的 `Pin.irq`，以同一 guest
的真实输入、source/寄存器、串口 callback、reset 与清理证据验收。
原版 BIN 的程序区保持不变，VFS 载入探针后的 Flash 身份单列。
旧 Mesh/Bruce 只作为非回归；原先失败不被后来的 PASS 覆盖。

完整命令、前置条件及待执行的 guest 控制见
[GPIO IRQ 回归入口](../../tests/firmware/esp32c6_gpio_irq/README.md)。

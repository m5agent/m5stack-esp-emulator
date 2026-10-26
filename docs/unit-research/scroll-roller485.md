# Scroll / Roller485 官方协议审计

日期：2026-10-26。归属 `UNIT-01`。本页是实现依据。Scroll已有独立、明确部分模型的候选运行时，逐主机验证范围另记；Roller485仍只有视觉外壳，内部模型与功能准入未实现。
不把官方驱动存在、寄存器文档或静态固件字符串称为 guest/controller PASS。
固定来源、大小与 SHA256 见[官方来源清单](../evidence/2026-10-26-live-unit-preview/official-units/sources.json)，
四款 reference 的[静态检查](../evidence/2026-10-26-live-unit-preview/official-units/reference-static-evidence.json)只证明模块/方法名存在，未运行这两款 Unit。

## Scroll

[官方产品](https://docs.m5stack.com/en/unit/Unit_Scroll)：STM32F030F4P6、EC10E编码器、按钮与单颗WS2812C。
默认7位I2C地址 `0x40`，与Encoder冲突，不能同挂被动HUB。规格的12 pulses/圈不能直接
当作guest count/圈；TIM编码器配置和机械角度换算仍需分别证明。

实现应固定[内部FW ae60717a](https://github.com/m5stack/M5Unit-Scroll-Internal-FW/tree/ae60717a4b9315cd12ac56389992fc2b7576d0aa)
的源码行为，而非把既有Encoder重命名。核心寄存器：

| 地址 | 内部固件行为 |
| --- | --- |
| `0x10..13` | 小端int32计数，支持部分字节读写 |
| `0x20` | 按钮，0为按下 |
| `0x30..33` | 保留/index、R、G、B；UIFlow从0x31写RGB |
| `0x40` | 写1清计数及增量 |
| `0x50..53` | 小端int32增量；选择寄存器并制作TX快照时清零 |
| `0x60 / 0xFB` | 方向 / AB或BA方向配置 |
| `0xFC/FD/FE/FF` | bootloader版本 / 跳bootloader / 固件版本 / I2C地址 |

[官方UIFlow驱动](https://github.com/m5stack/uiflow-micropython/blob/3a86d8f611b3639cca755a933e01a5a829771ef1/m5stack/libs/unit/scroll.py)
读取4字节却用 `struct.unpack('<h', buf)`，只暴露低16位。该MicroPython实现允许
buffer长于格式大小，不能用CPython的长度异常推断驱动坏。Arduino getter也返回
int16；其setter读取int16参数地址的4字节存在源码越界风险，不应复制该内存行为。
旧官方PDF另将多个系统寄存器误写成0xF0，并把计数描述为2字节；两种版本不可混算。

Scroll数据面覆盖原 `ScrollUnit` 的正负计数/低16位边界、增量快照副作用、按钮、
RGB、reset、版本与动态地址的限定子集。沿当前QEMU I2CSlave框架新增独立 `CONTROL_SCROLL`，
经GPIO matrix、主机控制器及真实I2CBus执行，保留原始int32寄存器。

## Roller485

[官方产品](https://docs.m5stack.com/en/unit/Unit_Roller485)：STM32G431CBU6、D3504 200KV电机、
DRV8311HRRWR及TLI5012BE1000。I2C默认 `0x64`；RS485默认Motor ID 0、115200/8-N-1。
协议不是Modbus。固定[官方内部FW 59d43890](https://github.com/m5stack/M5Unit-Roller485-Internal-FW/tree/59d43890ee25ea6101b3d801b96a6e5bb2670a4b)
中Markdown写FW V3，C源码声明V4，并有额外模式与扩展行为；实现前必须选择明确版本。

| I2C地址 | 功能/表示 |
| --- | --- |
| `00/01` | output、mode（speed/position/current/dial） |
| `0A..0F` | 超范围/堵转保护、status/error、按钮切模式 |
| `10/11/12` | Motor ID、波特率索引、RGB亮度 |
| `20` | 位置模式最大电流，LE int32，×100 mA |
| `30..33` | B/G/R与RGB模式 |
| `34/38/3C` | VIN×100 V、温度、int32编码器 |
| `40/50/60` | 目标速度×100 rpm、最大电流、实际速度 |
| `70/A0` | speed/position PID，3×int32，系数缩放1e5/1e7/1e5 |
| `80/90` | 目标/实际位置，×100 degree |
| `B0/C0` | 目标/实际电流，×100 mA |
| `F0/FE/FF` | 保存参数、版本、I2C地址 |

RS485控制请求15字节 `Cmd ID Data[12] CRC8`，响应17字节 `AA55 Cmd+0x10 ID Data[12] CRC8`；
查询请求4字节 `Cmd ID Option CRC8`，响应20字节，Data为15字节。
CRC-8/MAXIM reflected，init0、poly0x8C，响应CRC不含AA55；CRC/ID/长度错误无响应。
`00/01`开关/模式，`08/0A/0B/0C`编码器/RGB/波特率/ID，`20/22/24`速度/位置/电流目标，
`40..43`查询反馈与配置。`60..63`的RS485→I2C桥每块最多16字节，必须接真实下游I2CBus。
UIFlow RS485部分getter的read-command为None，不能发明额外查询命令。

完整模型还需运动/惯性/负载、限流、堵转/超范围/过压、按钮状态机、OLED、本地保存与I2C桥。
仅回显目标寄存器不能叫电机反馈；协议/运动模型也不能授予真实扭矩、FOC波形、热或电气PASS。
现有UART扩展入口是 `m5_unit_uart_tx()` 与实际RX FIFO/IRQ；新增帧解析不能绕过FIFO。

执行队列只维护在[项目Backlog](../project-backlog.md)；本页不提供另一套优先顺序。

### Scroll 当前候选的明确模型缺口

RGB当前按每事务同步消费、最新值读回的静态子集实现。官方FW将写入合并到
`rgb_color_buffer[index]`并推进index，main loop才依次显示并将index归0；
槽内容没有被清空。因此连续burst、跨槽partial写和LED排队时序不能由当前
latest-value模型推断。partial写探针只验证quiescent/slot0复用前提下的模型合同，
不宣称任意合法RGB burst与STM32内部固件等价。

固定源码`main.c:update_encoder`在AB反转后才加TIM wrap补偿；但同提交TIM3的
IRQ handler/NVIC链尚未闭合，不能将理想化modulo计数冒称该固件实际行为。
当前候选物理source-count限定[-32768,32767]，对应TIM16从0x8000起、不rollover，
单事件差分不超过32767；逻辑count/increment的int32溢出也拒绝，不静默回绕。
source与可写/reset的逻辑counter分开，不把寄存器操作解释成轴运动。

FE版本1来自固定应用源码；FC读取的是STM32 Flash字节，缺匹配bootloader内容，
当前不伪造版本。FD01不执行假bootloader，配置Flash持久化未实现。地址0虽为
该FW允许值，但QEMU总线把它当broadcast并抑制读，当前变更拒绝并保留旧址；
地址碰撞也明确拒绝。完整写完成时的callback error会增加command-errors，
不等于已完成写帧收到wire NACK；后续read拒绝与旧地址保留需真实guest另验。
超出官方局部缓冲区的未定义行为会有界早拒，不复制固件栈越界。

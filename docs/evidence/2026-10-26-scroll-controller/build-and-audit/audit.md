# Scroll 固定官方源码审计与可重放 oracle

日期：2026-10-26；开始 HEAD `662ca4e4`。本块仅只读审计源码、官方 MCP 和离线推导；guest/hardware 均 **NOT RUN**。机器可读的全部测试向量、来源 URL/SHA 与 blocker 在 [audit.json](audit.json)。未修改产品代码、未启动 guest。

## 固定入口

- 内部 FW：`ae60717a4b9315cd12ac56389992fc2b7576d0aa`。
- UIFlow：`3a86d8f611b3639cca755a933e01a5a829771ef1`。
- 本机缓存：`/tmp/m5-new-units-protocol-audit/{scroll_main.c,scroll_i2c_ex.c,scroll_tim.c,scroll.py}`，SHA 与仓内 sources 清单一致。
- 仓内已有研究：`docs/unit-research/scroll-roller485.md`；此前总计划：`docs/plans/2026-10-25-unit-runtime-integration.md`。没有把另一个未找到的独立 readonly 计划当作事实。
- 官方 MCP `knowledge_search` 已成功检索 ScrollUnit，bundled `uiflow2-coder/docs/unit/scroll.md` 已读；精确行为以下面的 pinned 源码为准。

## 确定协议

`main.c161..318` 在接收事务完成时解码整包；`i2c_ex.c117..121` 会在 repeated START 前提交 pending RX，`191..195` 在 STOP 提交；len0 无操作。
**不是每个 START_READ 都重拍寄存器**。只有合法单字节 pointer 才 `i2c1_set_send_data`，它复制有限快照并将 index 归0。每发一字节 index 按该快照长度循环，STOP 后没有新 pointer 就继续旧快照/index。未知 pointer、普通多字节写、reset 与地址更改不主动替换旧 TX。

| 地址 | 固定行为 |
| --- | --- |
| 10..13 | int32 LE count；从所选 offset 到 byte3 的有限快照；支持部分字节写，写 count 不增加 delta |
| 20 | 按钮0=按下；一字节快照重复，UIFlow 读两字节 |
| 30..33 | raw word 的 index/reserved,R,G,B；部分读写；UIFlow 写 `31 RR GG BB` |
| 40 | payload 首字节恰为1时清 count 和 increment；不重拍 TX |
| 50..53 | 选择时复制 remaining bytes，然后**立刻清全部 int32 increment**；即便 master 不读也清 |
| 60 | `!TIM counting_down`；不因 FB 翻转；静止保存上一次 DIR |
| FB | payload 非零归1，零归0；翻下一次计数差分；写回 flash；读一字节 |
| FC | flash `0x08000FFF` 的 bootloader byte，未有匹配镜像证据不能认定固定1 |
| FD | payload1进入真实 bootloader/reset 分支；本轮模型不能假装成功 |
| FE | 固定 FW version1，快照一字节循环 |
| FF | 只接受整包恰2字节且地址<128；固定源码允许0，模型若拒绝要明确 backend gap |

`ws2812.c82..86` 取 `R=word>>8,G=word>>16,B=word>>24`，所以写 `31 12 34 56` 后 raw=`0x56341200`，用户可见 RGB=`0x123456`。不是把 rawword 直接当 RGB。

## UIFlow 原 API 的关键差异

`scroll.py` 读取4字节但只 `<h` 解低16位；MicroPython允许较长 buffer。`get_rotary_value` 返回 `_start_value + signed16(count) - _zero_value`。`get_rotary_status` 只比较上次 value 的低16位记录，自己不更新它，所以连续查询可连续 true。

`set_rotary_value(7)` **只改 Python 偏移**，无 I2C 写，也不重设零点；count100 时随后 value=107。`reset_rotary_value` 才写 `40 01` 并清 Python 偏移。`set_color(index,rgb)` 忽略 index，写 `31 RR GG BB`。版本返回十进制字符串。没有公开方向或地址 setter。

## 最小事务 oracle

1. count=`0x12345678`，写 pointer11；read2=`56 34`；STOP 后无 pointer 再 read4=`12 56 34 12`。
2. 同 pointer11 后再注入变化，旧快照不改变；重新选择11才得到新 count。
3. increment=`0x12345678`，仅写 pointer51 就清零；无读取也清。随后注入+5，无 pointer 读仍是 `56 34 12` 循环；重新 pointer50 得 `05 00 00 00`，再选50得零。
4. count=`0x12345678` 写 `11 AB`，raw count=`0x1234AB78`，increment不变；公开值=-21640。
5. snapshot count5 后写 reset4001，无 pointer read仍为5，重选10才零。
6. FB0下 source+1→count+1/60=1；FB1下 source+1→count-1/60仍1；source-1且FB1→count+1/60=0。
7. 原 API 测 `32767→32768` 跳变-65535；`0→65536` 的 status 可为false；counter0/set70000 返回70000。
8. FF4142不改址；FF80不改址；FF41恰2byte后旧40NACK、新41ACK，读FF=41。

这些是源码推导的 callback 级 oracle，不是已测 guest PASS。完整41条向量见JSON。

## 采纳的保守 source-count 范围

root 已确定 `source-count ∈ [-32768,32767]`，代表合成绝对 TIM ticks，`TIM=0x8000+source`。单事件 abs(new-old)<=32767，用 int64 差分；FB 只翻转合法差分。count/increment 的结果越 int32 时明确报错。拒绝前不改 source、count、increment、direction 或 TX。

负控至少覆盖source32768/-32769、-20000→20000及反向过大跳、count/increment溢出/下溢、FB反转后溢出。原 driver 低16位边界可以通过原始 count register setter 布置，不需要声称 TIM rollover 已实现。

## 未闭合边界

- `tim.c128..131` 有 overflow callback，但已检查 `stm32f0xx_it.c` 没有 TIM3 handler，MSP也没见 TIM3 NVIC enable；目标 link/IRQ 可达性尚未证明。
- `main.c142..151` FB只翻encoder_change，未翻 ±65536补偿。条件性例：TIM65535→0、FB1且cDir=-1，delta=+131071；反向为-131071。若callback不可达则又是不同结果。禁止悄悄改成理想 modulo。
- int32 C有符号累加溢出不是可依赖协议，本轮failclosed，不授予2^31边界硬件行为。
- vendor rotation 仅 +X 右手轴；官方 EC10E PDF 有CW相序，但子型号、观察面、装配朝向及TI1映射未闭合。不能把12 pulses/圈直接当guest counts/圈，也不绑定正角=正count。
- address0在QEMU是broadcast，动态碰撞不是物理wire-AND复现；显式拒绝并保留旧地址属于已声明差异。
- bootloader FC值应明确fixture，FD模式和实际flash持久化/重启另验。
- 固定源码对过长 RX 有局部数组越界风险，Arduino int16 setter发送4byte亦有越界读；不能复制内存损坏。TX silicon预装载/NACK/时序仍是单独硬件层。

本轮可闭合有限、安全范围内控制协议及原API；不能把上述边界升级为完整STM32/物理Scroll等价。

## RGB oracle scope correction

Vendor main.c248..266 merges the current RGB queue slot, then advances its index. Main loop380..386 consumes queued slots and resets only the index, retaining slot contents. The rgb-partial oracle requires quiescent slot0 reuse; it is not valid for arbitrary burst/cross-slot writes. Current controller is a synchronous latest-value subset; queue depth, intermediate LEDs and scheduling remain explicit model gaps.

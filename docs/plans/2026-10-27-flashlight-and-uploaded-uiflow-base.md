# FlashLight 数据面与显式 UIFlow base

日期：2026-10-27。归属 UNIT-01，状态：本工作块完成，UNIT-01 整体继续。执行队列仍在 project-backlog.md。

前一块已完成checkpoint存储与旧程序保护，以及CoreS3官方兼容固件本地构建。
首次实际intake在session分配前被现有UART source/reference门禁拒绝，不能称为
新固件boot失败。保留原409和分类审计，通过扩展真实source composer推进，
不改manifest来源标签或绕过门禁。

新增可选base_firmware_id分支时必须钉住实际normalized stored bytes，并重验
base完整性、manifest/设备/SoC/Flash/PSRAM、安全与能力约束、实际应用/分区、
LittleFS布局。沿传base的运行约束，保持默认cached reference结果及旧ID兼容。
候选经public upload/import/compose创建可见8787会话，实际验证loader的模块
身份、重复运行、依赖更新、异常/格式失败、Ctrl-C与源码恢复。公共MPY能力
保持false，直到产品入口有同固件路径的独立验收。

FlashLight U152按固定AW3641E资料实现yellow EN真实GPIO边沿、QEMU虚拟时钟、
全16命令和Flash/Torch状态。S1是创建时fixture，initial全部应用后冻结，API和
Web都拒绝运行中写入。实际GPIO route/level不完整或超出受验时序时输出unknown；
不从LEDC占空比、Python参数或请求档位合成光输出。

500us稳定高后解码和首上升沿起算deadline是明确模型策略；推荐脉冲时序范围
之外不声称芯片必然失效。Torch无Flash超时，Flash档位只作相对码值显示；
光度、电流、电源、热、模拟电路和动态S1切换不在本块等价范围。原UIFlow长闪
错误编码保留原字节与negative结果，不能通过错误控制器解码让其通过。

新QEMU源码树/构建独立于已验2relay-final，追加0045补丁并核reverse-check和
源码/二进制SHA。先C时钟/定时器负控、catalog/视觉离线检查，再做实际Unit
同guest输入/输出/原驱动与Web反馈；新构建按门禁做定向与完整矩阵，旧Core2
IMU偶发失败不拼接补PASS。全部会话先ZIP再stop/close，保留历史并核资源释放。


验收：API 1.45 显式 UIFlow base 与内容来源冲突门禁、独立包容量配置已落地。
固定候选 loader 诊断通过，公共二进制入口仍关闭。FlashLight 以 partial 数字
子集准入，四主机 Flash/Torch 共8会话60次同VM Run、360 ZIP成员；CoreS3
真实Web五阶段通过，可选浏览器响应体捕获保持PARTIAL。新runtime完整单轮
67/67、平台1162项通过。详见
[分层证据](../evidence/2026-10-27-flashlight-and-uiflow-base/README.md)。

后续执行仍以 project-backlog.md 的 UNIT-01 为准：公共main.mpy入口、AIFlow
调用侧、SSE/实时分发与剩余Unit不由本块诊断或数字子集结果自动关闭。

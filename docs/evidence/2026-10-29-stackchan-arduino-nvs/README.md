# StackChan Arduino、NVS 与供电复测

本轮以固定官方 Arduino Dance 和不依赖 BSP 的独立 NVS 固件，分开验证
固件扭矩策略、S3 Flash 读取与真实模型关节输出。原生和 WASM
均已通过同固件的 8 项 NVS 验证，三阶段完整 Flash SHA 跨 runtime 完全一致。

旧 native/WASM 都实际写入了正确 Flash 字节，但 guest 分区读取偏移 +2，
导致 NVS 重新打开及复位后返回 NOT_FOUND。修复按实际 Flash 模型选择
QIOR mode/dummy phase：ISSI 3，Winbond/GigaDevice 5，CS1 PSRAM 保持原路径。
新 native 的写入/提交、重新打开准确值、同 guest 复位后保留、三次分区读取
摘要与实际 Flash 摘要一致，共 8 项通过。首次不存在的 key 删除返回
NOT_FOUND 是负控，不能称为已有 key 擦除验证。

Plus2 同一新 native 的 USB/电池两条原 SDK 路径共 13 项通过。USB 下原
Power.powerOff 进入真实深睡眠、保留同 PID 与供电并黑屏；该固定固件没有
启用唤醒源，不能声称电源按键唤醒已通过。电池路径由 guest 的长按/释放
调用原 Power.powerOff，GPIO4 HOLD 切断并自然 exit 0。RTC CRC 的硅片
等价性、正 EXT0 唤醒、其它固件与物理行为独立开放。

准确运行时、固件、Flash 和报告摘要见 [summary.json](summary.json)。
原始 Flash、固件、证据 ZIP、串口和截图仅保留在忽略存储，不进入源码 Git。
[Arduino 行为说明](../../stackchan-arduino-browser.md)包含固定 BSP 与最小扭矩
对照修改。完整共享控制器矩阵尚未重跑，不转授其它板型新版 PASS。


最终三组 Arduino 本地上传对照 29/29 通过：原样与仅观测版本的 torque=0，
目标变化但实际位置不动；显式启用 torque 后同 guest 的实际位置变化并映射到
模型。两份观测版本实际读回零位 460/620，UART 路由正确且无 SDK 读取回退。
这是对照实验通过，不能称原样 Dance 的运动通过。

默认示例在 v6 导出通过 9 项运动/同实例复位/6 秒长按自然关机和 Worker 清理
检查。最后还修正了关机完成后松开 PWR 误报“请先启动”的提示；v7 只改变
public.js，Arduino 上传在 v7 另通过 10 项实际运动、同实例复位、自然关机、
松开无错误提示及 iframe 移除前 Worker 全关闭检查。两个 manifest 分别记录，
不冒称未在 v7 重跑的全站验收。平台最终 1590 项测试完成，10 项跳过；四个
catalog/runtime/profile/snapshot validator 通过。

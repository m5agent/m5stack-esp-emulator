# StackChan Arduino、NVS 与供电复测

本轮以固定官方 Arduino Dance 和不依赖 BSP 的独立 NVS 固件，分开验证
固件扭矩策略、S3 Flash 读取与真实模型关节输出。当前原生修复已通过同一
固件的新旧对照；最终浏览器与公开 HTTPS 部署证据完成后追加本页。

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

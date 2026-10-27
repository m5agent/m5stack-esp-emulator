# Encoder / CardKB 资料版本边界

核对：2026-10-26。本页保留本批控制 Unit 模型实施期间的新证据；不表示
硬件等价或任意固件版本均已通过。

## Unit Encoder U135

官方产品页链接的
[Unit-Encoder_Protocol.pdf](https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/801/Unit-Encoder_Protocol.pdf)
标题为 V1、日期为 2022-05-13，按键栏写 `0: Released 1: Pressed`；当前
[官方可执行驱动](https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/libs/unit/encoder.py)
`get_button_status()` 则读取 `0x20` 后使用 `not bool(buf[0])`，是 active-low。
当前目录与仿真控制器明确选择 UIFlow 驱动兼容语义：按下为 0，松开为 1。
这两个来源不能混写成同一版本的已确认硬件真值。

该 PDF 还确认 `0x00` 的 Pulse/AB 模式字节、`0x10` 两字节计数及
`0x30` 的 `LED index,R,G,B`；index=0 同时设置两灯，1/2 分别设置单灯。
模式寄存器的存取不代表编码器模拟波形或机械旋转精度已经验证。

## CardKB U035-B

已独立读取产品页链接的
[v1.1 User Manual](https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/806/Unit_CardKB_v1_1_User_Manual_EN.pdf)
中的操作与四张键码表。其封面/正文标为 v1.1，但内页页脚写 CardKB2；保留
该排版矛盾，不据此引入较新 CardKB2 的 HID/report bank。

完整 50 键、normal/shift/sym/fn 字节及原 PDF SHA 保存在
[`cardkb-keymap.json`](../../platform/units/fixtures/cardkb-keymap.json)。按键矩阵
状态通过 QOM `keys` 的 50 项 bool 数组注入，C 模型产生并经 I2C `0x5F`
读出的按键字节。`keycode` 仍可注入确定的字节测试序列，不能与真实按键
矩阵状态混为一类证据。`0x02` 探测返回 legacy 状态，不伪装 v2 8 字节报告。

单击一次/双击锁定、再点击解锁来自手册；200 ms 双击窗口可在官方旧版
[MCU 源码](https://github.com/m5stack/M5-ProductExampleCodes/blob/1bc38736e61a362080d1dffc4020b3a2a1dff6ae/Unit/CARDKB/firmware_328p/CardKeyBoard/CardKeyBoard.ino)
中找到，但该文件是 ATmega328P 路径，并非本产品 ATMega8A 固件二进制。
当前模型采用该时间窗口作为明确的仿真策略，不能称为 U035-B 实测时序。

## 其他明确策略

- 8Encoder increment 在完整读取一个 int32 后清零，部分读取保留。
  这是当前仿真策略；掉电保存、增量清除和机械计数模式仍需匹配内部固件。
- 8Encoder 地址变更在同一会话生效，不宣称物理 Flash 持久化。
- RFID2 保留 WS1850S 产品说明与 MFRC522 原理图身份冲突。仿真实现的是
  MFRC522 兼容 I2C/FIFO/CRC/PICC 命令；卡内容为无生产数据的合成 1 KiB
  fixture，transport key `FFFFFFFFFFFF` 仅用于这张测试卡。
- RFID RF/调制、Crypto1 波形、自检指纹、MIFARE value/Ultralight 和完整
  access-bit 策略不是当前读 UID/认证/块读写子路径的可继承结论。

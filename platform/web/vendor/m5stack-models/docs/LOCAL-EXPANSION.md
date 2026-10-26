# 本地 Unit 扩展批次

2026-10-26。本页整理当前公开工作副本中的本地增量，便于其他Agent接入、查阅各批证据和续作。

当前catalog为14款主机、113款Unit，共127款；阶段计数`{"modeled": 127}`。生成本页时的提交基线为`32c95e05ded1bb7f1ff6437f5bce0db9bf91eefd`，该基线catalog有112款。此页描述当前源码快照；当前提交和远端状态以Git日志及GitHub main为准。各历史progress中的未提交/未推送字样只描述各自保存时点。 本次[127款源码同步](GIT-SYNC-127-2026-10-26.md)包含这15款增量、28张PNG及三旧端子闭合修复。

| 批次 | 产品ID | 检查点 |
| --- | --- | --- |
| GPS v1.1 / Weight-I2C / 8Servos | gps-v11 / weight-i2c / 8servos | [本地进度](../artifacts/unit-expansion/progress.json) |
| Fader / 8Angle / Mini Scales | fader / 8angle / mini-scales | [本地进度](../artifacts/interactive-unit-expansion/progress.json) |
| Weight-I2C / 8Servos 可拆端子 | 见记录 | [本地进度](../artifacts/unit-terminal-accessories/progress.json) |
| PaHUB v2.1 / PbHUB v1.1 / Gesture | pahub-v21 / pbhub-v11 / gesture | [本地进度](../artifacts/multiport-unit-expansion/progress.json) |
| OLED / LCD / CO2 | oled / lcd / co2 | [本地进度](../artifacts/display-co2-unit-expansion/progress.json) |
| Joystick2 / ByteSwitch / ByteButton | joystick2 / byteswitch / bytebutton | [本地进度](../artifacts/byte-joystick-unit-expansion/progress.json) |
| 2Relay / 4Relay / DMX | 2relay / 4relay / dmx | [本地进度](../artifacts/relay-dmx-unit-expansion/progress.json) |
| CAN / ENV Pro / ToF4M | can / env-pro / tof4m | [本地进度](../artifacts/can-env-tof-unit-expansion/progress.json) |
| RollerCAN / RollerCAN Lite / Vibrator | rollercan / rollercan-lite / vibrator | [本地进度](../artifacts/rotating-unit-expansion/progress.json) |
| RTC / Fingerprint2 / AudioPlayer | rtc / fingerprint2 / audioplayer | [本地进度](../artifacts/rtc-fingerprint-audio-expansion/progress.json) |
| PoESP32 / CamS3-5MP / Synth | poesp32 / cams3-5mp / synth | [本地进度](../artifacts/network-camera-synth-expansion/progress.json) |
| 近期30款Unit同步贴纸 | poesp32 / cams3-5mp / synth / 8angle / pahub-v21 / pbhub-v11 / 2relay / env-pro / fingerprint2 / byteswitch / bytebutton / gps-v11 / weight-i2c / 8servos / fader / mini-scales / joystick2 / gesture / oled / lcd / co2 / tof4m / rtc / 4relay / dmx / can / rollercan / rollercan-lite / vibrator / audioplayer | [本地进度](../artifacts/unit-sticker-additions/progress.json) |
| Mini IMU / EXT.IO2 / ACSSR | mini-imu / extio2 / acssr | [本地进度](../artifacts/imu-extio-acssr-expansion/progress.json) |
| Step16 / ASR / UHF-RFID | step16 / asr / uhf-rfid | [本地进度](../artifacts/step-asr-uhf-expansion/progress.json) |
| Earth / Hall / QRCode | earth / hall / qrcode | [本地进度](../artifacts/earth-hall-qrcode-expansion/progress.json) |
| Laser TX / Laser RX / MIDI | laser-tx / laser-rx / midi | [本地进度](../artifacts/laser-midi-expansion/progress.json) |
| DAC2 / DDS / KMeter-ISO v1.1 | dac2 / dds / kmeter-iso-v11 | [本地进度](../artifacts/dac-dds-kmeter-expansion/progress.json) |
| TimerPWR / ExtEncoder / NFC | timerpwr / extencoder / nfc | [本地进度](../artifacts/timer-encoder-nfc-expansion/progress.json) |
| ADC v1.1 / AMeter / VMeter | adc-v11 / ameter / vmeter | [本地进度](../artifacts/adc-meter-expansion/progress.json) |
| Tube Pressure / MQ / LoRaE220-920 | tube-pressure / mq / lora-e220-920 | [本地进度](../artifacts/radio-gas-pressure-expansion/progress.json) |
| Watering / HBridge v1.1 / DLight | watering / hbridge-v11 / dlight | [本地进度](../artifacts/watering-light-hbridge-expansion/progress.json) |
| DCSSR / NCIR2 / Reflective IR | dcssr / ncir2 / reflective-ir | [本地进度](../artifacts/dcssr-ncir2-reflective-ir-expansion/progress.json) |
| Thermal2 / FlashLight / GPS SMA | thermal2 / flashlight / gps-sma | [本地进度](../artifacts/thermal2-flashlight-gps-expansion/progress.json) |
| BLDC Driver / RCA / Puzzle | bldc-driver / rca / puzzle | [本地进度](../artifacts/bldc-rca-puzzle-expansion/progress.json) |
| RS485-ISO / AIN4-20mA / AC Measure | rs485-iso / ain4-20ma / ac-measure | [本地进度](../artifacts/isolated-interface-expansion/progress.json) |
| UWB / TMOS PIR / Mini ToF-90 | uwb / tmos-pir / mini-tof-90 | [本地进度](../artifacts/ranging-presence-expansion/progress.json) |
| Roller485 Lite / Mini CAN / INA226-10A | roller485-lite / mini-can / ina226-10a | [本地进度](../artifacts/roller-mini-can-ina226-expansion/progress.json) |
| Mini PDM / Mini BPS v1.1 / MIC | mini-pdm / mini-bps-v11 / mic | [本地进度](../artifacts/audio-pressure-expansion/progress.json) |
| Accel / OP90 / OP180 | accel / op90 / op180 | [本地进度](../artifacts/accel-op90-op180-expansion/progress.json) |
| Unit ID / RF433R / RF433T | unit-id / rf433r / rf433t | [本地进度](../artifacts/id-rf433-expansion/progress.json) |

各进度记录绑定相应批次的源码/检查范围。近期新增只执行必要局部结构、动作/API、接线夹具及构建；没有逐面浏览器复核或全量验收。`modeled`表示已有实现，不能视为完成视觉或实物配合验收。

## 接入入口

- [Agent总指南](AGENT-INTEGRATION.md)：按需loader、输入/外驱状态、层级地址与生命周期。
- [Unit ID/RF433R/RF433T](ID-RF433-UNITS.md)：真实加密IC与接收/发射封装、固定PCB天线和同步贴纸。
- [Accel/OP90/OP180](ACCEL-OP90-OP180-UNITS.md)：真实加速度封装、两种固定光电叉与检测空气槽及同步贴纸。
- [Mini PDM/Mini BPS v1.1/MIC](AUDIO-PRESSURE-UNITS.md)：真实声学/气压封装、声孔与可调头及同步贴纸。
- [Roller485 Lite/Mini CAN/INA226-10A](ROLLER-MINI-CAN-INA226-UNITS.md)：真实电机转子、非隔离CAN与隔离采集端子及同步贴纸。
- [UWB/TMOS PIR/Mini ToF-90](RANGING-PRESENCE-UNITS.md)：内置天线、真实红外感测窗口与固定直角双板/原稿印刷。
- [RS485-ISO/AIN4-20mA/AC Measure](ISOLATED-INTERFACE-UNITS.md)：真实隔离芯片/四位端子、可拆跳帽与原稿印刷。
- [BLDC Driver/RCA/Puzzle](BLDC-RCA-PUZZLE-UNITS.md)：真实三相连接器、音视频插座/壳内双通道开关和64灯外驱/物理级联。
- [Thermal2/FlashLight/GPS SMA](THERMAL2-FLASHLIGHT-GPS-UNITS.md)：热成像采集头/原壳舌、固定白灯/壳内选择器和可拆有源带线天线。
- [DCSSR/NCIR2/Reflective IR](DCSSR-NCIR2-REFLECTIVE-IR-UNITS.md)：完整直流SSR、实际测温头/按钮和红外阈值调节头。
- [Watering/HBridge v1.1/DLight](WATERING-LIGHT-HBRIDGE-UNITS.md)：真实泵/极板、驱动端子与稳定电源选择器、环境光感测实体。
- [Tube Pressure/MQ/LoRaE220-920](RADIO-GAS-PRESSURE-UNITS.md)：真实气嘴、金属感测罩、可拆配件与无线模组DIP形状。
- [ADC v1.1/AMeter/VMeter](ADC-METER-UNITS.md)：真实模拟输入/测量插座、可拆端子与外驱螺钉头。
- [TimerPWR/ExtEncoder/NFC](TIMER-ENCODER-NFC-UNITS.md)：真实按键、外部屏幕、五芯插头与NFC实体。
- [DAC2/DDS/KMeter-ISO](DAC-DDS-KMETER-UNITS.md)：可拆端子、SMA同轴与K型扁插座/附件。
- [Laser TX/RX/MIDI](LASER-MIDI-UNITS.md)：发射/接收光学实体、DIN/TRS插座与真实稳定滑块。
- [Earth/Hall/QRCode](EARTH-HALL-QRCODE-UNITS.md)：土壤探针、固定磁感实体、真实触发键/通讯滑块与独立灯。
- [Step16/ASR/UHF](STEP-ASR-UHF-UNITS.md)：旋钮、原生七段/RGB外驱、固定声学与RF实体。
- [IMU/扩展IO/ACSSR](IMU-EXTIO-ACSSR-UNITS.md)：纯实体锚点、真实排针、按键/螺钉与独立外驱灯。
- [近期Unit贴纸](UNIT-STICKER-ADDITIONS.md)：30款原稿/参考重绘、来源、开关与必要局部检查。
- [网络/摄像/合成Unit](NETWORK-CAMERA-SYNTH-UNITS.md)：真实网口、固定镜头、内置喇叭与同步贴纸。
- [旋转Unit](ROTATING-UNITS.md)：转子、真实弹舌和移动Grove输出。
- [显示Unit](DISPLAY-UNITS.md)：独立与嵌套framebuffer。
- [可动输入Unit](INTERACTIVE-INPUT-UNITS.md)：稳定开关、瞬时键和双轴摇杆。
- [Relay与DMX](RELAY-DMX-UNITS.md)、[CAN与环境/测距](CAN-ENV-TOF-UNITS.md)、[RTC/指纹/音频](RTC-FINGERPRINT-AUDIO-UNITS.md)。

## 端子闭合修订

AC Measure/AIN4-20mA/BLDC Driver插舌已补孔下壁；当前SHA/局部证据见[闭合修复](TERMINAL-TONGUE-CLOSURE.md)。原批22/23及批25的冻结/进度保留为历史快照，不能拿旧SHA当当前源。该修复不增加型号/PNG数。

## 保留的边界

提供给公开分发的新增代码使用MIT，第三方CAD/标识/图片保留各自权利。CSV、矢量原稿、私有映射、生成器和中间材料继续在仓库外；只分发已授权的普通PNG和配准代码。原始官方STL、照片/PDF和MCP长篇原文不加入公开包。

旧50张参考重绘PNG保留为未完成全批复核的检查点；私有实现尚未整批同步这些重绘。私有Scroll结构WIP与公开新增Unit分开保留，禁止整树覆盖或夹带发布。StackChan生产装配基准及隐藏配合仍未闭合，整体goal保持active。

本地预览为<http://127.0.0.1:5188/>。`npm run catalog`生成loader、服务catalog与STATUS；各批专项命令见对应指南。后续新增时应按本页批次和当前实际diff保留依赖，保留公开基线已有的素材净化规则。

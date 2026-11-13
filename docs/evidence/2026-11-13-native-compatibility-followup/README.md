# 原生固件兼容性后续

日期：`2026-11-13`。验证类型：`virtual-device validation`。

这些修复沿原固件实际 controller、bus、DMA/FIFO 和板级接线执行。未修改
原 BIN、禁用 watchdog、延长原输入或伪造云端响应。这里的局部 PASS 不授予
其它固件、browser-WASM 或物理硬件通过；最终组合回归和交付单独记录。

| 问题 | 已执行结果 | 证据与复现 |
| --- | --- | --- |
| #205 | 五份原版 StickS3 BIN 的 display 方向与真实 MADCTL 逐像素一致；raw/触摸保持独立契约 | [帧方向](../2026-11-13-native-frame-orientation/README.md) |
| #188 | 完整 Flash/ELF 身份、服务隔离与旧参考首触摸已修；最新原版在闭源 P4 CSR/DSI 路径仍失败 | [边界对照](../2026-11-13-tab5-service-boundaries/README.md) |
| #221 | Matrix 原版两次 130 秒，Lite 和 Matrix v1.1 各 130 秒；真实 RMT 灯阵与按键通过，Matrix 两型号实际网络 HTTP 404 保留 | [Wi-Fi/RMT](../../../tests/firmware/classic_factory/README.md) |
| #222 | 严格板级 CS/FIFO 修复让 HamRadio 越过错误板型探测；Core2 SPI SD 支持原应用选文件，UIFlow2 512 字节 DMA 写读与独立磁盘 oracle 通过 | [面板与 SD](../../../tests/firmware/classic_panel_cs/README.md) |
| #222 | Cache 同步只失效已改变的映射，并合并单次寄存器写的内存拓扑更新；原 UIFlow 的资源加载和硬件 CS 原应用对照分别保留 | [缓存与原应用](../../../tests/firmware/classic_cache_boot/README.md) |
| #216 | Bruce 原版从 LittleFS 读取错位恢复到菜单；真实 QIO/DIO 与擦除后探针通过 | [QIO Flash](../../../tests/firmware/esp32c6_flash_qio/README.md) |
| #216 | SX1262 实际硬件/软件 SPI 共用寄存器和 FIFO；Meshtastic 越过旧 radio 初始化失败，原 140 秒黑帧保留为较晚采样，后续主循环、显示与休眠另有独立证据 | [SX1262](../../../tests/firmware/esp32c6_sx1262_spi/README.md) |
| #216 | 无 host backend 仍有 PHY 计时器，但没有虚构 AP/RX；BLE 独立 AES 控制器执行真实单块 DMA 加密，LPPERI RNG 经真实 MMIO 接入 guest-random | [射频控制器](../../../tests/firmware/esp32c6_radio_controllers/README.md) |
| #216 | Nesso MADCTL 与 SPI2 18 位长度修复后，同原 Meshtastic 显示完整欢迎页、响应按键、自然休眠后按键唤醒；实际 C 正反对照覆盖 DMA 无通道与 FIFO 混合路径；GPIO matrix 硬件片选与未选中/无线电隔离另有 16 项 guest、24 项 actual-C 对照 | [显示与 DMA](../../../tests/firmware/esp32c6_panel_madctl/README.md) |
| #216 | Launcher 原版发生 mutex owner/current task 不匹配；RFID 原版寄存器转储、重启与黑帧仍未解决。缺少 PN532Killer 外设不能单独证明崩溃原因，均未授予整应用 PASS | [原版边界](../../../tests/firmware/esp32c6_radio_controllers/remaining-originals-2026-11-13.json) |
| #223 | 两份原 BIN 和 UserDemo 的未修 SDK 公开源码重建均崩溃；GPT 没有独立未修源码重建负控。仅加入官方 I2C 补丁的两款重建版各 360 秒、真实动画/触摸/UART 协议通过 | [源码与控制实验](../../../tests/firmware/s3_i2c_lifetime/rebuild-applications.md) |
| 服务输入 | QOM 错误清空 QMP 连接后，下一次原生输入通过统一重连路径进入同一 guest | [输入恢复](../../../tests/firmware/service_input_reconnect/README.md) |

当前整合交付：`NOT RUN`。此前全量平台 2,128 项通过、8 项按依赖可用性
跳过；新增 C6 显示、DMA 和片选修复后的最终完整矩阵、平台复验、main/常驻
更新及发布后复验尚未完成。本页不会把中间候选二进制描述为已部署版本。#192 的早期
完整 68 case 基线通过，但高负载覆盖不足；新增 Core2 SD 后须按现有完整
case 集合重新执行两轮，不能复用旧计数。

硬件、RF、物理熵、机械运动、声学、电气和安全属性均不由这些模型结果
推导。所有原始失败、观察器/夹具错误、源代码与二进制身份、输入及清场
保留在各自日期化摘要；无固件或 ROM 二进制进入源码仓库，未提交 Burner。

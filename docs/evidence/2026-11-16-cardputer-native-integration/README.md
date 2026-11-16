# Cardputer 原生组合运行时验证

日期 2026-11-16。实际执行源码 f2f26604a5e8c8df898aa5ba2354364e6f1911d5，
Xtensa 06db397cbe804e9eb13390d797cd67ca33ce5f29048fe7a56342cb66f4d2f9e0。
从已验证 0202 源码按 0203、0204 顺序正向应用、逆向核对，重新编译全部 QEMU 对象。
[构建摘要](build-summary.json)和[定向验证](targeted-summary.json)固定了固件、ROM、输入、实际帧和清理状态。

[#229](https://github.com/m5agent/m5stack-esp-emulator/issues/229) 的原版 M5Apps 2.7
不再停在 ROM Cache_Occupy_Addr 等待。0203 模拟 ENA/DONE 和地址/长度寄存器，并在与
ESP-IDF 16 KiB 数据缓存设置相符的 DROM 范围提供实际 SRAM。普通 Flash/PSRAM 走原有 MMU，
IROM 指令映射保持独立。先前仅补完成位的候选仍在写入 heap 时崩溃，其证据留在
[控制器与原版记录](../../../tests/firmware/esp32s3_cache_occupy/evidence-2026-11-16-original.json)。

组合运行时上，原版近 4 秒出现按任意键提示。经过空闲等待，36 秒和 61 秒样本黑屏。
在有、无 SPI 跟踪的独立会话中，A 唤醒启动页，Enter 进入 SETTINGS / INSTALLER / FDISK，
两次主菜单画面哈希相同。[原版默认设置](https://github.com/d4rkmen/M5Apps/blob/e35868a3ae9d5799f95531031b7e5bb5fa9b37b4/main/settings/settings.cpp#L72)、
[唤醒键处理](https://github.com/d4rkmen/M5Apps/blob/e35868a3ae9d5799f95531031b7e5bb5fa9b37b4/main/hal/keyboard/keyboard.cpp#L77)
和[渐暗到休眠](https://github.com/d4rkmen/M5Apps/blob/e35868a3ae9d5799f95531031b7e5bb5fa9b37b4/main/apps/launcher/launcher.cpp#L362)
支持这次时间线。首次把旧候选的黑帧误用于最终候选，实际读取 PNG 后更正。
ST7789V2 ID 0 仍记录于串口，应用进入主菜单的验证不依赖该读值。

[#230](https://github.com/m5agent/m5stack-esp-emulator/issues/230) 的四个原版执行映像
均能绘图并响应同一按键验证。Tiny Journal 接受 x 并写入笔记，MacroCard Enter 反馈未分配，
Frequency and Noise Generator Enter 切到播放，CapLab Enter 进入遥控采集页。
ADV 两份样本都从 GPIO I2C 读到 TCA8418 ACK，并在硬件总线读到 Enter 的按下和松开。
MacroCard 复用前次审核的 app-only 组合与原 app，未修改其应用代码。
[基线与独立板型修复](../2026-11-16-cardputer-gpio-board-detect/README.md)
保留四份黑帧以及仅修面板时 ADV 键盘无响应的对照。

复用两份定向记录的 Device Service API 启动及输入步骤。使用锁定的原生运行时和 ROM，
运行 tests/firmware/esp32s3_cache_occupy/run_qtest.py 及
tests/firmware/stickc_plus2_bt_lp_clock/check_gpio_lcd_readback.py 的四板检查。
六个会话均在停止前导出 ZIP，并核对 ZIP 成员与清理。
验收为 virtual-device validation，范围是启动、显示、键盘和已声明的控制器合同。
网络、存储、声学/电气、浏览器 WASM 及物理设备为 NOT RUN。

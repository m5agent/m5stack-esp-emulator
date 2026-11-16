# Cardputer 系列 GPIO 板型探测复验

日期 2026-11-16。验证类型为 **virtual-device validation**，对应 [#230](https://github.com/m5agent/m5stack-esp-emulator/issues/230)。[逐样本证据](native-targeted.json)记录原始文件与实际 Flash 的 SHA-256、原生运行时身份、帧像素、按键、控制器事务和会话清理。

同一 Device Service 上，基线的四个原版执行映像在 61 秒时均为 240×135 全黑，串口均报 `Unsupported board type: 136`。两款 Cardputer 和两款 Cardputer ADV 共用 ST7789V2 接线。较新 M5GFX 从 GPIO 读 `0x04`，基线只在 GP-SPI 数据通路提供面板 ID。修复把已有 StickC Plus2 GPIO SPI 适配器移进面板模型，两条总线输出同一面板的响应。真机接线见 [Cardputer](https://docs.m5stack.com/en/core/Cardputer) 和 [Cardputer ADV](https://docs.m5stack.com/en/core/Cardputer-Adv) 的 LCD 管脚表。

只补面板读回时，四款应用都有画面，两款 ADV 固件都未响应三次已接受的按键。ADV 的软件 I²C 探测还需要从 GPIO8/9 读到现有内部总线的 TCA8418 `0x34` ACK。接入同一总线后，两款 ADV 正常探测，并在硬件 I²C 键盘事件寄存器 `0x04` 读到 Enter 的按下 `0xc3` 和松开 `0x43`。Cardputer 的键盘继续走 GPIO 矩阵。

| 原版固件 | 设备 | 4 秒采样 | 36 秒非黑像素 | 输入和实际应用结果 |
| --- | --- | --- | ---: | --- |
| Tiny Journal 2026.11.14 | Cardputer | 非黑 | 4,545 | 输入 `x`，显示字符且笔记长度由 0 变 1 |
| MacroCard 1.0.0 | Cardputer | 非黑 | 12,829 | Enter 后菜单显示 `[enter] not assigned` |
| Frequency and Noise Generator 1.0 | Cardputer ADV | 非黑 | 9,497 | Enter 后 `stopped` 变为 `174 Hz` 播放状态 |
| CapLab 1.5.1 | Cardputer ADV | 非黑 | 32,400 | Enter 从主菜单进入采集遥控页 |

MacroCard 复用原审查保留的 app-only 组合镜像 `2d793ad1…`。其余样本复用原 BIN，由服务按设备要求填充空 Flash。候选未改动固件。四份 ZIP 的 CRC 和 manifest 成员哈希均通过，停止后保留历史并释放 Flash 和 QMP socket。

现有 qtest 在两款 Cardputer、StickC Plus2 各通过 14 项，在 Core2 的未接入 GPIO 控制通过 13 项。两款 Cardputer 的 GPIO 与硬件 SPI 均读到 `0x81`，StickC Plus2 保持 `0x85`。基线 Cardputer 的 GPIO 控制读到 `0xffffffff`。有关主机接线、CS、D/C、方向、换向时钟、半条命令和复位的检查使用实际 MMIO。

## 复现

从 `0202` 后的已验证原生 Xtensa 源码应用 `0204`。常规构建使用 `scripts/bootstrap-unit-runtime.py` 的锁定源码与构建配方。上述候选为差分试验，重新编译四个受影响对象后，使用基线的其他对象与同一链接命令。

以 `M5_QEMU_XTENSA` 和 `M5_QEMU_XTENSA_ROM_DIR` 指向该可执行文件及其 ROM，在独立端口和状态目录启动 Device Service。上传同 SHA 原件及 MacroCard 组合镜像。为每个样本创建 `runtime=qemu` 会话，采集 `/serial` 和 `/frame.png`。使用 `/input` 发送 `kind=key`、`action=tap`、`hold_seconds=0.22`。启用 `M5SW_SPI_TRACE`、`M5SW_SOFT_I2C_TRACE`、`M5SW_I2C_TRACE` 观察面板和键盘事务。下载 `/evidence` 后以 `purge=0` 停止。

```sh
python3 tests/firmware/stickc_plus2_bt_lp_clock/check_gpio_lcd_readback.py \
  --qemu "$xtensa_binary" --rom-dir "$xtensa_rom_directory" \
  --machine m5cardputeradv --expected-id 0x81
```

ADC 校准及 MacroCard 的 LittleFS、SD、USB 和 NVS 报错仍出现。板型、显示和按键之外的应用功能，以及物理设备、浏览器 WASM，均为 NOT RUN。

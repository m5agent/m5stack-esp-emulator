# Tab5 原版启动：触摸探测、USB 与旧 P4 CSR 对照

日期：`2026-11-16`。**#226、#227 保持 PARTIAL / OPEN，未交付后端修复。**
本轮是独立 Device Service 的 **virtual-device validation**。两个原版 BIN
与 issue SHA 一致，所有执行都保留真实 ESP-Hosted C6 伴生实例。
[逐轮身份与结果](summary.json)保留九次 guest 执行及一次分配 guest 前的运行器错误。

## 同原版的实际结果

| 固件 | esp-emu 0.50.0 | esp-emu 1.0.0 |
| --- | --- | --- |
| CarPlay-Tab5 1.0.0，`4f3bb118…` | 硬件断点读到 `bsp_get_board_version bsp_display.c:189 (NULL)` | 反复启动；旧 abort 断点在有界观察中未命中。后续 CSR 对照在 `0x4ff014c0` 的 `csrr a4,0x346` 单步后进入异常向量 `0x4ff00000` |
| M5TabOS 0.9.1，`08aa10d0…` | 硬件断点读到 `usb_dwc_hal_init usb_dwc_hal.c:152` 的 GSNPSID 断言 | 反复启动；旧 abort 断点在有界观察中未命中。后续 CSR 对照在 `0x4ff0255a` 的同指令单步后进入异常向量 `0x4ff00000` |

两个原版在 **0.50.0 的同 CSR 单步正控均到达 PC+4**，分别是
`0x4ff014c4`、`0x4ff0255e`。所有断点均为 GDB `hbreak`，没有修改指令、
寄存器或 guest 数据；CSR 对照仅额外单步执行原指令。因此新版失败不能写成
“仍命中同一触摸/USB 断言”，也不能用升级后的重启去否定旧版断言证据。

每个会话先自然观察约 18 秒，再做 GDB 取证。摘要中的 ROM boot 计数来自最终 ZIP，
包含后续调试耗时，不是每 18 秒的启动率。应用分区在取证后的完整 Flash 中逐字节
保持原样；归一化只在上传镜像尾部填充 `0xff`。

CarPlay 的 app descriptor 是 ESP-IDF `v5.5.3`，M5TabOS 是 `5.5.5`。
两版官方源码都为旧修订 P4 定义 `mintstatus=0x346`，见
[v5.5.3](https://github.com/espressif/esp-idf/blob/v5.5.3/components/riscv/include/esp_private/interrupt_clic.h#L50-L58)、
[v5.5.5](https://github.com/espressif/esp-idf/blob/v5.5.5/components/riscv/include/esp_private/interrupt_clic.h#L50-L58)。
当前运行使用 rev0 ROM 和 P4 1.0 eFuse，未把镜像换成新硅片构建规避兼容问题。

## 当前可修范围与阻塞

截至本次检查，最新稳定版是
[esp-emu 1.0.0](https://github.com/espressif/esp-emulator/releases/tag/v1.0.0)。
公开树固定为 `f77b06d76ec1c8323c21d3543ec86bf426567f22`，其中有
[esp-part SDK](https://github.com/espressif/esp-emulator/tree/f77b06d76ec1c8323c21d3543ec86bf426567f22/esp-part)
和 [part ABI](https://github.com/espressif/esp-emulator/blob/f77b06d76ec1c8323c21d3543ec86bf426567f22/proto/PART_ABI.md)。
它们允许可维护的 GPIO/I2C/SPI 器件实现，不能再笼统称“新版完全无法扩展”。
但公开树没有 CPU/CSR 核心源码，CLI/part ABI 也没有替换 CSR 或片上 MMIO 控制器的接口。
0.50.0 的 CLI 没有 `--cosim-board`。

- **#227**：当前 0.50.0 Tab5 配置没有 ST7123/GT911 I2C 器件。实际断言与
  [issue 已列的 BSP 两次 probe 失败分支](https://github.com/m5agent/m5stack-esp-emulator/issues/227)
  一致；本轮未另行采集逐笔 I2C 事务 trace。1.0.0 的 I2C part 是可行的工程入口，
  但当前同原版先被旧 P4 CSR 执行兼容阻断，尚不能完成原应用验收。
  下一步应先取得旧 P4 CSR 兼容的可执行后端，再实现触摸寄存器、复位、IRQ、
  接触报告及输入注入，沿原 BSP/触摸驱动验证；静态地址 ACK 不等于触摸模型。
- **#226**：0.50.0 的新原版 M5TabOS 同样命中 DWC core-ID 自检断言。
  1.0.0 发布的 USB 功能是设备模式由虚拟主机枚举，不能转授 guest USB 主机能力。
  原版在新版的 USB 初始化尚未验收；需要真实 P4 guest-host 控制器、根端口与
  端点数据通路，随后运行原 BIN 并完成至少一次 HID/MSC 枚举与传输。
- **独立 M5GFX #417**：失败读取后解析未初始化触摸缓冲区的 host 复现，
  属于更后的读取处理路径，不修复 #227 的 BSP 地址 probe。它可以提供未来
  器件模型的 NACK/部分读取故障注入用例，不能代替本轮原版验证。

本轮没有添加假 GSNPSID、静态触摸 ACK 或 guest 返回值拦截，也没有替换驻留服务。

## 画面与证据边界

所有原版会话的 `frame.png` 都返回 `409 screenshot_requires_matching_elf`。
这是当前服务没有配置与这些应用匹配的 ELF，**没有测量 framebuffer**；不能写成
“采到黑帧”或“该 HTTP 响应证明 guest 没有绘图”。本轮失败由重启、断言和
同指令 A/B 证明，应用画面、触摸输入、USB 主机枚举和网络数据面均未验收。
UART0 没有断言文本不等于没有断言；本轮使用 GDB 读取实际 abort details。

## 复现

1. 使用摘要中固定的两个原版 BIN、运行时、rev0 ROM、32 MiB PSRAM、
   P4 1.0 eFuse seed 及 C6 固件。在独立端口和状态目录启动当前 Device Service。
   比较候选时仅将载入的 Tab5 `DeviceSpec.emulator` 与 `flash_emulator` 指向
   对应运行时，其余 launch/Flash/I2C/C6 配置不变。不要修改共享设备配置。
2. 依次 `POST /api/v1/artifacts`、`POST /api/v1/firmware/import`
   （`device_id=tab5`），然后以 `runtime=qemu` 和返回的 `firmware_id`
   创建独立会话。保存请求幂等键，确认运行的是 P4 与 C6 两个所属进程。
3. 自然观察约 18 秒，读取串口；在该会话的 GDB 端口进行以下独立观察。
   CarPlay 的 abort 断点是 `hbreak *0x4ff0ce9e`，M5TabOS 是
   `hbreak *0x4ff10f00`；`continue` 命中后 `info registers pc ra a0`
   与 `x/s $a0`，最后 `detach`。1.0.0 的旧 abort 观察有界 12 秒未命中，
   该失败观察保留，不视为断言消失的证明。
4. 另建同原版会话进行 CSR 对照：CarPlay 在 `0x4ff014c0`、M5TabOS 在
   `0x4ff0255a` 设置硬件断点，命中后 `x/i $pc`、`si`、`info registers pc`。
   0.50.0 是 PC+4；1.0.0 转异常向量。没有给 CSR 注入返回值。
5. 先请求 `evidence?include=manifest,serial,frames,logs,flash`，验证文件清单
   长度和 SHA，再 `DELETE /api/v1/sessions/{id}?purge=0&retain_flash=0`。
   本轮全部 P4/C6 子进程和专属服务均已退出；历史保留、可变 Flash 已释放。

原始 BIN、ZIP、日志与宿主标识不入库；本页仅链接脱敏派生摘要。
物理硬件、浏览器 WASM、完整应用稳定性均 `NOT RUN`，未提交 Burner 或联系上游。

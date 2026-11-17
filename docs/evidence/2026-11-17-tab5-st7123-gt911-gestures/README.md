# Tab5 原版 ST7123 取帧和 GT911 拖动

日期 2026-11-17。Virtual-device validation。用同一个隔离 Device Service，
按上传镜像规范化后的 SHA-256 选择板型。两个原版均以 esp-emu 1.1.0
macOS arm64 运行，SHA-256
633a35f993300a765634ed78a2dbcfd5ffcd5c3f2f354a2dddabeb6108240828。
两个会话均未提供匹配 ELF。

## 原版 Arduventure 1.0.0

原始 BIN SHA-256
e2f228813b719b81c47a8deaa7576f1b83e61e950c6178c5cf570bfaca7b8616，
规范化并实际执行的 Flash SHA-256
0922e46d70edc11d285fd3d4023a18f061d4d95fd8e7a1729e00702cc3dba063。

| 对照配置 | 同一原版结果 |
| --- | --- |
| 仅原生 DSI | 串口报 Wrong display geometry。DSI 已连接，142 次帧请求返回 409。 |
| 硬件 I²C1 的 ST7123 静态版本寄存器 | 相同串口 SHA 和几何错误。142 次帧请求仍返回 409。 |
| 硬件 I²C1 的 GT911 静态身份寄存器 | 相同串口 SHA 和几何错误。141 次帧请求仍返回 409。 |
| 原生 ST7123 GPIO I²C Part | 串口选择 ST7123、初始化 PPA 和 DSI DMA。原始 720×1280 帧同时显示操作区和 ARDUBOY TEAM A.R.G. PRESENT 启动画面。 |

三个失败对照的串口 SHA-256 均为
1d1fac9d762790812fae6843eaa8935d55c49a7d7c5b9c376f4c83631a479add。
独立的只读 GPIO 观察器从 SDA31/SCL32 解出五次对 PI4IO 0x43 的写地址，
其 9 位周期的 ACK 位保持释放。该对照没有能在 GPIO 总线上驱动 SDA 的
外部设备，硬件 I²C 寄存器设备不能回答这一路。原版包含 M5GFX 软件总线
探测日志串。修复后的 Part 直接观察主机 SDA/SCL 边沿，在 ACK 和读周期
驱动从端 SDA；寄存器组覆盖必要的 0x43、0x44 和 0x55 探测。原版串口明确
输出 ST touch FW version 03 与 detected ST7123 display。 [M5GFX 检测源码](https://github.com/m5stack/M5GFX/blob/28d47949bdc84f30881623476f555398e2194313/src/board_detect/m5/esp32p4.inl)

同 worker 正控的 ST7123 Part SHA-256
6eaa3664fd81ce7e8f56bc0f84ad124ca2afcce21c947e74bbb41f1d9802d106，
有游戏像素的原始 PNG SHA-256
b132be51149e62583817538364084b4f31f31f16b54e9f8c89313dd861bc4348，
串口 SHA-256
988e37642531b0f68e50fa90808c9f27d34ca49304c288402222b8b1c8655b0d，
会话 ZIP SHA-256
239b3807c74edf286e28dd0ef0cd51aa4093d018e9c305ab78c3ef4cb72db2c8。
普通输入端点仍对 ST7123 会话返回 input_requires_matching_elf。

## GT911 数据面与 CarPlay 对照

在正常 POST /input 路径，ESP-IDF 控制器探针
0e7a9596ffe0c2725ad34c69be6cf16a80963580208d0640be18886dd521aeaf
从 GPIO23 低有效 IRQ 和 HP I²C1 读取严格有序的唯一位置：
(120,200)、(220,360)、(320,520)、(420,680)、(520,840)、(620,1000)。
最后一个报告是释放，全部 22 份报告均经 0x814e 确认。探针 ZIP SHA-256
92ffee93b9a3db5931f0ae94a70e88e6055910bad31933be3a9f5960e8ad77c7。
[固件探针](../../../tests/firmware/tab5_gt911/README.md)

同一隔离 worker 保持默认 gt911-ili9881c，选择 CarPlay 原始 BIN
4f3bb118a5570a6ba885a234fce55b66e28ef26091cfe4f3f2e4c33711471ea3
及执行 Flash ff578ccc3f4f93a6f431eff0809b1e46bfb3951101c81bc676774d3f3a36387b。
既有 GT911 Part SHA-256
a0852d08d6cc04a11dcdd57c417b497f857be3e6265f8b690968ae3338cd3ce9。
空白区拖动 (320,500)→(500,900) 的 24 份报告均经来宾确认，图像 SHA
保持不变。随后点 (640,160) 打开 Clear phone pairing?；确认框原始 PNG
SHA-256 bf357f04e40dc9cb76f7e34df7b94a45a89f97da7df26f813fac35577103eed3。
没有确认清除。该会话 ZIP SHA-256
9ab0105953b9eb459cf8414b280d4064e7658c9c7057640408933fd3c887adf2。

## 复现与范围

从 [Device Service 说明](../../device-service-api.md#create-a-reference-uiflow2-device)
取得构建及配置方法。上传两个原版，将两个 admitted SHA 加进
M5_TAB5_DSI_FIRMWARE_SHA256S，默认板保持 gt911-ili9881c，只将 Arduventure
的 admitted SHA 映射为 st7123。以相同 worker 先后开启两个独立会话，从
GET /sessions/{id}/frame.png?orient=panel 取帧，查看 serial 及板型身份，
再通过 /input 做对应正负控。ZIP 均在结束前下载并通过校验，停止后释放
Flash 与所有租约。没有提交 Burner。

Arduventure 通过板型探测与实际启动画面。ST7123 触控、多点与游戏操作
仍未验证。CarPlay 的拖动覆盖控制器和空白区域行为，原应用没有该拖动
的功能响应。USB/iPhone 数据面、浏览器触点映射、实际板卡和物理总线电气
参数仍未验证。

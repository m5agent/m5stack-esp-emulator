# Tab5 原版正常启动与无 ELF 取帧对照

日期：`2026-11-18`。执行类型：**virtual-device validation**。

**98TAB5 仍为 PARTIAL。** 同一原版 BIN 在旧 `esp-emu 0.50.0` 的观察窗口内
只有一次启动、没有软件复位，但无匹配 ELF，不能获取应用画面。启用已验证的
`1.1.0` DSI 与 GT911 板级配置后，DSI 已连接，却没有完整帧，并观察到反复
软件复位。CarPlay 在后一配置下正常出图，验证了同配置的无 ELF 取帧路径。98TAB5 的启动问题仍待归因。

本轮只观察正常启动，没有注入输入、连接调试器、修改 guest 内存或请求外部
网络。原 BIN 来自已有本地审核缓存，没有下载或替换固件。没有改动常驻服务、
没有提交 Burner。旧版与新版同时改变了运行时和板级/取帧配置，需单独验证 CPU 和外设路径才能定位根因。

## 执行身份

Device Service 源码固定于
`c53750bf0cc23e717943c6c3c79e49b11e1a227a`。均使用独立服务和状态目录，
原版经 `/api/v1/artifacts`、`/firmware/import`、`/sessions` 执行，未提供 ELF。
执行映像由服务补齐至 16 MiB，上传原 BIN 的字节保持不变。

| 原版 | 原 BIN SHA-256 | 服务执行 Flash SHA-256 |
| --- | --- | --- |
| 98TAB5（串口 `pc98tab5` / `1.3.0`） | `ea4fb0889e4a2c68d472947137908c52c25a663152d3ff78262ce2605440dc6d` | `35c636324ea1fcebd12f4752e458936c2ac151a9d171a67f1d624d944b96b0ff` |
| CarPlay 1.0.0 | `4f3bb118a5570a6ba885a234fce55b66e28ef26091cfe4f3f2e4c33711471ea3` | `ff578ccc3f4f93a6f431eff0809b1e46bfb3951101c81bc676774d3f3a36387b` |

| 配置 | 固定 SHA-256 |
| --- | --- |
| esp-emu 0.50.0，旧符号取帧路径 | `a4c3468a4abf3f2e55ca0912fa7cdfbe5e101ecb6ab74a9ec35182d70ba6a771` |
| esp-emu 1.1.0，原生 DSI | `633a35f993300a765634ed78a2dbcfd5ffcd5c3f2f354a2dddabeb6108240828` |
| 新配置的 GT911 Part | `a0852d08d6cc04a11dcdd57c417b497f857be3e6265f8b690968ae3338cd3ce9` |

两配置均为 ESP32-P4、32 MiB PSRAM、UART0 console、host-image Flash。
P4 ROM 和 hosted C6 固件 SHA、逐例 ZIP/串口 SHA、采样范围与清理结果见
[有界摘要](summary.json)。P4 和其 hosted C6 进程使用各自同一版本的后端；
本轮没有验证网络或 C6 数据面。

## 实际观察

| 原版与配置 | 观察目标 | 帧结果 | 串口启动 / SW_CPU_RESET | 结论 |
| --- | --- | --- | --- | --- |
| 98TAB5 / 0.50.0 | 60 秒，30 次采样 | 29 次 `screenshot_requires_matching_elf` | 1 / 0 | PARTIAL；应用显示是否就绪未证实 |
| 98TAB5 / 1.1.0 DSI + GT911 | 60 秒，30 次采样 | 29 次 `tab5_dsi_frame_unavailable`，状态均为 `connected` | 32 / 31 | PARTIAL；有真实复位观察，无完整帧 |
| CarPlay / 1.1.0 DSI + GT911 | 30 秒，15 次采样 | 14 次有效 720×1280 帧 | 1 / 0 | PASS，仅限正常启动显示 |

每例第一次采样都发生于会话启动完成前，返回 `session_not_running`，不计为
应用失败。最后采样时刻分别是 58.317、58.228、28.842 秒；摘要保留这些实测
值，不把观察目标当成精确采样跨度。

CarPlay 首个有效帧在 2.003 秒采样取得，PNG SHA-256 为
`b9caf8f325d9b9ec1ee5d7ae3b49f3c709d584b0a5dce54d2ffd2fc62708f767`，
921600 个非黑像素、48 色。人工查看可见 `Connect your iPhone` 与
`Clear pairing` 控件。本轮未点击配对清除、未连接手机，USB Host/CarPlay
功能不在该 PASS 范围内。所有帧保留为私有原始证据，未提交原图或完整串口。

最初一次观察器在 `booting` 时把尚未就绪的 `flash=null` 当成字典读取，导致
观察器退出。该会话和服务已经清理，表中三例均使用修正后的观察器。

## 仍未解决的身份与启动边界

98TAB5 的应用分区是 `app0`，type `0x00`、subtype `0x10`（OTA0），
offset `0x10000`、size `0xc00000`，没有 factory 应用分区。基线 Tab5 符号
身份 helper 要求恰好一个 factory 应用，因此服务记录 `application=null` 和
`Tab5 regression requires exactly one factory application`。缺少匹配 ELF 也限制了符号取帧，串口记录了原版实际启动。

## 单 OTA0 应用身份复验

`d6a22054fbf6527f89845804d90ff5c1ef44d864` 的 Device Service 读取同一
98TAB5 Flash 中唯一应用 `app0`、两扇区空白 OTA 数据及 ESP32-P4 应用的
尾部 SHA-256。API 和同会话 ZIP 均给出 `selection=ota0_erased_otadata`，
启动日志实际加载 `0x10000`。符号状态为 `unavailable`。
ESP-IDF 在擦除态 OTA 数据下的默认选择见[ESP32-P4 OTA 指南](https://docs.espressif.com/projects/esp-idf/en/stable/esp32p4/api-reference/system/ota.html#ota-data-partition)。

同一 1.1.0 DSI 配置下，98TAB5 在 60.293 秒内再次记录 31 次软件复位，29 次
会话运行后的帧请求均无完整帧。CarPlay 的 factory 字段一致，取得 14 个
720×1280 有效帧，首帧哈希与基线一致。两会话均保存证据后释放 Flash 和租约。
[OTA0 与 factory 复验摘要](ota0-identity-summary.json)

多应用 OTA 身份、98TAB5 的重复复位原因、正常应用画面与用户输入仍开放。
M5TabOS 的独立启动问题沿用此前记录。

## 后续原版启动观测

独立 Device Service 以 `80a3b5eda5f50c4a8cced04e31021fc8363593ab` 和同一个
1.1.0 后端运行原版 98TAB5、M5TabOS 和 UserDemo。98TAB5 使用 GT911 板型的
内置静态识别寄存器，未加载不同的触摸 Part。三份原版各自保留 Flash 身份和
真实来宾的取证结果。

98TAB5 的新无调试控制在 64 秒内产生 33 次软件复位和零完整帧。同原版从
`0x4ff00402` 和 `0x4fc02750` 两个执行点均能读到原始 Flash 表字。
一次到达 `0x4ff003fc` 时，DROM/IROM 都已读零，随后 CPU1 跳到零并发生
指令访问异常。两次调试把 CPU0 的缓存维护与 CPU1 读零时间重叠绑定到 ROM
`Cache_Sync_Addr` 或 `Cache_Invalidate_Addr`。同轮 CPU1 真正执行加载时，
其读取已恢复，仍观察到 CPU0 Cache error。故障的缓存实现或调用顺序仍待区分。

只读分段停靠的诊断复测在跳转至 `0x4ff00cca` 后脱离调试器，取得
20 次同哈希的无启动盘帧。普通冷启动仍会复位。证据范围以 [98TAB5 摘要](98tab5-cache-window-summary.json)
为准。M5TabOS 的双核等待和 UserDemo 的暂停确认缺失记录在
[原版启动分流](tab5-startup-paths-summary.json)。实际启动盘、触控及真机未验证。

## 复现入口与清理

1. 准备上述原 BIN、已固定 SHA 的后端与 GT911 Part，以及项目 Tab5 profile
   所需 ROM/C6 资产。原版无匹配 ELF 时不要上传无关 ELF。
2. 在独立端口、状态目录和 token 文件启动
   `python3 platform/tools/serve.py PORT --bind 127.0.0.1 --state-dir STATE --api-token-file TOKEN --max-sessions 1`。
   旧配置不设置 `M5_TAB5_DSI_*`/`M5_TAB5_GT911_PART`；新配置设置
   `M5_TAB5_DSI_EMULATOR`、`M5_TAB5_GT911_PART`、
   `M5_TAB5_DSI_BOARD=gt911-ili9881c`，并将上述执行 Flash SHA 放入
   `M5_TAB5_DSI_FIRMWARE_SHA256S`。
3. 通过上述 API 上传、导入并创建 `device_id=tab5`、`ttl_seconds=180` 的
   会话。每约两秒读取会话与 `frame.png?max_age_ms=0&orient=panel`，分别观察
   98TAB5 60 秒、CarPlay 30 秒；仅收集串口和实际帧，不发送输入。
4. 先读取 `serial?limit=262144`，再请求
   `evidence?include=manifest,serial,frames,logs` 并检查 ZIP 完整性；最后
   `DELETE sessions/ID?purge=0&retain_flash=0`。三例均已验证会话停止、
   Flash 释放、active leases 为零、原 BIN 哈希不变，随后停止各自独立服务。

原始 ZIP、日志和帧保留在忽略目录。本页只提交白名单摘要，不包含 token、
会话标识、机器路径或设备唯一标识。physical hardware、浏览器 WASM、
电气/功耗、外部网络及完整应用功能均为 **NOT RUN**。

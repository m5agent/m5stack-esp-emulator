# 2026-11-13 新增模拟器问题复核

本页保留 #216–#224 的逐问题结果；所有功能证据均为 **virtual-device validation**。原版 BIN 未改写，控制器探针和 SDK 诊断正控分别标注。

## #218 主动关机

服务使用 QMP `SHUTDOWN` 的 guest/reason 与 `query-status=shutdown` 判定主动下电。
`-no-shutdown` 让服务在正常回收前读取最终屏幕，原来的取消、lease 和进程围栏仍负责清场。
退出码 0、串口文案和白屏均不作为关机原因的替代判据。guest panic 和宿主异常继续失败。

两份公开原版 BIN 经独立 Device Service 的 artifact → firmware → session 路径运行，
刻意等待不会出现的就绪 marker，均能在启动阶段主动关机并正常收口。相同运行时上，
批量固件 runner 分别得到 `PARTIAL/guest_poweroff`、`application_ready=false`。
[逐固件身份、QMP事件、末帧和ZIP哈希](poweroff-summary.json)。

PaperColor 最终帧全白；PaperDIY 保留黑白图像。这里只证明帧保存与关机语义，
没有用非黑像素或一张图宣布应用就绪。PaperDIY 的首次短观察窗口在下电前结束，
仍为 `PARTIAL/no_observable_input_response`；默认时间线的后续独立运行观察到主动关机。

复现时使用这两款固件的原版 BIN（哈希见摘要），通过 `/api/v1/artifacts` 上传，
`POST /api/v1/firmware` 指定设备和 `kind=merged`，再创建 `runtime=qemu` 会话并
设置一个不存在的 `ready_marker`。轮询至 `stopped`，读取串口、`frame.png` 和
`evidence`，最后 `DELETE /api/v1/sessions/{id}?purge=0`。期望无启动错误、
`stop_reason=guest_poweroff`，末帧可读、worker lease 已释放。无需改写应用或 NVS。

本轮没有物理硬件、光学或浏览器 WASM 验证。

## 已验证的修复与限定结果

| Issue | 结果与证据 | 仍不覆盖 |
| --- | --- | --- |
| #216 | C6 原生构建配方固定上游版本；补 AES/GDMA/IRQ。Nesso 与 NanoC6 的 NIST CBC、跨描述符加解密通过，原 Bruce 越过原 AES 等待到 LittleFS 错误页。见 [C6 摘要](../../../tests/firmware/esp32c6_aes/evidence-2026-11-13.json) | Launcher 互斥量断言、Meshtastic/RFID 异常仍在；[诊断边界](c6-remaining.json)，整项 PARTIAL |
| #217 | 共享 IOMMU 失效在目标 vCPU 线程清 TLB，保留 atomic 断言。相同探针旧运行时三次宿主失败，修复后两次完成 200,000 次重映射；原 PaperColor 两轮 120 秒宿主稳定。见 [原始对照](../../../tests/firmware/s3_cache_atomic/evidence-summary.json) | PaperColor 后续 guest mutex 断言是独立问题；不转授 StackChan #223 |
| #219 | AtomS3 接通真实 LCD_CAM 命令探测路径；SPI 面板 ID 逐字节推进并在事务完成时锁存 FIFO。原 Snake 与 UserDemo 指定 GC9107 变体后均有有效帧并运行 120 秒。见 [对照](../../../tests/firmware/atoms3_display/evidence-summary.json) | 默认 ST7735S 不被替换；不宣称任意固件、全部游戏逻辑或物理显示等价 |
| #220 | 原 PaperColor factory 的 USB EP0 完成设备/配置描述符、地址、配置与 MSC GET_MAX_LUN；StickS3 CDC/bulk 独立回归。见 [协议摘要](../../../tests/firmware/papercolor_usb_otg/evidence-summary.json) | 工厂固件只暴露 MSC，不把 CDC 强加给它；不含块存储 I/O、后续 app 稳定性或物理 USB |
| #224 | Classic MAC fixture 修复 eFuse 字节序和 ROM CRC；Atom Lite/Matrix 三条真实 IDF API 与服务元数据一致。仅为实际挂载的 eFuse 提供身份，Core2/C6 明示 unprovisioned。见 [探针证据](../../../tests/firmware/esp32_efuse_identity/evidence-2026-11-13.json) | 未改写上传 NVS，不把校准失配日志或有 MAC 当成应用就绪 |

第一轮合并运行时 `d0c0054ae85aafd0eeb271045e81e258899d0f6d2422392d6834cb66c98a784d`
从固定源码和完整配方重新构建，只复用依赖产物，未复用 QEMU 对象文件。
同一运行时复测 USB、主动关机、双核 cache/atomic 和 AtomS3 原版显示路径，
身份、帧、输入与清场见 [整合摘要](integration-summary.json)。
Snake 的固定 200 ms 输入观察在第四次得到相同帧，原 FAIL 保留；
调整为保持输入并最多观察 2 秒后四次均观察到帧变化。该回归只声明可见响应，
不把帧 hash 改变等同四个方向的游戏语义。

## #223 保留失败与 I2C 生命周期诊断

原 StackChan UserDemo/GPT 仍能复现上下文破坏。QEMU 的 guest-store 环形 trace 捕获 CPU0 的
I2C ISR 字节写覆盖 CPU1 saved-frame 地址，其中重叠返回状态的尾部写入为零；
`retw.n` 随后读取坏的返回地址。每 CPU trace 本身不建立完整跨核先后顺序，
返回后写入由下面的最小探针独立证明。`break 1,4` 位于 DoubleExceptionVector，不能归为随机 PC 截断。

同一 ESP-IDF 5.5.4 最小双核探针在第 10/75 次成功读返回后仍被 ISR 修改缓冲区。
仅在诊断 SDK 将 DONE 通知移至 RX FIFO 拷贝后，30,000 次通过且错误为零。
[源码、可运行命令、SDK 诊断 patch 和对照证据](../../../tests/firmware/s3_i2c_lifetime/README.md)。
原 BIN 没有被替换，模拟器延时与 single+icount 候选均未可靠消除故障且未合入。
这证明了本运行路径的缓冲区生命周期竞态，不证明真实硬件复现，timeout 分支也仍需独立检查。

## #224 原版应用归因校正

历史上游明确要求初代 AtomS3。相同 Evil-Parasite BIN 在 AtomS3R 为黑帧，
CPU 的 `0x42092762` 位于正常 WAITI 路径；在 AtomS3 GC9107 上可见 avatar 像素。
[同运行时与同 BIN 的板型对照](evil-board-comparison.json)记录精确哈希和帧数据。
因此原先“PHY 校准回退导致黑屏”的归因不成立为已证结论，不能通过覆盖 NVS 消日志来修复。
仅观察显示，没有触发固件的无线攻击模式；完整应用和 RF 未验证。

## #221 / #222 未完成的原版应用

Classic 原生构建遗漏了已存在的 per-vCPU 时间片实现，服务传入的配置被旧二进制忽略。
`qemu-unit-runtime/0021` 恢复与旧 0090 等价的实现，不改现有服务默认策略；
`0184` 让 DPORT 六个中断源状态寄存器读回真实 IRQ level，使 IDF 能区分 TG1 WDT
与 cache error，设备仍自行清中断。Atom Lite 在早期组合重复并行冷启出现过 IWDT；最终 main 服务与 `dcb5c9f3…`
两轮独立运行 121.90/121.85 秒、按键→RMT 通过，旧负控仍保留。Matrix 原版仍有
Wi-Fi watchdog 且无灯阵，因此 #221 不关闭。Matrix 的离线 MAC 候选没有完成
scan/灯阵验收且未合入。见 [Classic 对照](../../../tests/firmware/classic_factory/bootstrap-summary.json)。

Core2 原版 UIFlow 1.15.5 和 HamRadio 0.1.5 仍未出现应用就绪帧；UIFlow 在 qemu-wifi 已显示启动 logo，HamRadio 仍黑。plain/qemu-wifi、
双核时间片候选和 AXP192 板型控制分别保留于 [逐轮摘要](core2-remaining.json)。
UIFlow CPU0 有 Flash/cache handoff 指令簇活动，HamRadio 继续到配置文件检查；
单个忙等/WAITI PC 不证明永久死锁，也没有匹配 ELF 支持精确源码归因。
最终 `dcb5c9f3…` 的 [同组合对照](core2-final.json)中，UIFlow 120 秒停在启动 logo、HamRadio 全程黑帧，AWS 30 秒有完整首页。0179 的 AWS 成功不能覆盖前两者，#222 保持开放。

## 整合检查

首次完整原生矩阵为 [66 PASS / 2 FAIL](native-matrix-first.json)，278 项检查。
原 StackChan/Core2 audio 用例没有 guest 就绪条件，固定时间截帧早于初始化完成。
加入真实串口就绪标记、沿用既有 30 秒有界等待后，相同组成 BIN 在旧基线、第一轮
整合与最终运行时均通过；原 PCM/颜色/PMIC 判据保持。最终 StackChan audio 与
Core2 全部六例为 [7 PASS](audio-readiness.json)，首轮失败不被覆盖。
最终 `dcb5c9f3…` 另通过 [原版显示、USB、关机和 atomic 复测](final-runtime-summary.json)。
[主线 eFuse 集成复测](efuse-integration.json)另验证四板身份状态及服务重启后的历史一致。

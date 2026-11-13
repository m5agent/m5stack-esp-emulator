# 原生运行时恢复与独立复验

日期：`2026-11-13`。验证类型：`virtual-device validation`。

清理移除了此前的临时整合目录和冻结运行时。已从保留的提交恢复源码，
重新构建 Xtensa 和 C6；旧二进制没有恢复，不能把旧执行结果归给新 SHA。
部分旧原应用 ZIP 已丢失，保留下来的历史摘要与新执行证据分别记录。

## 恢复后的执行结果

| 运行时 | 实际结果 | 证据 |
| --- | --- | --- |
| Xtensa `e529a11c…` | Matrix/Matrix v1.1 灯阵、按键与真实网络传输通过；厂测 HTTP 返回 404。Core2 UIFlow 1.15.5 配置页及 HamRadio 的 SD 文件选择、仪表页通过。Atom Lite 持续 watchdog，阻止交付 | [原版执行](xtensa-originals-before-irq-fix.json) |
| Xtensa `e529a11c…` | 五款 StickS3 原版的 display/raw 同样本逐像素比较、方向和可读性通过；只覆盖显示方向 | [方向复验](orientation-before-irq-fix.json) |
| C6 `e4c9bb8d…` | Nesso 的面板方向、长 DMA、硬件片选及未选中/无线电隔离控制通过 | [控制器正反对照](c6-controller-controls.json) |
| C6 `e4c9bb8d…` | 原 Meshtastic 显示、按键、休眠唤醒及原 Bruce 菜单、触摸、复位后 LittleFS 保留通过。两版 Launcher、Zigbee、RFID 仍失败；Honeypot 仅启动与 GPIO 输入有证据 | [七份原版执行](c6-originals.json) |
| C6 `e4c9bb8d…` | 原 Launcher 3.0.0 中，显示任务成功获取 SPI mutex 后，输入任务通过共享触摸配置释放同一 mutex，触发 owner 断言 | [原 BIN 指令与事务追踪](launcher-original-mutex-trace.json) |

Atom Lite 的后续排查定位到高优先级中断返回后的模拟器调度状态未清理。
IRQ 修复及最终组合运行时的验收单独追加，不覆盖这里的失败结果。
Launcher 的原 BIN 动态证据没有借用重建 ELF 的地址；源码修复构建与
原发布 BIN 是不同产物，不能把后续重建版通过写成原版通过。

## 后续独立控制

- [IRQ/CPU 变频控制](../../../tests/firmware/classic_factory/README.md)：正式 0194 跟踪实际中断槽；0197 在变频时保持 CCOUNT 连续并重排未来 CCOMPARE。增量候选 `a2c5e415…` 的原 Matrix/Lite 各 130 秒、Core2 UIFlow1 180 秒通过，旧 `dfb73748…` 与 MEMW 单行负控的 Matrix watchdog 仍保留。最终 fresh 组合验收不由这三例替代。
- [Nesso 触摸源码控制](../../../tests/firmware/nesso_touch_bus_shared/README.md)：同 C6 `e4c9bb8d…` 上，完整固定 Launcher 和两份固定 M5GFX 探针均在未修版触发 owner assert；仅修改独立触摸 `bus_shared=false` 后，各运行超过 155 秒。完整应用通过菜单、触摸、返回及设置页；原发布 BIN 保持 FAIL。

## 身份与可复核范围

- [运行时身份](runtime-identity.json)记录新旧 SHA、构建配方及证据可用性。
- 旧回执只有九份选定源码的哈希；按原配方重建的 146 份源码一致，仍不能
  证明已丢失的增量构建不存在陈旧对象。因此以新原应用运行结果决定交付。
- [文件清单](manifest.json)固定本页六份摘要的字节数和 SHA-256。
- 新会话均通过 Device Service 执行，先取得 ZIP，再停止并保留历史；
  实际固件、输入、运行时、串口/帧/数据面及清场状态在各摘要中独立绑定。
- 固定时间输入曾错过 HamRadio 文件选择窗口，后续按实际界面就绪输入；
  最初失败仍保留。C6 首次错误环境变量运行不计入新运行时验收。

物理硬件、RF 和 browser-WASM 不继承这些原生结果。RFID 未连接外设
不足以解释其重启；PCR/MWDT 时钟接线和重复 TWDT 初始化继续独立验证。没有修改原 BIN，也没有提交 Burner。

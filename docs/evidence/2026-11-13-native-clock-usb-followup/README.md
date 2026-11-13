# 经典 ESP32 时钟与 C6 USB 原生后续验证

本记录绑定集成源码 `4a5d28e6d4764ec78c0621aed0e0527080597486`、Xtensa 原生产物 `5ce7d9f5…` 和 C6 原生产物 `80d92a6c…`。运行时完整哈希、上游提交、补丁数、构建记录及 ROM 哈希见[机器摘要](summary.json)。

## StickC Plus2 原版路径

同一 JIGGLER 1.0 原版 BIN 经 C 下压和释放进入主界面。B 100 ms 显示鼠标尚未就绪，A 100 ms 显示暂停，B 2000 ms 进入设置。两轮有界自适应在新鲜主界面基准后观测到的虚拟时间下界分别为 **300.377564** 和 **300.308091** 秒，在新鲜设置页基准后分别为 **280.820599** 和 **277.567543** 秒。默认固定步长 5 轮在新鲜设置页基准后继续运行至少 **15.866** 虚拟秒。三轮均保留原始应用分区和正常看门狗配置，证据 ZIP 先于会话停止保存。 [输入、时钟与画面证据](../../../tests/firmware/stickc_plus2_bt_lp_clock/bounded-adaptive-evidence-summary.json)

自适应上限采用已验证的固定步长 5，允许在 0–5 调整，达到上限后虚拟时间可落后于主机。旧无界自适应的 IDLE0 超时与后续重启 panic 保留，首次超时的完整事件链仍未确定。RWBT 复位域修复有独立 CPU-less 控制器 qtest。原版三轮未发生看门狗复位。 [模型、时钟和迁移复现](../../../tests/firmware/stickc_plus2_bt_lp_clock/README.md)

## 定向与宿主回归

同一 Xtensa 产物在 `a8c9b222c6af0081fd48bc7facafa7cd12b6e5c3` 上通过四个独立 Device Service 会话。Core2 固定与有界自适应各完成 320×240 显示和触摸后重绘。Plus2 两模式各识别 board 5、显示 135×240 画面并处理 100 ms 虚拟 A 键。每轮都有 guest 串口、帧、输入和停止前 ZIP。 [四组合回归证据](../../../tests/firmware/stickc_plus2_bt_lp_clock/classic-input-regression-summary.json)

集成源码 `4a5d28e6…` 的完整 Python 平台套件运行 2,178 项，跳过 8 项，耗时 209.054 秒，退出码为 0。平台契约和 guest 证据分别记录。

## Nesso N1 扩展器控制

C6 旧产物的同一合成等待程序在 17 项板级观察中出现 9 项预期差异。最终产物通过 17 项。测试经实际 HP I2C0 FIFO、QMP 按键与触摸、GPIO3 输入寄存器验证双扩展器与共享 pad，未执行 CPU GPIO 中断矩阵、BMI270 IRQ 或原应用。 [板级与宿主 C 证据](../../../tests/firmware/esp32c6_nesso_pi4ioe_irq/shared-pad-evidence-summary.json)

## 最终 C6 原版与串口复验

同一 `80d92a6c…` 运行时与 `4a5d28e6…` 服务源码上，原 Mesh 观察 150.382 秒，A 1.2 秒打开区域菜单、短 A 改变选项，自然休眠后 B 唤醒恢复同一选项；原 Bruce 观察 150.393 秒，触摸切换菜单，一次请求重启后文件系统重挂载正常。原 Honeypot 独立观察 180.011 秒，USB 输出完整 153 字节应用内容；另一个 90.012 秒会话完成 API 与三个真实页面的 console/USB 切换。九张页面截图逐张复核，18 次 API 有界读取与同会话 ZIP 字节一致。[最终 C6 原版与控制证据](../../../tests/firmware/esp32c6_shared_irq_pad/README.md)

实际 USB 控制器的 Arduino 传输、原版 UIFlow REPL、TSF、两会话身份隔离与 Nesso 外设/LoRa fixture 均通过各自限定路径。802.15.4 读回仍是预期失败，GPIO3 pad 通过不代表 CPU GPIO 中断矩阵、BMI IRQ 或 FT6336 精确 IRQ 时序已经实现。Honeypot 的 AP 关联、HTTP 与 RF 未验。原 Mesh BIN 直接读取 `0x0F` 的 A/B 位，早先按公开 fork 推断的 `0x13` 单键路径不适用于该原版。

## 当前原版包核验

重新下载当前公开 UserDemo、GPT 和 RFID 包，三者 SHA 均与已测失败原版相同；发布版本名称变化不能作为缺陷已修复的证据。[当前包身份摘要](current-artifact-summary.json)

## 最终联合回归

精确源码 `4a5d28e6…`、Xtensa `5ce7d9f5…`、C6 `80d92a6c…` 在环境负载下完成 **69/69**，含 64 个 Xtensa 用例和 5 个 C6 用例。每项只执行一次，零重试，耗时 964.700 秒。首末采样的 1 分钟负载分别为 3.295 和 2.433，未启用负载进程。逐例保留固件和产物哈希，回归进程及临时缓存链接已清理。 [逐项矩阵证据](ambient-matrix-summary.json)

## 交付状态

main 已快进到 `4a5d28e6…`，精确提交 CI 通过。两个常驻角色均加载本记录的运行时并通过健康检查，各自原有的 29 和 42 条历史全部保留，复验后总数分别为 36 和 46。 [main CI](https://github.com/m5agent/m5stack-esp-emulator/actions/runs/43453074487)。发布后的八条原版云端配对和一条真实网页本地编程均在独立首轮会话通过。九张帧逐张复核，同会话 ZIP 的运行身份和停止后的资源释放均已核对。首次 dry-run 验收脚本缺 Pillow，在创建审核任务或 guest 前退出。随后加载已安装的 Python 依赖继续执行，脚本源码保持原样。

原版 Cardputer ADV MP3 Player v1.0.0 读卡后列出 `TEST.MP3`，按键进入播放，进度从 0:00 到 0:01。实际 PCM 为 1,364,992 字节，有 160 个匹配窗口。原版 Core2 2048 Game 1.0 的右、左、上、下各执行两次，八次均得到合法移动或合并及新块生成。审核服务均返回 `SIM_VERIFIED`，原始验收脚本保留 `status=REVIEW`、`visual_review=PENDING`，随后独立查看 MP3 库/播放/进度帧和 2048 的九张棋盘帧，均通过。两个原版应用分区字节保留。11 个发布后会话均在停止前导出 ZIP，随后释放 Flash 和租约并确认 guest 进程退出。 [发布后逐项证据](post-delivery-summary.json)

主线、常驻与发布后复验为 `PASS`。两次只读审计器自失败分别来自控制日志定位错误和把整数字段当成列表，均在审计报告中保留。实际回滚、状态迁移和切换前后认证材料原始字节对比为 `NOT RUN`，后者缺少切换前的内容哈希基线。整体保持 `PARTIAL`，真机时序、BLE HID 空中传输、浏览器 WASM 与 Burner 提交未执行。

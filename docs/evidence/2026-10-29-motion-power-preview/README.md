# 舵机、电源与复位浏览器预览

用户要求先更新自己的 GitHub Pages 查看效果。本次预览限定 StackChan 新链路，
保留现有 15 款浏览器入口；没有把一次 StackChan 验证扩展为所有板型的新版回归结论。

新原生和 WASM 后端从固定补丁完整构建。Arduino 固定 BSP 的八组动作通过
UART1 SCS 协议更新真实 present-position；扭矩关闭和断供电时位置保持，顶部
Si12T 原 SDK 回调也已观察。原 UIFlow2 默认示例改为四组动作，网页按同 guest
只读 QOM 快照映射到 yaw/pitch，禁止输入回声和网页伪造位移。

复位通过固定 QMP `system_reset` 作用于同一实例。PMIC 按各芯片寄存器和虚拟
时钟处理短按、长按、关断与重启，不能把每个设备的长按都解释为关机。
CoreS3、StickC 与 StopWatch 当前控制器级电源检查另有独立 Service 证据。
Plus2 HOLD/USB sleep、PM1 ROM 下载、物理性能及本轮完整矩阵保持未完成。

准确 runtime/firmware/ROM、输入、串口、帧、QOM、构建与报告 SHA 见
[有界摘要](summary.json)。原始材料留在本地忽略存储；没有提交固件、ROM、
凭据或原始 ZIP。默认示例浏览器已通过；最终同 manifest 的窄烟测 9/9 通过：65 份 QOM 与模型角度一致，左右/抬头变化 288/179 ticks；同 session/iframe 复位后新 ready，外壳 PWR 长按 6 秒触发 SHUTDOWN 和自然 exit 0，5 pthread 与 1 engine 在 iframe 移除前全部关闭。

已部署到 [fork GitHub Pages](https://yuyun2000.github.io/m5stack-esp-emulator/?device=stackchan&mode=browser&v=35ce38c8)，[发布任务](https://github.com/yuyun2000/m5stack-esp-emulator/actions/runs/40862804528)成功；公网首页、manifest 与 runtime 清单均 HTTP 200，manifest SHA 精确一致。

新版完整共享控制器回归与上游新主线整合应在正式 PR 完成前执行；本次先部署预览。

# PaperS3 原厂触摸的浏览器 GT911 读回

日期 `2026-11-18`。结果 `PARTIAL`，验证范围为 Chromium 上的浏览器
QEMU WASM 虚拟设备。源代码为 `a2148953f1c22a2b2b066780f9c501b3daddcdf0`。
[运行摘要](summary.json)绑定运行时、私有观察改动及以下两组派生记录。

| 轮次 | 原厂图标切换 | GT911 总线 | 帧对照 |
| --- | --- | --- | --- |
| 原时序序列，两个成功均为 300 ms | 2/9 | 6 次漏响应可归为松手后清除、空报告读回、再次清除，1 次证据不足 | 保留周期性墨水屏刷新过渡值，只将预期图标变化计为通过 |
| 独立启动后等待稳定帧，两个成功均为 500 ms | 2/6 | 其余四次均符合松手后清除序列 | 6/6 的共享 RGB565 与 QMP 截屏图标区域逐像素一致 |

[原时序序列](bus-summary.json) · [稳定帧复测](stable-bus-summary.json)

## 固件与运行时

- PaperS3 Factory V0.5 原始合并 BIN
  `d6733a0ca378f95335fa5fba4d4d992fb1dd97c17557b20e9aebfca08ba6d624`。
  [官方 BIN](https://m5burner-cdn.m5stack.com/firmware/16287f6984f8ec7fe8058a6c3497b3b4.bin) · [原厂版本](https://github.com/m5stack/M5PaperS3-UserDemo/releases/tag/V0.5)
- 浏览器运行时 `papers3-wasm-wallclock-et047tc1`，WASM SHA-256
  `96c7f8baf1d5f2fd760c560a0827ef7305ad06a1cefb28c905d05d796dc540d8`，
  运行时 manifest SHA-256
  `17cdc825f87c7549e946e477cb4fc4561245cca0793115075d2a8d93d719636c`。
  对应源码包中的 `qemu/hw/m5stopwatch/m5paper_et047.c` SHA-256 为
  `88d4b30712372c88cabf375cf16e569a3d533f2731014dd6e918a49a3cb7cdf8`。
- ESP32-S3 ROM SHA-256
  `b5c7090cc22efce51c1323cef31ca96fcd673a5b1d1b1017e219d393f2659913`，
  由本机字节校验后的浏览器路由提供。 [ROM 源](https://raw.githubusercontent.com/espressif/qemu/40edccac415693c5130f91c01d84176ae6008566/pc-bios/esp32s3_rev0_rom.bin)

## 复现步骤

1. 按[浏览器站点导出说明](../../pages-deployment.md#本机-device-service-的浏览器运行)
   准备上述冻结静态站点的独立副本。以独立本机端口提供静态文件，请求响应使用
   `Cross-Origin-Opener-Policy: same-origin`、`Cross-Origin-Embedder-Policy: require-corp`
   和 `Cross-Origin-Resource-Policy: same-origin`。本轮未向 Device Service 发请求。
   固件与 ROM 只向诊断浏览器提供，导出资产保留原字节。
2. 在副本的 `platform/web/public-qemu-engine.js` 的 `request(op, value)` 内
   加入以下限定观察命令。该调用只使用冻结 WASM 内已有的三个 trace event。
   固件、ROM、C 代码和 QEMU 启动参数维持原值。

   ```js
   if (op === 'paper-gt911-trace') {
     if (boardProfile?.deviceId !== 'papers3' || typeof value?.enable !== 'boolean') {
       throw new Error('This observation requires PaperS3 and a trace state');
     }
     const names = ['i2c_event', 'i2c_send', 'i2c_recv'];
     const states = [];
     for (const name of names) {
       await qmp('trace-event-set-state', {name, enable:value.enable});
       states.push(...await qmp('trace-event-get-state', {name}));
     }
     return states;
   }
   ```

3. 通过 `PublicQemuRuntime.start({device:'papers3', firmware})` 启动原 BIN。
   等待串口 `board_M5PaperS3` 和 540×960 画面。对
   `x=[78,155), y=[296,385)` 的图标区域，初始黑像素数为 1,910。
   调用 `runtime.ask('paper-gt911-trace', {enable:true})` 后核对三项
   `enabled`。在页面的 runtime `receive(data, generation)` 中记录
   `type === 'diagnostic'` 且匹配 `i2c_(send|recv|event).*0x5d` 的行，
   并保留原处理、浏览器接收时间及输入前后事件序号。
4. 用 `runtime.input({type:'touch',x:113,y:347,down:true})` 注入按下，
   等待浏览器壁钟保持时间，再用同坐标和 `down:false` 注入松开。
   原序列为 150、300、500、300、150、500、300、150、500 ms，每次
   观察最长 4.2 秒，并在下次输入前等待 300 ms。稳定帧复测用独立冷启动，
   序列为 150、300、500、300、150、500 ms。前后以间隔 150 ms 的三次
   同一图标区域像素样本确定稳定，预期黑像素数为 1,910 或 1,755。
5. 按 I²C 写地址和重复启动分别解析 `0x814E` 的状态字节和
   `0x8150–0x8153` 的小端坐标。稳定帧轮次在每次输入判读后暂停客体，
   依次请求 `runtime.ask('frame')` 和
   `runtime.ask('frame',{diagnosticTransport:'qmp-screendump'})`，
   对两个真实输出逐像素比较同一区域，再继续客体。关闭三项 trace 并
   检查 `disabled`，最后执行 `runtime.stop()`。

## 结果与边界

每个匹配原厂图标切换的操作都读取了 `0x814E=0x81`、坐标
`(113,347)`，并在松开后读取 `0x80`。这四次操作均正好改变 607 个
区域像素。另有十次直到浏览器发出松开请求才观察到总线访问，其序列为
向 `0x814E` 写零、读到空报告 `0x80`、再次写零。第 9 次原时序操作
在观察窗内缺少总线事件，单独保留。浏览器时标记录的是宿主输入和诊断
到达次序。该轮未测量虚拟接触长度、驱动调用间隔或 IRQ 电平，后续复测见下节。

原厂 V0.5 在应用循环调用 `M5.update()`，并约每 15 秒触发一次 EPD
全刷。原厂绑定的 M5GFX GT911 驱动在距前次处理就绪低电平至少 128 ms 时会先
清除旧报告，再尝试读取。这条路径与上述十次漏响应的总线次序一致。
延后读取的具体原因仍待定位。真机、光学刷新和实际蜂鸣器音频均未执行。
两轮都正常退出，剩余 Worker 和 iframe 均为零。
[原厂轮询与全刷](https://github.com/m5stack/M5PaperS3-UserDemo/blob/5e275ad4b70abb85f7193fda137844730e64c4db/main/main.cpp#L58) · [锁定 GT911 驱动](https://github.com/m5stack/M5GFX/blob/c6f92dc03226cdc04d67c705a2020f62ad21ad01/src/lgfx/v1/touch/Touch_GT911.cpp#L174)

## 接触时长与 IRQ 复测

复测沿用原厂 V0.5、上列冻结 WASM 和时钟除数 1，以两个独立的 Chromium
会话交替从稳定图标与可见全刷过渡帧注入 (113,347) 的 300 ms 接触。
[逐次时长、GPIO 与 EPD 控制器摘要](clock-irq-epd-summary.json)

1. 保留上文限定的 GT911 总线追踪。在浏览器 engine 对正常 QMP
   `input-send-event` 的入队前与确认后分别记录同一 `performance.now()`。
   QMP 在设备的输入同步后才确认。运行期间没有 icount、停止或复位，
   冻结运行时的虚拟时钟由未分频单调壁钟驱动。因此从按下确认到松开
   入队是接触的下界，从按下入队到松开确认是上界。
   [虚拟时钟源码层](../../../patches/qemu-wasm-probe/0010-wasm-explicit-vm-clock-rate.patch)
2. 按下前、保持中段和松开后读取 `/machine/et047tc1` 的
   `latched-lines`、`scan-frames` 与 `query-status`。
   第二轮增加固定的只读观测，经私有 QMP 入口执行
   `human-monitor-command` 的 `xp /1wx 0x60004040`，取
   S3 `GPIO_IN1` 返回字的第 16 位，即 GPIO48。中段读回严格位于按下确认
   和松开入队之间，且无其它输入。
3. 同步解码 GT911 总线记录并等待图标稳定。第一轮对两种画面状态各
   执行四次，第二轮各两次。停止前关闭 trace，确认两个会话均无存留 Worker
   或 iframe。

12 次接触的下界均至少为 300.355 ms，全部上界在 342.650 ms 以内。
四次 GPIO48 读回均为按前高、按住时低、松手后首次读取仍低。中段
读回在按下确认后 150.780–180.180 ms 的观测范围内。12 次按住时均无
GT911 总线访问，松开后均出现旧报告清除、读取空 `0x80` 和再次清除。
本轮未出现图标切换，先前独立会话通过的 300 ms 和 500 ms 仍保留。

第一轮从按下前到松开后的样本显示，稳定图标组锁存 634–700 条 EPD
扫描行，可见全刷过渡组锁存 600–659 条。两组都存在显示传输，稳定图标
无法作为低 EPD 负载对照。该复测确认在完整接触期间已有来宾可见的就绪
电平，且 guest 未消费报告。固件服务间隙是否由 EPD 或运行时调度放大
仍待定位，真机未执行。未调整触控模型或保持时间。

## 无扫描窗口与帧轮询对照

文档基线 `36b091f9766209d2fbc1c28d717ea065cd035d96`。沿用上列原厂 V0.5
BIN、冻结浏览器 WASM 和输入时间上下界。首次启动在原厂应用就绪前出现
浏览器运行错误 `memory access out of bounds`。该次未发送触摸，单独保留
启动失败。相同镜像和运行时复启后完成输入测试。 [逐次有界证据](render-service-summary.json)

1. 输入仍为 (113,347)。第一轮按 200 ms 间隔连续采样 `latched-lines`
   和 `scan-frames` 约 32 秒，再以交错顺序比较正常取帧和临时停用
   取帧时的 300、500 ms 接触。停用组在按下前调用
   `runtime.stopPolling()`，松开后恢复现有轮询。两个组的来宾和
   ET047 控制器均持续运行。在按前、保持中段、松开后读面板计数和
   GPIO48，保留稳定图标变化与 GT911 总线序列。
2. 第二轮只用 300 ms 接触，按 130 ms 间隔测 `latched-lines`。
   选择相邻样本相等或计数增加超过 60 且图标已稳定的时点。
   连续扫描与无扫描均以按下前和松开后的实际计数判定。记录本轮
   `PublicQemuRuntime.ask('frame')` 在按下前到松开请求前的调用次数，
   以此区分停用组和正常组。按住期间不查询 QOM 或 HMP。
3. 除 GT911 `0x5D` 外，第二轮同一总线追踪还记录了 RTC `0x51` 和
   BMI270 `0x68`。以 RTC 完整读取寄存器 `0x02–0x08` 及 IMU
   寄存器读回观察来宾进度。以同一观察器的事件时间对齐按下确认至
   松开入队区间。

第一轮 145 次被动采样找到至少 1,085.395 ms 的无锁存窗口。完成的 12 次
操作中，一次 300 ms 漏响应从按下前到松开后保持零新增锁存行和零新增完整扫描。
虚拟接触在 302.590–333.605 ms 之间，GPIO48 为高、低、低，固件只在松手后
清除旧报告并读到空 `0x80`。另一次 500 ms 操作在 +1,150 行和两个完整扫描
期间正确切换图标，浏览器当时停用了取帧。

定向复测的三次无扫描和三次持续扫描（+711–784 行）均漏响应。正常组每次
发出 9 个取帧请求，停用组均为 0。在两组的无扫描窗口内都复现了松开后
清除、读取空 `0x80`、再次清除。三个仍在扫描的漏响应中，原版在按住期间
完成了 RTC 日期时间和 BMI270 读取，其中一次浏览器发出的取帧请求为零。

这些样本验证了无面板输出、无浏览器取帧时仍可漏响应，也验证了部分来宾
应用操作可与漏响应并行。总线读取不能证明按下后已经执行新一轮
`M5.update()`。无新增锁存行也不衡量 guest 尚未入队的绘图准备工作。
固件服务间隙仍需定位，本轮未调整触控模型或保持时间，两次完成的会话均确认
Worker 和 iframe 清零。真机未执行。
[原厂 RTC](https://github.com/m5stack/M5PaperS3-UserDemo/blob/5e275ad4b70abb85f7193fda137844730e64c4db/main/apps/app_rtc.cpp#L27) · [原厂 IMU](https://github.com/m5stack/M5PaperS3-UserDemo/blob/5e275ad4b70abb85f7193fda137844730e64c4db/main/apps/app_imu.cpp#L24) · [EPD 前台入队](https://github.com/m5stack/M5GFX/blob/c6f92dc03226cdc04d67c705a2020f62ad21ad01/src/lgfx/v1/platforms/esp32/Panel_EPD.cpp#L570)

## 原生驱动读取时序

本节只覆盖原生 QEMU。沿用同一 PaperS3 Factory V0.5 BIN 和 (113,347)
触控坐标。原生冻结版 `68d98b8491b09eeb91fc3c99ee2dd7d2752ac1b6b548bf0c93981f4c225fb05d`
来自 `63472ab884dc2968904999c75eb6aca91c3f2517)。独立观测版 SHA-256 为
`1309290143c16e7a8f1131ca07acde728e809a48295abc255616ed3575a1706b`。
[逐次时序与无观测对照](native-poll-summary.json)

用独立 Device Service 启动原厂画面后，依次输入 150、300、500、500、300、
150、300、500、150、500、300、500 ms。对照组使用冻结版。诊断组在按下及
松开后 1.5 秒内记录 `GPIO_IN1` 的来宾读取、仅用于观测的 TCG 指令位置、GT911
就绪和状态寄存器读写时间。用只读 `cpu_unwind_state_data` 从实际 MMIO 访问还原
Xtensa PC。源时标来自原生 QEMU 虚拟时钟。未写入来宾寄存器、插入断点或改变
控制器、时钟和固件。

在同一 BIN 的原始 IROM 段反汇编核对 `0x42032e87`。该处读取 GPIO
高位寄存器、检查 IRQ 掩码、更新驱动的上次服务时间，并以 127 为比较界限。
后续代码读取已校验 DROM 地址 `0x3c128968` 的 `81 4e 00` 清除命令，
重试至多 24 次，与原厂 `getTouchRaw()` 一致。另一个通用 GPIO 读取位置
`0x42035073` 独立计数，不视为 GT911 已接受报告。
[锁定的原厂驱动](https://github.com/m5stack/M5GFX/blob/c6f92dc03226cdc04d67c705a2020f62ad21ad01/src/lgfx/v1/touch/Touch_GT911.cpp#L169)

以一次 150 ms 原生漏响应为例，报告在按下后 7.526 ms 就绪。另有两个通用
GPIO 读取，但经指令确认的驱动位置在按下后 157.832 ms 才首次检查就绪。
旧报告于 158.189 ms 被清除，160.512 ms 松手，165.041 ms 的下一报告已为空。
固件在 181.343 ms 读到 `0x80`，按住期间未读到 `0x81`。这条证据定位到
原版驱动采样过晚，未定位延迟的应用或模拟器原因。另一次 500 ms 的图标
结果未匹配，但已读取按下和松开报告，单独保留。

12 次诊断输入中，10 次图标改变 607 像素。未加观测的冻结版复测接受 12 次
输入，其中 11 次取得稳定图标，4 次正确切换、7 次未改变。最后一次未在
观察窗内得到稳定图标。冻结版另有一次输入前的 EPD 过渡帧触发观察失败，
该次没有发送触摸。两种原生观察的取帧判据和运行时开销有差异，不能据此
比较漏响应率。所有会话均先取证再停止，租约清零。此前浏览器观测和真机
边界维持原结论，触控仍为 PARTIAL。

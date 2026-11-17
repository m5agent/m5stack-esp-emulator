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
全刷。原厂绑定的 M5GFX GT911 驱动在距前次服务至少 128 ms 时会先
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

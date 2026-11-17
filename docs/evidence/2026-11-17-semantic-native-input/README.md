# 原生语义输入同 guest 验证

复核日期：`2026-11-17`。以下是 virtual-device validation。常驻部署、
物理硬件和浏览器-WASM guest 为 NOT RUN。

通过独立 Device Service 的 `POST /api/v1/sessions/{id}/input` 注入。
卡片键盘、按键和触摸的通过条件是原 UIFlow2 驱动/API 的同会话读回。
这些板载探针以官方固件作底包，只更改 VFS，报告所执行组合镜像的 SHA。

| 目标 | 组合镜像 SHA-256 | 原生结果 |
| --- | --- | --- |
| StickS3 | `c3b808f1baedf12af0175729e5fadc95f49c5414a485a65a4e5f2b8549ba1200` | 实际 `wasDoubleClicked`、A+B 共同按下、B 长按 4999 ms。前一组合的 B 释放为 543 ms |
| Cardputer K132 | `05aaf207b477794995693c999feeb2ab8df5fe0598ab4ec1a7051df6fd65513c` | GPIO 矩阵的 Keyboard 驱动同时读到 Fn 与分号，随后确认释放 |
| Cardputer-ADV | `c1e0c0dadfdcc401bc3d4050b238b8c8ac0735e558972ea4ed66a204a9560899` | TCA8418 的原驱动读到 56 个物理键及其释放，另验证 Fn+反引号输出 27。探针没有绘制屏幕 |
| Core2 | `9065f7220e817e9d48e1e693074a3e4a0a63e79e19b64d61c6ff84acae942765` | 原 Touch 驱动在原始坐标 (67, 110) 读到两次接触及释放 |
| Dial | `d96ed86ddac999e5f44add088f3f7bf9db48e977f043daf5f859204fa4bcf3d0` | 9 次 detent 目标全部交付，读回 120 个 GPIO 边沿。原 RotaryIRQ 计数 3/9 精确，应用层 PARTIAL |

前四项运行 Xtensa
`8f5a839537857d05b2c1e5a7ba0bb401e123924b8202c4a7a6adfd2c0b5f4e41`。
Dial 和 ADV 旧版负对照运行 Xtensa
`06db397cbe804e9eb13390d797cd67ca33ce5f29048fe7a56342cb66f4d2f9e0`。
ADV 负对照使用同一组合镜像。语义 Q 返回 409，旧 raw Q 请求未产生
guest 键事件。K132 初次探针的 Python 成员测试抛出
`NotImplementedError`，修正为原驱动常用的序列索引后重新采样。
各通过样本取证后停止，保留会话历史。

审核控制面另用 StopWatch 原版 Grok Bot MultiFace
`0b207ba2d2ba11907bb4a3bc58fb6cd2ecc0a8f0db8e847ac50969fded0d720a`
回放保存快照。双击 A、A+B 各发一次请求，两步取得有效 PNG。未声明足够
具体的固件行为断言，审核保留 `E_INTERACTION_CLAIM_PARTIAL`。Burner
提交数为零。

同路径复现可使用 `tests/uiflow2/api_sweep/run_hardware_guest.py`，
在其 `--drive-json` 中将固件准备标记绑定到 `input` 请求。
[请求字段与完成语义](../../device-service-api.md#inject-input)。

## Dial 显式物理速度复验

候选原生 Xtensa
`bef8e5f1f181c341076b35ea1cb5946ba8437349ed879196469d4448e0e33e98`
通过同一个 HTTP 输入端点分别提交 +3@35 ms 与 −5@50 ms，各三次。
原 UIFlow2 RotaryIRQ 六次计数精确。随后省略间隔的 +2 请求均恢复 5 ms，
三次都交付 8 个 GPIO 边沿，驱动三次均读成 +1。ESP-IDF GPIO ISR 对照
捕获九个动作的全部 120 个边沿，正交相序正确。旧运行时明确拒绝显式速度，
未改变 detent 目标和计数。固件调度回调没有保存边沿时的 GPIO 状态，后续
读实时引脚可能合并已经到达的相位。保留默认速度和高速驱动的证据边界。

## Dial 普通服务输入和快速边沿对照

在原生 Xtensa `5f8a5f38…` 上复跑同一 UIFlow2 组合镜像 `310c6eff…`。
上一版服务以 5 ms 输出时，八个正反向快速动作中应用只准确计数一次。
ESP-IDF ISR 对照捕获这些动作的全部 96 个 GPIO 边沿，正交相序完整。
仪器化的 UIFlow2 探针同样执行了全部 96 次回调，但八个动作采到的
实时 A/B 组合均出现跳变或重复。GPIO 中断将 Pin 对象排队，RotaryIRQ
在回调执行时才读取两个引脚。

将前台循环从 20 ms 缩短到 1 ms 后，八个快速动作仍少计。恢复
20 ms 循环，只省略应用每次计数变化后的 LCD 重画，六个明确指定 5 ms
的动作均正确。这定位了本探针的同步重画开销和延后采样问题。

Device Service 在支持 `paced-detents` 的 Dial 上将普通 `encoder`
请求的间隔设为 35 ms。未改动的组合镜像对 ±3、±4 各三次都准确计数。
显式 `edge_period_ms:5` 仍产生四相快速边沿。旧运行时允许普通请求
继续使用 5 ms，并在回执中返回实际间隔。最大 +128 请求的 ISR 对照
记录全部 512 个边沿，首末边沿间隔为 18.104 秒。回执的 `completion:queued`
表示输入已排队。直接控制器路径和物理硬件的声明范围保持独立。

复现时启动独立 Device Service，等待 Dial 的 `DIAL_DISPLAY` 和初始
计数，再对同一会话提交 `{"kind":"encoder","delta":3}` 等请求。
从 `/machine/encoder` 读回 `delivered-detents` 和 `gpio-edges`，
同时检查同会话串口 `DIAL_ROTARY` 的前后差值。每次动作结束后再发下一次，
并在停止前取证。5 ms 对照只增加 `"edge_period_ms":5`。

[精确固件、相序、同会话证据和清理](dial-default-pace-summary.json)。

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

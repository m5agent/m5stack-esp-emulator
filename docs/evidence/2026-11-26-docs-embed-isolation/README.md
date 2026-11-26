# 文档跨站 iframe 的浏览器隔离（2026-11-26）

对应 [#242](https://github.com/m5agent/m5stack-esp-emulator/issues/242)。
本页为浏览器 WASM 虚拟设备验证。正式文档站部署、其他浏览器和真机均未执行。
有界结果见 [summary.json](summary.json)。

## 原因

COOP/COEP 只能隔离顶层页面。文档页没有这两个响应头，所以嵌入的模拟器
即使由 Service Worker 补上 COEP，`crossOriginIsolated` 仍为 `false`，
QEMU pthread 所需的 `SharedArrayBuffer` 不可用。

## 修改

- 项目 Service Worker 在原有 COOP/COEP 之外加 `Document-Isolation-Policy:
  isolate-and-require-corp`。Chromium 137 起，带此头的文档即使位于未隔离
  父页的跨站 iframe 内也能获得隔离。它只作用于本项目的文档，不要求父页改动。
- 嵌入页的浏览器不支持该策略时，运行面板显示原因和一个
  “在新标签页打开模拟器”链接，指向同一项目地址。
- 测试新增 `M5_PUBLIC_DOCS_EMBED=1`。它由本机静态服务提供一个
  `localhost` 父页，用 `allow="cross-origin-isolated"` 嵌入 `127.0.0.1`
  的工作台，所有 HTTP 响应都不带隔离头。编辑器、CoreS3 原始 LVGL 触摸、
  按键和 Cardputer-Adv 全键盘四个现有来宾用例共用此模式。

## 结果

Chrome 158.0.8127.37，同一导出 `8864e12e…1e41`，Xtensa WASM
`8067a6b8…2c1e`。每例父页 `crossOriginIsolated=false`、无
`SharedArrayBuffer`，工作台 iframe 为 `true`。

| 设备 | 用例 | 结果 |
| --- | --- | --- |
| CoreS3 `b9fe8334…2d49` | 编辑器：启动、UTF-8、长源、错误、中断、帧像素、硬复位 | PASS，点击到就绪 10.7 s |
| Cardputer-Adv `b6255f6a…52bd` | 同上 | PASS，5.0 s |
| CoreS3 原始 `78961297…bd3f` | 负向触点、LVGL 计数和像素、PIR 双向、共享链接在新 iframe 重开后再次触摸 | PASS |
| Cardputer-Adv | 112 个物理键经 TCA8418 IRQ 送达原 UIFlow2 | 112/112 PASS |
| 两款 | 公开模型按键（CoreS3 PWR，ADV G0） | PASS |

所有来宾都以退出码 0 正常停止，5 个 pthread 与 engine Worker 由 CDP
确认消失，无 fallback 终止。同一导出的顶层 CoreS3 编辑器回归也通过。
负对照：移除该策略后，同一嵌入保持未隔离，启动按钮禁用并显示新标签页链接。

## 未覆盖

- docs.m5stack.com 实际页面的 iframe 权限、CSP 与其他跨源资源。
- Firefox、Safari 和 Android Chrome；该策略目前仅在桌面 Chromium 提供。
- 首个 CoreS3 板级用例 `test_public_qemu_board_guest.mjs` 的 `屏幕与输入示例`
  标题断言在 main 顶层同样失败（CoreS3 走 LVGL + PIR 固定示例），未在此修改。

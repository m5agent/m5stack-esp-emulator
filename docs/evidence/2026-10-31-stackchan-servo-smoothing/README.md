# StackChan 稀疏舵机状态展示平滑与 Pages 发布

日期：`2026-10-31`

## 结论

StackChan 跳舞固件的 SCS `present_position` 仍来自稀疏 QOM 快照；本轮没有
伪造更多 guest 采样。浏览器工作台现在按相邻快照的墙钟间隔，为 3D 关节做
最多 `1.2 s` 的展示插值。原始 QOM、角度标签、DOM ticks、串口和运行记录仍
保存实际采样值。

同一完整 Flash `c854d3ac6b958439ad30c5277266575d8765f228febf75de243da5d011904542`
在 Metal 硬件渲染下独立运行两次：

- 两次均为 `12/12 PASS`，均观察到 23 个原始状态样本和 30 个有效 SCS 包；
- 2 秒采样窗口分别输出 15 / 14 个中间 3D 姿态；
- 最大单帧视觉步进分别约 `9.03° / 9.34°`，修复前直接跳变样本最大约 `86.9°`；
- 原始 yaw `307..613`、pitch `677..850`、DOM 标签和 packet 计数保持一致；
- 正常 Stop 后 engine 与五个 pthread target 均在上下文关闭前消失。

## 部署

- 合并提交：`68afbd7c13669c1fb652b976b68c48364c7f0d6c`
- 源码 PR：#71、#72
- 正式地址：<https://m5agent.github.io/m5stack-esp-emulator/>
- prepared-site release：`pages-preview-20261031-stackchan-smoothing`
- release asset：`public-site-preview-live.tar.gz`，`151913554` B，
  SHA256 `1565afc97085cfa4f33760bf7655d9d19d43897f742f1615fca57dda62be2e5a`
- 部署运行：<https://github.com/m5agent/m5stack-esp-emulator/actions/runs/41158906682>
- Pages manifest SHA256：
  `22b90111ae80080ea5b7e9e73ae140af758a4ef60cfb4bd3286c0b61d4be4ae8`

正式构建工作流从同一 `main` 启动过两次，均在上游依赖下载阶段遇到
`The handshake operation timed out`，未进入浏览器验收。因此本轮使用项目既有
prepared-site 流程部署本地已审查、已真实 guest 验收的完整导出；这不改写为
regular all-admitted 发布工作流的 PASS。

## 线上验收

从正式 HTTPS 地址回读：

- 首页 HTTP `200`；
- `public-site-manifest.json` SHA256 与待部署 manifest 一致；
- `public.js` `e89d98c4…29bb8d`；
- `public-qemu-servo.js` `250e7229…3020ca`；
- `public-qemu-runtime.js` `e4e8801c…34741`；
- `public-qemu-instance.js` `04d360cf…d00c`；
- QEMU WASM `5d6c36bd…0a993`。

同一正式地址在 macOS M4、Chrome 156、ANGLE Metal 下完成真实 CoreS3 guest
验收：`30/30` checks PASS，包含 COI/SharedArrayBuffer、实际 LVGL 帧、触摸
正反例、PIR 双状态、QMP pause/resume、四档布局、历史保留、分享重开，以及
两代 engine/10 个 pthread Worker target 的实际关闭；无 JavaScript 错误。

## 验证边界

- 3D 插值只改善浏览器展示，不增加 guest 采样，也不代表真实舵机连续运动、
  速度曲线、机械行程、扭矩或电气行为。
- 物理 StackChan、LCD 光学、音频和 RF 均为 `NOT RUN`。
- regular Pages source-build workflow 的本次失败原因是构建机下载 TLS 超时；
  prepared-site 成功不替代该工作流的历史与未来结果。

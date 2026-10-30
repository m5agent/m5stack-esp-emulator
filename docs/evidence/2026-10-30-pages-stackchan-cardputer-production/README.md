# StackChan 跳舞与 Cardputer-ADV 全键 Pages 部署

日期：`2026-10-30`

## 结论

正式站点 <https://m5agent.github.io/m5stack-esp-emulator/> 已更新到包含
StackChan 跳舞固件 app-bound div6 profile 和 Cardputer-ADV 全键映射的网页。
本次通过已准备静态站的应急 Pages 流程部署，prepare 与 deploy job 均成功：

- [部署运行](https://github.com/m5agent/m5stack-esp-emulator/actions/runs/41058959787)
- [静态站 release](https://github.com/m5agent/m5stack-esp-emulator/releases/tag/pages-preview-20261030-stackchan-dance)

这不是完整远端 all-admitted 发布门禁的 PASS。最新正式 all-admitted 运行
[`41056051554`](https://github.com/m5agent/m5stack-esp-emulator/actions/runs/41056051554)
在 Sticks3 已完成功能、输入、停止和 owner finalize 后，仍被 macOS Chrome
CDP target graph 的 engine target 残留挡在部署前，因此正式发布保持
`PARTIAL`。应急部署使用当前网页源码和有界的本地真实浏览器证据，不能把
远端 target graph 异常掩盖为 PASS。

## 精确身份

- GitHub Pages manifest SHA256：
  `3c3cdb2f3ea71b458d48c9b6203282ee14bc205e9edad257cb955094c24a958b`
- 静态站 release asset SHA256：
  `ad0607f01cac1b7d313b21a1cd339341156f36535bfc5cbca0e21e5206757026`
- 静态站 release asset bytes：`151909857`
- browser QEMU WASM SHA256：
  `5d6c36bdafc1129c2652b5ba9422f3deb5ab170475748cea96fdc4cf9520a993`
- Worker finalize wrapper SHA256：
  `bb62533b0e8a2899e017ddcf78935b35759dd6784d6d6c855b601d5e8b49f753`
- Cardputer canonical keymap SHA256：
  `28ec5ab41b3e636ee7fea3200de474eeaec62aadfad0de07729e4f8c8d1dd37b`

线上 `public-site-manifest.json`、`public-qemu-instance.js` 和
`cardputer-adv-keymap.js` 的 SHA256 与待部署导出逐一相等；线上
`qemu-browser-profiles.json` 精确包含：

- firmware SHA：
  `c854d3ac6b958439ad30c5277266575d8765f228febf75de243da5d011904542`
- profile：`stackchan-wasm-dance-div6`
- clock divisor：`6`

## 验证

在 macOS M4、Chrome `156.0.8078.74`、硬件 ANGLE Metal 和当前
`5d6c36…a993` WASM 上：

- StopWatch：`24/24 PASS`；engine 与五个 pthread target 在 iframe 移除前关闭。
- Sticks3：`25/25 PASS`；同样完成 owner normal finalize 与零 target 清理。
- StackChan 跳舞完整 Flash：`11/11 PASS`，yaw `307..613`、pitch
  `677..850`，模型/DOM/角度标签同步。
- Cardputer-ADV `4faaccde…2bd7b`：`36/36 PASS`，56/56 物理键和
  55/55 direct PC code。

线上回读结果：

- 首页 HTTP `200`，Pages Service Worker 后 `crossOriginIsolated=true`；
- 首页、完整 WASM、manifest、Worker wrapper、keymap 和 profile 均 HTTP `200`；
- 线上 manifest/profile/keymap/wrapper 与待部署导出 SHA 精确一致；
- 真实 Chromium 页面可切换到 StackChan 并显示模型工作台。

线上 CoreS3 guest 重测在 M5Burner composer 下载阶段收到上游 HTTP `503`，
因此该次公网 guest 重跑为 `NOT RUN`；这是上游依赖失败，不以静态资源一致
替代 guest PASS。

## 边界

- 本记录是 `virtual-device validation`；物理舵机、机械行程、电流、USB
  供电路径、实体键盘、LCD 光学和 RF 均为 `NOT RUN`。
- 应急 prepared-site 部署不等同于正式 all-admitted 发布 PASS。
- macOS hosted runner 的 CDP target graph 与 normal `Worker.terminate()`
  仍存在独立的可观测性/回收差异，regular publication gate 保持 OPEN。
- 结论只覆盖列出的 manifest、WASM、Flash SHA 和 profile。

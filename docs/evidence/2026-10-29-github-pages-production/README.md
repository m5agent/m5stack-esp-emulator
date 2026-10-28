# 正式 GitHub Pages 部署与公开 CoreS3 验收

日期：`2026-10-29`。结论限定为 `browser virtual-device validation`；
物理硬件、RF、声学、光学和电气验证为 `NOT RUN`。

## 部署

正式站点：
<https://m5agent.github.io/m5stack-esp-emulator/>

源码提交：
[`8e47c6ba`](https://github.com/m5agent/m5stack-esp-emulator/commit/8e47c6ba83c042398d767a8d56ff47c16b927181)

Pages 来源已设置为 GitHub Actions。工作流在 main 上以
`publish=true`、`base_path=/m5stack-esp-emulator/` 手动运行：

- [构建 job](https://github.com/m5agent/m5stack-esp-emulator/actions/runs/40719197233/job/122925130720)
  在 `13m53s` 内完成固定源码 C/QEMU、LittleFS、静态导出和真实
  CoreS3 guest 验收；
- [部署 job](https://github.com/m5agent/m5stack-esp-emulator/actions/runs/40719197233/job/122933361298)
  在 `14s` 内完成 GitHub Pages 发布；
- 站点根地址返回 HTTP 200，公开 manifest 的 `base_path` 为
  `/m5stack-esp-emulator/`、`service_url` 为空、`firmware_bundled=false`，
  共声明 `1922` 个资产。

## 独立公开复验

部署后使用同一验收器直接访问正式 HTTPS 地址，21 项检查全部 PASS：

- Service Worker 取得控制并启用 `SharedArrayBuffer`；
- 实际 CoreS3 C/QEMU 客体进入 ready，显示真实 `320x240` RGB 帧；
- DOM 触摸负控不触发，有效触摸到达 LVGL 回调；
- Port A PIR 的 `0/1` 双向变化与 QOM 回读一致；
- QMP 暂停停止客体推进，继续后恢复；
- 1440/1024/768/390 四档布局无横向溢出；
- 停止/重开均自然退出，Worker 与 iframe 清理完成；
- 页面无 JavaScript 错误，也未访问 `/api/v1` 或本机模拟器接口。

公开验收原始报告 SHA256：
`3251b33ef5fb76340a48f8cbd3e780ee3b9ce86caf613f176b58a90ffa6bee33`。

## 固定执行身份

| 项目 | SHA256 |
| --- | --- |
| Site manifest | `ba041639ad8959c9d9c529db02a41d1cb59a349f875fec7e2c50a62ff8c50187` |
| Runtime manifest | `59ff1fb5a43b0aae6aa25da5d357b5246621c190c5ad18de482f78e23a5fe124` |
| C/QEMU WASM | `716f3b6a8750335613da2897be0933d1497965962d0dc1b3f2754ebf76316c89` |
| ROM | `b5c7090cc22efce51c1323cef31ca96fcd673a5b1d1b1017e219d393f2659913` |
| 最终 Flash | `78961297e751ec9c743b4cdf89cc2c137e7e2c801dda3ead9df2ea45d59fbd3f` |

Runtime source commit 为
`40edccac415693c5130f91c01d84176ae6008566`，构建类型为
`source-build`，Emscripten `3.1.50`。链接审计确认主栈和 pthread 栈均为
64 KiB，`STACK_OVERFLOW_CHECK=2`。

## 边界

当前公开 profile 仍是 `cores3-wasm-vm-div8`：虚拟时间和 watchdog 到期
相对墙钟慢放 8 倍。默认墙钟调度、长期稳定性、网络、音频、其它设备/Unit、
任意固件兼容性和 Flash 持久化均未由本结果覆盖。本结果不证明物理硬件行为。

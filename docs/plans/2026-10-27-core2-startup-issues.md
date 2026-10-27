# Core2 首帧、网络初始化与 LVGL 阻塞修复

日期：2026-10-27。起点：`origin/main@a0ad8150`。
本轮范围为 GitHub #2、#3；执行队列仍以 `docs/project-backlog.md` 为准。

## 目标与约束

- 先核对原 issue 的 UIFlow2 v2.5.3、复测固件和运行时，不将 legacy
  UIFlow1 v1.15.4 的 LVGL7 等待归因为另一固件的同一个缺陷。
- 用阶段串口、同一 session 的 framebuffer、QOM/网络数据面定位阻塞；
  不用宿主假值、关闭 watchdog 或放宽网络隔离制造 PASS。
- 功能复现通过可见 Device Service `/api/v1`，先收 evidence ZIP，再
  `purge=0` 停止。固件、凭据、原始私有 app 和大 ZIP 不提交。

## 调查与实施

1. 同步主线，读取两个 issue 的原文、补充和最新复测，核验各自固件身份。
2. 并行检查 WLAN 初始化及 LVGL/SPI completion，保留失败负控。
3. 对证据确认的根因做最小修复，并添加覆盖真实行为的回归测试。
4. 验证原触发路径：底层绘图、Widgets/LVGL、离线 WLAN 查询及有界
   网络失败；有网络功能声明时收集同 guest 网络证据。
5. 跑平台和生成物检查；controller 变更按仓库门禁跑受影响组及完整矩阵。
6. 更新状态、台账与快照，归档精简可重放证据，独立审查后提交新 PR。

## 完成标准

- #2：最小 Core2 绘图产生非黑帧；至少一条 issue 启动路径产生有内容
  的帧或可解释的 Python 异常。
- #3：`WLAN` 创建、`active` 和 `isconnected` 返回，离线网络失败有界；
  应用能到达 `loading...`，且串口明确标出失败阶段。
- UIFlow1 LVGL7 如有修复，必须另外绑定该固件 SHA、真实 SPI completion
  与 `lv_disp_flush_ready`，不能继承 UIFlow2 PASS。
- 所有结论标记 `virtual-device validation`；硬件验证另行记录。

## 结果

公开最小复现定位为普通 Core2 缺少 WiFi MAC/MMIO；0049 补离线控制器，
服务统一 Core2 deterministic clock。实际截图另发现 LVGL SPI DMA 双消费，
0050 修复后相同源码显示正常位置与字形。冷构建补回已有 0034 timer 修复。

最终运行时的四个启动探针及两个连续显式 WiFi session 通过，Core2 外设组
6/6 通过；平台与完整矩阵的最终状态单独写入
[本轮摘要](../evidence/2026-10-27-core2-startup/summary.json)。
本机未取得原始私有完整应用归档，用户同意按已有公开路径继续验证；
不声明原 app 整包业务或旧 UIFlow1 LVGL7 已通过。

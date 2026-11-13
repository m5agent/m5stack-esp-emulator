# 2026-11-13 新增模拟器问题复核

本页保留本轮逐问题结果；所有功能证据均为 **virtual-device validation**。

## #218 主动关机

服务使用 QMP `SHUTDOWN` 的 guest/reason 与 `query-status=shutdown` 判定主动下电。
`-no-shutdown` 让服务在正常回收前读取最终屏幕，原来的取消、lease 和进程围栏仍负责清场。
退出码 0、串口文案和白屏均不作为关机原因的替代判据。guest panic 和宿主异常继续失败。

两份公开原版 BIN 经独立 Device Service 的 artifact → firmware → session 路径运行，
刻意等待不会出现的就绪 marker，均能在启动阶段主动关机并正常收口。相同运行时上，
批量固件 runner 分别得到 `PARTIAL/guest_poweroff`、`application_ready=false`。
[逐固件身份、QMP事件、末帧和ZIP哈希](poweroff-summary.json)。

PaperColor 最终帧全白；PaperDIY 保留黑白图像。这里只证明帧保存与关机语义，
没有用非黑像素或一张图宣布应用就绪。PaperDIY 的首次短观察窗口在下电前结束，
仍为 `PARTIAL/no_observable_input_response`；默认时间线的后续独立运行观察到主动关机。

复现时使用这两款固件的原版 BIN（哈希见摘要），通过 `/api/v1/artifacts` 上传，
`POST /api/v1/firmware` 指定设备和 `kind=merged`，再创建 `runtime=qemu` 会话并
设置一个不存在的 `ready_marker`。轮询至 `stopped`，读取串口、`frame.png` 和
`evidence`，最后 `DELETE /api/v1/sessions/{id}?purge=0`。期望无启动错误、
`stop_reason=guest_poweroff`，末帧可读、worker lease 已释放。无需改写应用或 NVS。

本轮没有物理硬件、光学或浏览器 WASM 验证。

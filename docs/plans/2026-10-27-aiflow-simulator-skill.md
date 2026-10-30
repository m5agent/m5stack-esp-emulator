# AIFlow simulator skill consumer

日期：2026-10-27。归属 `UNIT-01` 的 AIFlow 调用侧；不修改控制器或固件模型。

目标是在本机开发的 AIFlow 中，以可分发 skill 调用现有 Device Service，完成代码/资源
checkpoint、同 guest Run、报错与屏幕检查、主机/Unit 选择和用户预览。权威实现位于
AIFlow SDK 的 `skills/uiflow2-simulator/`，接入涉及其 Agent skill 选择、配置、网络
sandbox 和事件脱敏。该目录可独立分发，helper 只依赖 Python 标准库与公开 API。

## 已完成范围

- 动态查询 devices/units、准入与冻结接线；完整包白名单、资源保留和显式删除。
- Preview/Run owner、generation、幂等请求持久化；模糊响应保留恢复状态。
- 当前 execution 的增量串口、Run 身份与 PNG SHA 校验、应用 READY 完整行、异常分类。
- Unit/host 输入、显式续租、取消、关闭前 ZIP 与历史保留。
- 已配置地址才启用 runtime skill；仅允许配置的服务地址/端口；Token 文件由 helper
  使用，凭据不进入 prompt、用户事件、链接或分发包。
- 为本机现有 loopback Device Service 提供临时 LAN TCP bridge；保持同一服务、
  原有鉴权和会话，不为局域网入口重启其他线程的设备。

## 本轮限定验证

CoreS3 + PIR 通过可见托管 Preview，运行三文件应用（main.py、模块、文本资源），
按冻结 GPIO 和原 PIR 驱动读取输入；off/on 的 Unit controller 状态、guest 串口与
320×240 Run-bound 画面一致。故意抛出 RuntimeError 后，helper 返回失败并保留
traceback；完整包恢复后在同一 session/VM 再次正常运行。关闭前 ZIP 已取得，
Preview closed、日志/末帧/history 保留；没有操作其它任务的会话。

LAN 入口已验证 health/Live sessions HTTP 200、缺少授权的控制 API HTTP 401。
官方 sandbox runtime 的无模型测试验证 helper 经运行时代理访问允许的 IP:port，
未允许端口被拒绝，直接绕过代理的 socket 被 OS sandbox 拒绝。
helper recording-server 测试与 AIFlow Agent/config 回归另有本地工作记录。

这不是局域网 AIFlow 的部署或真实模型任务验收；该运行实例仍需同步接入代码并配置
其本机 Token 文件。不同主机、Unit、固件 SHA 不继承本轮功能 PASS。没有真机部署。

## 本机 LAN 入口管理

```bash
./manage-preview-lan.sh start
./manage-preview-lan.sh status
./manage-preview-lan.sh logs
./manage-preview-lan.sh stop
```

默认从本机 en0 获取 RFC1918 IPv4，绑定该地址的 8787 并透明转发到现有
127.0.0.1:8787；也可按 `help` 指定 bind。仅管理桥进程，不管理 Device Service。
地址属于 operator-local 配置，不写入已提交 skill。Token 始终独立配置。

预览页面路径为 `/platform/web/sessions.html`，用户按返回的 session ID 选择设备。
当前没有经过确认的 per-session deep link。页面和 helper 轮询不自动续租。

## 保留边界

需要“先看预览、确认再推硬件”的任务必须使用 AIFlow `deploy_mode=none`，然后另发
获授权的部署请求。原 `server` 模式会在任务结束后自动推送，skill 文字不能暂停它。
本次不修改既有自动部署语义。

独立 Live sessions 页面和可下载 PNG 已可用；AIFlow 内嵌预览、生成中 checkpoint
事件、SSE、虚拟目标产品界面、长期 revision 回收和多租户控制继续留在既有 Backlog。
同 VM 更新仍是 interrupt-only，不保证清空 native、timer、IRQ 和 thread。

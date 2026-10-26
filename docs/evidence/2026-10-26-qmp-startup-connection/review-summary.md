# QMP startup race candidate review — 2026-10-26

确定复现源码竞态，符合两次历史失败现象；历史没有逐 attempt 的 connect/greeting
日志，不能声称完整重演当时的线程顺序。两次历史记录仍为 FAIL，未追认 runtime
或 Unit PASS。当前 service 源码、gen7、runtime 和 profiles 均未修改，也未新建
Device Service session 或启动 QEMU。

## Top 3 假设与结论

1. **启动与 HTTP 轮询重复创建同一 QMP endpoint 的连接：强支持，源码已确定复现。**
   `_launch()` 在 `device_service.py:5640` 暴露 `_proc`，再做两次 process inspection
   和持久化，最后在 `:5662` 无锁无 None 检查地创建连接。与此同时，booting 的
   `frame_metrics()` 在 `:5942` 被允许，经 `:5953` 调用 `_qmp_call()`；后者在
   `:5700–5705` 的锁内发现 `_qmp is None` 也会连接。任一初始化顺序均可重复建连。
   QEMU `chardev/char-socket.c:907–909` 在接收一个 client 后停用 listener 的
   client callback；`:932–933` 也明确拒绝非 disconnected 的新增 client。
2. **资源压力导致 guest/QMP 启动一直慢：与现有证据矛盾。** 两次在 booting 后
   约 0.1 秒就有首份 HTTP 200 live frame；串口早已 READY，随后持续循环到服务
   的第60秒失败。压力可扩大竞态窗口，但没有调度/CPU 历史采样，不能归因为慢启动。
3. **QEMU 崩溃、错误 socket 路径或 bind 失败：无支持。** 截图必须经过同一
   `_qmp_call("screendump")`，QOM 也在失败前仍成功；stderr 仅记录最终来自服务
   的 SIGTERM。没有历史 lstat/accept trace，故不推断 socket 在全部瞬间的状态。

## 历史时间线（UTC；本地为次日 UTC+8）

| 阶段 | Atom boot `4c0070…` | Limit R4 `648367…` |
| --- | --- | --- |
| created | 18:38:33.839667 | 18:52:21.270514 |
| booting | 18:38:46.057594 | 18:52:45.496691 |
| 首次 live-frame HTTP 200 请求时间参数 | 18:38:46.145 | 18:52:45.596 |
| guest 串口 | `HOST_PROBE_READY`，BMI identity 循环到232次 | `IO_PROBE_READY limit`，持续 `IO_LIMIT 1 0` |
| 最后 live frame | 18:39:45.492267 | 18:53:45.258620 |
| 最后 live QOM | 18:39:44.291835 | board 18:53:45.377433 / Unit 18:53:45.191915 |
| failed | 18:39:46.108008 | 18:53:45.574748 |

入口证据是 `.work/unit-device-service/sessions/<id>/{events.json,serial.log,
last-frame.json,device-state.json,qemu.stderr}`。Atom serial lines11–17 / Limit
lines11–14 含 READY；两份 events 的 lines30–38 绑定 booting 与 failure。
generation6 HTTP log 首次 frame 200 位于 lines27954 / 32810。Limit 浏览器
`web-report.json` 的 readback[1] 在18:52:47.861437 已返回 booting/live/guest-qom。

错误文案不能证明 socket 缺失：`run_profile_ui_test.py:112–118` 的构造包含
connect、greeting、capabilities；`:150–159` 吞掉所有 OSError（含握手 TimeoutError）
后统一报 socket did not appear。第五项真实 AF_UNIX 传输测试确定复现：路径始终
存在、第一连接继续可 query，第二连接无 greeting 仍收到这条缺失文案。

## 最小候选与回归

`startup-qmp-lock.patch` 只给 `_launch()` 的建立连接段加 `self._lock`，在锁内
检查 `_qmp is None`，复用早期 HTTP 已建立的连接。60秒启动预算、2秒命令预算、
真实错误和清理契约不变。没有改 wait_qmp 的错误分类或扩大 retry。

正常 unittest 已准备为 `test_device_service_qmp_startup.py`，直接 import
device_service 并复用现有临时 fixture，可直接纳入 platform/tests。两种顺序由
thread Event 和非阻塞 lock acquisition 观察器强制，未靠 sleep 制造顺序。
其余三项确认真实启动错误504/原60秒预算、命令超时关闭连接、存在 socket 的
握手超时分类。A/B 都运行同一正常 unittest：baseline **3 PASS / 2 FAIL**，
candidate **5/5 PASS**。测试只验证 host control plane，不作为 guest/硬件结果。

## 其他入口审查

- `_qmp_call()` 和 `_qmp_execute()`（`:5699`、`:5726`）已有同一 RLock 及 None
  检查；与本候选连成同一个初始化临界区。
- `reattach()`（`:3401–3460`）确实先创建本地 qmp 再赋 self，但当前唯一调用来自
  `_restore_history():8169`；该 session 在 `:8182` 才注册，restore 发生在
  janitor 创建之前（`:7783` / `:7788`），且 HTTP server 尚未接收这个对象。
  当前没有并发 API exposure，无需在本次扩大 patch；将来若开放 live reattach
  endpoint，必须另加同一对象的初始化锁/生命周期校验。
- QEMU radio/native-HCI lanes 复用 `_launch()`，因此覆盖同一竞态入口。Tab5 用
  GDB framebuffer；独立 network diagnostic lane 不使用该 QMP 初始化。

应用应等待 gen7/27 cohort 结束。随后运行新增 unittest 和现有 service checks，
以新 generation 记录真实 flashing→booting→running 与 host9；不改写历史失败。

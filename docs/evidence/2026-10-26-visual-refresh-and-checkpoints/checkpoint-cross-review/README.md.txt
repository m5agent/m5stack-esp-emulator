# Checkpoint API 独立审查

开发与虚拟设备实测日期：2026-10-26；封存、独立复核与归档日期：2026-10-27（Asia/Shanghai）。

最终状态：**PASS，剩余缺陷 0**。发现的一项 P3 OpenAPI 错误响应遗漏已由 root
修复并独立复核；原发现保留在 `findings-original.md`，修复收据在
`resolution.json`。审查者未实现本次 checkpoint API；本人模型浏览器测试未列入
此次独审范围。未修改产品、vendor 或仓库文档，未启动新 guest 或访问真实硬件。

## API 与宿主契约

读取 `device_service.py`/`serve.py` 新增分支、不可变 package store、MPY 结构检查、
现有 guest 部署/错误处理，以及 API/OpenAPI/Agent 指南。原始 diff、9 份源快照与
SHA 索引均在本目录。原 API 15 项测试通过，另有 3 项独立宿主场景通过：

- 活跃程序期间保存语法尚未编译的 checkpoint，旧收据/事件保持原字节，未部署或执行。
- host 结构有效的 small-int 32 `.mpy` 保存成功；在同步中断之后调用真实
  `validate_mpy` 对 guest 31 位能力检查，返回 HTTP 409、新执行为 failed、旧执行为
  interrupted，未执行入口。
- 引用读取存储不可用返回 HTTP 503，当前程序及事件未改变，program lock 释放。

这些场景运行真实 HTTP handler/临时 store；guest 部署/执行和进程启动被明确
mock，不能继承为虚拟 guest 或硬件运行证据。日志是 `unittest.log` 与
`independent_probe.log`。

| 关注点 | 结论与证据 |
| --- | --- |
| 保存不触碰 guest | 保存仅规范化/结构检查/store create；15 项 API 测试和独立活跃程序保存场景通过 |
| 引用不重新 create | reference 分支只 get/read_files；两个 create 方法被设为抛错的负控通过 |
| 三种请求互斥 | source/files/revision_id 恰选一；引用只准 revision_id/expected_execution_id/timeout_seconds；非法混用在执行分配前拒绝 |
| 旧 source 兼容 | 原 Python identity、64 KiB、默认 10 秒/最大 30 秒、直接 run_source 保持；package/reference 为默认/最大 120 秒 |
| 格式与 guest 兼容分层 | 已知非法/native MPY 在公共保存/引用分配执行前拒绝；实际 guest small-int/版本错误可在中断旧程序后产生 failed 收据 |
| 并发与停止 | reference 与 source 共用非阻塞 program lock；读取/部署期间 stop fence 及 unknown/interrupted 语义通过 |
| 实际 limits | 动态 package max_count、64 文件、每文件 256 KiB、总 1 MiB、HTTP 2 MiB、gc=false 与 OpenAPI 一致；package 上限 256 独立于 Python source 上限 |
| 错误响应 | 400/404/409/413/429 及损坏 500/存储 503/确认超时 504 的路径核对；唯一 P3 文档遗漏已修 |

最终 OpenAPI SHA256：
`aaa3e90ec0db8ed9f73763148922b5b6883d2d71734ffbee75cfc884f43ea162`。
独审期间源范围仅该 YAML 有变化，后端与测试字节保持一致。没有 Preview/Run
编排、latest-wins、保 VM 的单 Run 取消、多租户所有权或 GC 已完成的结论。

## 两批已有虚拟 guest 原始证据

另对已有 CoreS3/PIR 与 CoreS3/Relay 的原始 report、HTTP body/header 记录和 ZIP
做独立只读交叉核验，没有使用作者 `independent-audit.json` 作为另一审查者结论。
可重跑的本地审查脚本为 `audit_live_bytes.py`，收据为 `live-byte-review.json`。

- 主流程 HTTP 共 **983**（PIR 572、Relay 411），逐个核对原响应 body 的 size/SHA、
  status 与完整有序 header pairs；另 4 份 post-stop 历史/末帧 GET 收据单独核对。
  本批实际重复 header 项为 0，不能说观察到了重复 header；捕获保持了重复项能力。
- 两 ZIP 各 **84 成员、12 execution**；逐成员 size/SHA、完整执行 ID 集、固件/PID、
  保存前后 checkpoint identity、原文件与 guest deployment inventory 均相符。
  A/B/C 保存、重复 POST、GET 都在 session 创建前完成，结束后 GET identity 不变。
- 每例合法 A、B、B-recovery、C-recovery 四次仅按 revision_id 运行。
  八种 reference 拒绝都无 execution_id 分配；按 HTTP 顺序确认拒绝之后的
  program GET 仍为 B/running，再建立新的 serial baseline，之后读到 fresh B。
- 27/23 个串口观察窗口与 ZIP `serial.log` 的原始 byte offsets/窗口交叉一致；
  `prefix_sha256` 的原约定是 UTF-8 errors=replace 后重新编码的文本前缀哈希，
  不是原始 UART 前缀哈希。原始 UART 整成员 SHA 与 byte 窗口另行核对。
- 真实 QOM Unit 状态来源 guest-qom、available、errors 与输入窗口相符；最终帧
  SHA、320×240 PNG、原资源文件均匹配。此项是虚拟控制器/UART/帧证据。
- HTTP 顺序明确先 evidence ZIP，再 DELETE purge=0。ZIP 内末程序仍 running，
  停止收据与后续历史里的末程序实际为 **interrupted**，不改称 cancelled。
  Flash 释放、历史/末帧保留，原 PID 2416/2668 在本次独审时均已退出。
- 两例开尾 runtime provenance 均为相同 QEMU binary SHA；11 个明确列出的
  on-disk 源文件 size/SHA 匹配。该列表不等于所有 backend 依赖，也不构成已加载
  Python 模块的独立 attestation。没有物理硬件验证或单 Run 取消结论。

| 批次 | 原 report SHA256 | ZIP SHA256 |
| --- | --- | --- |
| PIR | `4019af25431ef5c5acaa275fb7a6279b6be6f8aa8e9b6d67bda8711fa26166ed` | `d599f1728bb92fe5bba64247a5ae40ff10c5e5272a7b4d90f422f53bd0e6d0c4` |
| Relay | `b05b12e65815dd46eaf86729a4ded7c820acdae327911f6a7bdf0f83ea1b8181` | `dffd3992dc867ec2f656a4b97365d5d913084cd387b7c05e206737c75b35c36e` |

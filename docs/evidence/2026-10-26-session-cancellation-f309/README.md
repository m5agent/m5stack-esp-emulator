# 会话启动取消与真实 Unit 回归

日期：2026-10-26。代码基线为 `23af04bc` 上的本块修改，实际源码 SHA 见
`source/` 与 `copy-provenance.json`。外部 agent-work-logs 按用户要求
`SKIPPED_BY_USER`。本包是 virtual-device / host lifecycle 证据，hardware
validation 为 `NOT RUN`。

## 实际 Device Service

`live/result.json` 为两个不同会话的实际结果，均走 8787 `/api/v1`：

- 含唯一注释的新十九文件源码通过 `/firmware/uiflow` 生成不可变镜像，并带
  source pin 创建 AtomS3R + PIR。冷 Flash 准备期间请求 evidence ZIP，再只发
  一次 stop。约 1.007 秒返回 `stopping / stop_pending=true`，当时租约和容量
  仍占用；准备退出后自动停止，没有进入 booting/running，Flash 被释放。
- 同一不可变镜像随后创建新的实际 guest，READY 后发送 PIR true/false，分别
  以输入前串口 offset 后的新 `IO_PIR` 行和 guest QOM 读回核对。原生 PNG
  非空，停止前 ZIP、停止后最后帧/历史、Flash 释放和 PID 退出均保留。
  QEMU 实际可执行文件 SHA 为 `d1ba0063…`，worker generation 为 13。

同固件 SHA 为 `240d70e6f00317cbfd20246662a889c6546bcc5050973ad38079292ba829837b`；
caller source SHA 为 `2786bbcc6b56199c3afa8566e48ab7056be7d959dc2caf90e9d3d56cd309862a`。
第一次会话只验证准备取消，没有执行该程序；第二次才提供 Unit/画面运行证据。
没有拼接为一个 guest，也不把约 1 秒的停止确认当作资源清理完成或性能 SLA。

`live/http-calls.json` 及对应原始 request/response 保存 113 次实际 HTTP 调用，
包含 ZIP-before-stop。`live/final-health.json` 与 `live/final-worker.json`
分别确认活动会话和 worker lease 为零。输入、串口和画面为分次采集，非原子快照。
没有运行 AIFlow 全链路、同 guest 程序更新、其它主机/Unit 或硬件测试。

## 宿主生命周期与剩余边界

修复以每会话生命周期事务串行化资源创建/发布/清理，停止事件单调设置。
准备、Popen、QMP、readiness 和 radio retry 均有取消检查；QMP 原有连接锁归属
保持。慢阶段未退出时返回最小 Session 状态，不提前释放 lease、Flash 或 purge；
退出后自动收尾。并发追加 purge/释放 Flash 意图按版本再消费。

Tab5 reset/失败、Network 自然结束、租约失败重试、重附着进程杀停未确认、服务
draining 和在途 janitor 均有独立宿主回归。Network runner 新增原子生命周期
收据，先记录再创建 child；BLE 等待可取消，子进程与 fixture 清理未确认时
禁止报告完成。强杀后缺少有效收据时会保留 `stopping` 和 lease，需要进一步
核查；这不是任意不可信固件或物理跨主机的外部 side-effect fence。

宿主测试的进程、QMP、时钟等边界采用隔离 mock；不能转授为所有后端的实际
设备执行。其它后端的同场景现场验证、完整低延迟预览和性能基准仍待继续。

新增会话生命周期40项与Network runner17项隔离测试通过；最终完整平台回归
709项通过、零跳过，源码/测试前后SHA一致。前一完整轮的夹具初始化错误和状态页
篇幅/职责失败均保留；修复后独立重跑完整轮，不拼接补跑。本块未改QEMU
controller，也未重跑完整外设矩阵；不继承为新的矩阵或硬件结论。

## 来源与重放

`copy-provenance.json` 记录逐字节运输的来源/SHA；捕获代码改名 `.py.txt`，
内容未改。harness 原路径是 `.work/aiflow-cancellation-live-20261026.py`，引用
前批 `.work/unit-source-host-io-20261026/live-rest-r1/atoms3r/pir` 的原请求；
该请求也可从前批仓内归档恢复。本包 `live/source-request.json` 保存本次完整
caller，`live/session-request.json` 绑定本次 source pin。重放必须重新 compose
并用新响应创建可见会话，不能把历史 session ID 当现存运行。

最终测试日志、版本收据和顶层 `SHA256SUMS` 随本块收尾归档；校验存储字节可用
`shasum -a 256 -c SHA256SUMS`。原始失败尝试保留为过程证据，不计入最终 PASS。

`audit_archive.py` 离线核对来源副本、ZIP CRC/成员、图片与凭据候选；扫描器复用
相邻已归档脚本，路径与哈希写入 `archive-audit.json`。唯一候选为新增宿主测试
中验证“凭据不写入收据”的非工作 mock 输入，按完整文件 SHA、AST 行号和值 SHA
精确审查。报告保留候选计数 1、已审查 1、未审查 0，不设通用放行、不改原字节。

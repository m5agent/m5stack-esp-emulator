# 同 VM Preview / Run 控制面

日期：2026-10-27。归属 `UNIT-01`。状态：已实现；CoreS3 PIR/Relay限定真实会话验收见[证据](https://github.com/m5agent/m5stack-esp-emulator/blob/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence/2026-10-27-preview-run-control/README.md)，部署事务取消另有PIR实测，不关闭AIFlow/其它Unit。
执行顺序只在 [Backlog](../project-backlog.md) 维护。

本块把公共完整 checkpoint 接到稳定 Preview：首次准备一个可见 UIFlow session，
后续 Run 只引用不可变 package，在同一 guest 串行切换。保留旧同步 `/program`，
不改变已有 source/files/hash/evidence 契约。Preview/Run 新接口在对应测试和
8787实际会话通过前，不写成已交付。

持久化控制面使用独立 SQLite ledger，WAL、FULL、短事务；一次提交原子记录
Run/execution身份、generation、desired、幂等原收据及revision pin。只支持验证
控制Bearer后的local-control principal，轮换token对应同一principal；body不能
声明owner。没有配置控制token时新Preview入口返回503，旧入口授权规则不变。
不声明多租户隔离。保留记录计入固定配额，GC disabled，不通过增大配额代替回收。

每Preview一个worker、一个UART传输owner、一个pending desired。新提交覆盖
未写UART的旧queued Run；传输中的旧Run只单调取消，迟到START/返回不能重获active。
新Run前先完成实际raw prompt确认，取消不设置session stop、不重启或换guest。
中断失败保留cancelling/unknown与阻塞原因，不自动重传。START不等于应用READY。

session在发布前持久化管理binding及实际reference pin；旧HTTP程序/重置/输入/
续租/停止/删除不能绕过协调器。分配先写allocation intent；服务重启只接管有
可验证binding的已有session，不凭旧幂等key盲建第二个guest，也不重放不明Run。

输入必须带owner epoch和expected_run_id，并取得该Run的in-flight permit。
切换先关闭旧输入准入，等待旧QMP操作完成/释放momentary，再发新程序；只捕获
同一session指针后放锁不足以隔离同VM的迟到输入。慢UART/QMP不占DB或全局锁。
帧采集前后都核Run/execution，身份改变返回409；历史没有对应样本返回410，
不能给旧Run返回新Run图片。Unit、串口和帧分别采样，不宣称原子设备快照。

验收先用宿主阻塞点验证并发幂等、A/B/C覆盖、取消各阶段、迟到结果、输入drain、
失败raw prompt和重启窗口；再用8787可见CoreS3 PIR/Relay验证原驱动、同PID/
固件/VM nonce、完整包及字节码依赖、突发提交、独立取消、实际画面与输入。
先取evidence ZIP再close/purge=0，并独立核PID/Flash释放和历史/末帧。
无C/QEMU变更时不启动完整矩阵。

本块不关闭其余Unit协议、main.mpy、保存开机、hotplug、SSE/后台采样、AIFlow端
checkpoint/virtual target接入、完整native/IRQ/thread清场或物理硬件验证。

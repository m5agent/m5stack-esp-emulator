# 公共 main.mpy 实时运行：分层证据

日期：2026-10-27。本块功能验收完成，UNIT-01整体继续。

API1.46把已验证loader接入公共Session和Preview。服务的受控bootstrap经真实UART
执行固定官方纯bytecode canary，按实际if-main/文件/模块身份与owner恢复判定能力；
能力绑定当前session/device/firmware/runtime/PID/进程启动标识/worker代际。
默认stock保持source-only，不根据请求字段或镜像标签授予二进制能力。

| 层级 | 已验证范围 | 入口 |
| --- | --- | --- |
| 宿主事务/契约 | 动态proof/身份逐项负控、stock/unknown在旧程序与配额前拒绝、RESTORE_ERROR撤权、reset/恢复不继承；Preview ABI32/read期间撤权/最终admission锁与null pair早拒绝 | [宿主验收](host/index.json) |
| 真实8787 API | gen45/新7c898 runtime，CoreS3 stock与兼容候选的ordinary session；stock1执行、candidate8执行，后者5次main.mpy。原bytes重跑、仅dep更新、if-main/真实file/三模块身份、异常/格式早拒绝、PIR/UART/QOM/PNG、Ctrl-C回同VM源码通过 | [API/runtime](api-runtime/index.json) |
| 真实托管Web | 同一个candidate Preview最终5执行，其中3次main.mpy；Web只读加载、2次Run、PIR真/假、取消、显式新main.py再Run；count1→2→3、nonce/owner不变，原checkpoint无变化 | [Web验收](web/index.json) |
| 清理 | 三个guest共14执行（8 main.mpy、6源码）；三个最终ZIP共86成员已核CRC/manifest/文件SHA。全部先ZIP再stop/close，PID消失、Flash/lease释放、服务active/lease均0，历史末帧精确SHA保持 | [API终态及指纹](api-runtime/index.json) |

stock prepared firmware为`0ede40601c1e37b7ba32c87a3ca55e4da7a448f6cf52957f005763bc7c7c78e8`；
候选prepared firmware为`28b16f0b192d037ecc44008efcbc32e43dc787c388fa92d66267694a140fdf4c`，
源manifest base normalized SHA为`3cb901cbfebd616a96292f234fe88ad1b145c3bb019f256dcb57257d78f878d8`。
runtime SHA为`7c898e8d456f2d85bf75481f8d90b4ef493dcef00a290053c4b804c387f2018e`。
候选完整构建来源及原merged SHA见[官方兼容构建](../2026-10-27-binary-checkpoint-admission/firmware-build/index.json)；
前块[loader诊断](../2026-10-27-flashlight-and-uiflow-base/loader/index.json)不替代本块公共入口验收。

main.mpy原字节经guest文件系统写入/回读/哈希/发布，再由官方override-main importer
执行，没有host解释或字节码重写。LOAD只证明import派发，不能代表应用body/ready；
公共application_started/application_ready仍null。测试程序自己的新鲜串口nonce/count、
模块身份、PIR实际GPIO和独立frame/QOM另证其body运行。有限import返回及正常异常
后经finally恢复才发DONE/ERROR；恢复不确定单独RESTORE_ERROR并撤销能力。

Web mandatory六阶段通过，6张direct非空PNG与12张mounted/card截图独立保留。
可选Playwright body capture有8条HTTP200观察为0字节PNG（2历史session、6本Preview），
保持PARTIAL，不当PNG，也不称实体不存在或完整texture-transfer证明。正常304没有
entity，另行记录。真实执行与UI不依赖这些可选空体。没有硬件/光电/机械/射频结论。

宿主全平台最终1213项/115.835s通过；初轮1213仅因新module缺code-map条目失败，
原日志保留，补文档后完整重跑。canary改为safe getattr期间的旧fixture fingerprint
FAIL与Preview ABI/read-time撤权的旧负控独立保留；不能拼到真实gen45 PASS里。

固件、ROM、原程序MPY及含其ZIP不入库，仅保留原始指纹/成员表；API/浏览器JSON
若含base64程序bytes则明确转为redacted metadata，保留original/archive不同SHA，
不伪称原字节。完整测试源码、官方compiler commit/SHA/精确argv可重编对应MPY。
本块archive本身不重建候选固件，须结合上方构建来源。微小固定canary bytecode是
可审计的产品协议fixture，源码、编译recipe与固定fingerprint在实现中。

当前功能验收只覆盖这组CoreS3固件/runtime/PIR与Web路径；其它主机/固件需各自真实canary
及功能验证。native/IRQ/thread仍interrupt-only，reset/重连/restore不自动恢复旧能力；
SSE、AIFlow调用侧、保存开机、更多Unit及FlashLight route历史仍按Backlog推进。

最终审查另修两项边界。OpenAPI3.1的旧nullable与capacity公开worker投影已按原始
响应修正，766份JSON响应及48项类型控制通过；原schema与harness失败不覆盖，见
[契约复核](contracts/index.json)。应用破坏os.chdir/sys.print_exception可使受信wrapper
只发LOAD而逃出收尾；在同步确认raw prompt后，缺少DONE/ERROR也必须撤销MPY能力，
普通运行中查询与尚未LOAD的部署取消不因此撤权。原宿主复现与修后28+155项窄测见
[恢复门禁复核](host-followup/index.json)，真实gen46会话证据与gen45基线分开归档。
gen45的源码/服务receipt保持原字节；不能把最终修复反写成gen45已执行的代码。
最终全平台1218项/108.913s通过，追加轮次和资源终态见[最终验收收据](final-acceptance.json)。
完整离线校验：`python3 -B docs/evidence/2026-10-27-public-main-mpy/verify.py`，
只核归档与已有结果，不启动guest、不调用API、不授予硬件结论。

最终gen46独立复验stock与candidate两会话9次执行（5次MPY），正常重复Run、依赖更新、
应用异常、PIR及loop中断回同owner源码通过；两ZIP共58成员核验，先导出再stop，
历史帧SHA保持且PID/Flash/lease释放。见[最终运行复验](restoration-followup/index.json)。
该轮未重跑Web；异常污染运行环境的额外guest场景被自动安全审查拦截（可能的网络安全风险），
仅保留宿主负控证据，不作为guest PASS。gen45的六阶段Web与八个optional空体分类不变。

工作块提交5be2687a后fetch/merge origin/main@f2061759，已同步且无代码变化；
未push、未新跑guest或重载服务。同步/隐私复核及归档器原失败见[收尾记录](integration/index.json)。

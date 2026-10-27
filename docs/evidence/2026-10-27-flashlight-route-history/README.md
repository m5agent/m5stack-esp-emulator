# FlashLight 路由历史：分层证据

日期：2026-10-27。UNIT-HOST-38 限定路由历史验收完成；UNIT-01 整体继续。

`0046` 修复 UNIT-HOST-38：原模型仅在 getter 看到 unsupported route 时隐藏输出，
恢复 GPIO 后可再次暴露旧 Torch/Flash 资格。现在真实 GPIO OUT_SEL 提交后通知
同 SoC layout、同 EN pin 的 FlashLight，立即撤销内部 known/active/qualified/ready，
取消 reset/settle/timeout，清除旧 low 起点与期限；返回 GPIO 也不恢复旧资格。
这一通知不制造 pad edge、脉冲或 decoded 计数，不合成 LEDC/RMT/PWM 波形。

本块保守恢复策略是重新观察受支持 GPIO 的真实下降沿和完整 >500us 低区间，
再由实际程序控制。它不是芯片要求额外下降沿的声明；冷初始化无边沿的
UNIT-HOST-37 仍 OPEN。官方 TOFF 要求连续低，后续须补有效 pad 来源和所有
writer 的观察生命周期；只在 route 返回时读一次低值不足以证明连续低。
只读研究见 [后续依据](followup-37/assessment.md.txt)。

| 层级 | 范围与结果 | 入口 |
| --- | --- | --- |
| 永久测试与独立 C | 真实补丁重放/route MMIO commit；26 cases、357 checks；旧模型152项失败，候选0。时钟与外围存储 shim 不作 guest 证明 | [controller](controller/index.json) |
| 独立冷构建 | 固定12 patch、106 source；新 QEMU source/object build，43份依赖缓存及3下载包复用，未复用 QEMU objects | [build](build/index.json) |
| 平台回归 | 完整1220项、窄检查24项通过；源码捕获发生执行后，启动前后绑定另有独立收据 | [testing](testing/index.json) |
| 真实8787 API | CoreS3/AtomS3R/StickS3/StopWatch 各 Torch/Flash，8 lane各21次同VM执行，共168次；5类路由历史/旧低区间负控及新复位恢复 | [live](live/index.json) |
| 真实 mounted Web | CoreS3 同VM的14次执行/13状态阶段，实际组件灯材质/unknown撤回及新复位恢复通过 | [live](live/index.json) |
| 完整共享控制器回归 | 独立一轮67例、274检查，无重试；66 PASS，Core2 IMU FAIL，绝不以单例或其它轮拼接全量PASS | [testing](testing/index.json) |

新 Xtensa runtime SHA256：
`3f161756cdb31dec3812393b730e1ae670733e7354d7b57fddbbd0149b8645e1`。
QEMU base commit：`40edccac415693c5130f91c01d84176ae6008566`。
完整 patch stack 临时 index 逆序返回 HEAD tree
`ddde372fbcc1b22e99f24372e14dee425be3193b`，正序回到 postimage tree
`ce1b71562a4f87bcdd0344cc8dd8304b661fff6f`；实际 index、源文件和旧 runtime 未改。
依赖 `.pc` 可保留历史缓存前缀，缓存复用不冒称全依赖冷构建。
完整矩阵中的新 Xtensa 62例与未重建 C6 的5例分别绑定 runtime；C6 不继承新
Xtensa 源码来源。确切固件 SHA、profile、工具、argv 和输入逐 lane/case 记录。

Core2 IMU 本轮 guest exit0、串口最终 accel=0.25,-0.50,0.75、gyro=10,-20,30，
画面 marker 仍为黑，保持 UNIT-HOST-21 OPEN。PaperColor RGB 实际通过，
`summary.command` 已保留 profile runner/参数，checker 使用独立变量；
UNIT-HOST-22 的 old FAIL/new PASS 宿主负控与原历史错误分开保存。
outer build/matrix argv 明确为执行后 root attestation，不当作事前独立 exec trace。
启动时 composed Flash SHA 与停止后的可写 Flash SHA 分开；guest 可修改后者，
不能拿 postrun mutable image 指纹替代 launch composition 指纹。

窄测试 r1 因冻结 builtin sys 不允许新属性而失败，未执行 route；r2 没有建立
旧 active 前置，原 FAIL 保留。改用真实可变 sys.modules 保存跨 Run nonce，
并让 sleep_ms 给虚拟 timer 调度机会后，独立 Torch/Flash 窄测试通过；没有放宽
模型时序窗口或 decoded 准入。失败会话的 cleanup 另行核实，不回写原报告。
原 UTF-8 serial verifier 失败与后续 verifier 收据也保留；raw serial/ZIP 从未转码。

Web共1062条browser响应，386个200/676个304；7个optional200空frame capture保持
PARTIAL，不当PNG实体或完整贴图传输证明。mandatory直接非空frame与mounted状态
独立通过。13个会话的原cleanup报告为12 PASS/1 UNCONFIRMED，失败r1由独立
finalization证明已停止并释放资源，不回写原报告，也不授予其功能帧PASS。
各会话均先ZIP再stop，历史末帧按各自ZIP/最后live帧核验。最终独立只读检查
确认gen47源码83份/runtime相同、旧322包文件/408source record原字节保留，
active/lease均0，见[服务起止收据](service/index.json)。
该gen47收据在元数据更新前捕获。随后只更新runtime-profiles的blocker/route policy
及新增限定route_history_validation，旧guest/program验证记录逐字节保留；17项窄测
通过后在idle重载gen48，沿用同3f1617 runtime。实际API读回与83份当前源码一致、
active/lease0，见[元数据收尾](metadata/index.json)。gen48没有新guest执行，不替代
gen47真实功能/Web证据；最终文档48项和五validator通过，见[检查收据](acceptance/index.json)。

所有正向功能测试使用可见 Device Service 会话、实际 UART REPL 和同一个 guest，
首次初始化后不重刷固件。真实 guest `machine.mem32` 修改 OUT_SEL；serial、
QOM 与 frame 分别取证，不把分次采样说成原子快照。固件、ROM、执行文件、
功能会话原 ZIP/raw serial 仅留指纹；回归安全文本/串口/PNG 保留原字节，变换副本明确分类和双 SHA。
ASCII marker 按原始 byte offset/window 验证，内存中的字符映射不是原件转码。

动态 S1、完整 PWM/OEN/IOMUX、hard-reset 观察、冷 route、任意固件、其它 Unit、
硬件光电/热/电气等价性均不由本块关闭。AIFlow 消费者、SSE、保存开机和更多
主机/固件的 main.mpy 继续按项目 Backlog 推进。

离线校验：`python3 -B docs/evidence/2026-10-27-flashlight-route-history/verify.py`。
它校验全部归档指纹、固定的controller/build/testing/live四个子门禁、真实live摘要
和服务终态，不启动guest或联系API。预备版曾允许空child列表，独立离线负控
复现后已修正；旧误PASS与新版拒绝都见[门禁复核](review/acceptance-gate-fixed-r1/receipt.json)。

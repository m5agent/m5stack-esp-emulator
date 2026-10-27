# FlashLight 路由历史：分层证据

日期：2026-10-27。API 已验，mounted Web 与最终归档收尾中；UNIT-01 整体继续。

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
| 平台回归 | 完整1220项、窄检查24项通过；源码捕获发生执行后，启动前后绑定另有独立收据 | testing/index.json（收尾中） |
| 真实8787 API | CoreS3/AtomS3R/StickS3/StopWatch 各 Torch/Flash，8 lane各21次同VM执行，共168次；5类路由历史/旧低区间负控及新复位恢复 | live/index.json（收尾中） |
| 真实 mounted Web | CoreS3 同VM的13阶段验证收尾中；以实际组件灯材质/unknown状态为准 | live/index.json（收尾中） |
| 完整共享控制器回归 | 独立一轮67例、274检查，无重试；66 PASS，Core2 IMU FAIL，绝不以单例或其它轮拼接全量PASS | testing/index.json（收尾中） |

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

所有正向功能测试使用可见 Device Service 会话、实际 UART REPL 和同一个 guest，
首次初始化后不重刷固件。真实 guest `machine.mem32` 修改 OUT_SEL；serial、
QOM 与 frame 分别取证，不把分次采样说成原子快照。固件、ROM、执行文件、
原 ZIP、raw serial 仅留指纹；安全文本/PNG 保留原字节，变换副本明确分类和双 SHA。
ASCII marker 按原始 byte offset/window 验证，内存中的字符映射不是原件转码。

动态 S1、完整 PWM/OEN/IOMUX、hard-reset 观察、冷 route、任意固件、其它 Unit、
硬件光电/热/电气等价性均不由本块关闭。AIFlow 消费者、SSE、保存开机和更多
主机/固件的 main.mpy 继续按项目 Backlog 推进。

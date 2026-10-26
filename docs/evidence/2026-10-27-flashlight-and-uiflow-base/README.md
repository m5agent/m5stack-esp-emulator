# FlashLight 与显式 UIFlow base：分层证据

日期：2026-10-27。本块验收完成；UNIT-01 整体继续。

实时程序复用已启动 UIFlow guest 的 UART REPL。同一会话反复 Run 不重刷固件；
`firmware/uiflow`负责最初的基础镜像和文件系统准备。普通源码运行、字节码依赖、
二进制入口与固件loader能力分别验收。

| 层级 | 已验证范围 | 原始证据 |
| --- | --- | --- |
| API 1.45 | 显式manifest base/normalized SHA pin、实际镜像/分区/兼容性、安全能力/PSRAM沿传、CAS来源冲突拒绝；仅顶层created_at非语义差异可重试；包容量默认256、显式1–4096，降额不删除历史 | [API索引](api/index.json)、[源码代际](api/source-lineage.json) |
| 固件loader诊断 | 固定CoreS3候选在gen40/850426的同VM：11源码阶段、MPY同bytes重跑/依赖更新、if-main/模块身份、异常/坏magic/Ctrl-C、PIR/UART/QOM/PNG；171HTTP、44 ZIP成员及清理独立核验 | [loader结果](loader/outcome-summary.json)、[独立审计](loader/live-r4-20261027/independent-audit.json) |
| FlashLight数字子集 | gen42、新7c898 runtime、四host各Flash/Torch，共8独立会话60Run；360 ZIP成员、原驱动bytes、nonce/实际边沿/选定pad像素、历史末帧/Flash/PID/lease均核验。15个脉冲程序qualified、17个unknown；其余为reset/稳态Torch等 | [八会话选择与原始SHA](units/index.json) |
| CoreS3默认Web | 五阶段亮→灭→亮→未知撤灯→恢复亮，真实mounted FixedWhiteLed、独立QOM/serial/frame、25张图片；72直接GET与318浏览器响应 | [最终r3](web/artifacts/live-cores3-torch-r3/verification.json)、[捕获限制](web/browser-capture-assessment.json) |
| 构建/回归 | 11补丁独立正反重放、106 Xtensa源码、18 C测试/两完整C syntax/16 sanitizer；新完整矩阵单整轮67/67（908.997s、无重试），另targeted独立PASS；平台1162 tests/123.796s/OK | [构建](runtime-build/index.json)、[矩阵](regression/index.json)、[平台与配额日志](api/index.json) |

新Xtensa二进制SHA为`7c898e8d456f2d85bf75481f8d90b4ef493dcef00a290053c4b804c387f2018e`。
候选原始CoreS3固件SHA为`7ce5ca0744a27508913c4dd69dd06f30454fb27c54a920faf486d3350cf2267b`；
实际loader派生为`45a02c4c758eee9f18ab2195c3837c974f6aae8b882a9df295b658c1e07fdae9`。
公共`mpy_entrypoint/main_mpy`仍为false；本块没有把诊断探针改成产品入口。

FlashLight仅模拟yellow EN的真实GPIO边沿与QEMU虚拟定时器。推荐750..10000ns
是本模型受验窗口，超出时unknown，不代表真实芯片必然失效。最后上升沿后500us
锁存、首次上升沿起算220/1300ms是明确模型策略，不是硅片测量。S1为创建fixture，
全部initial后冻结；Torch无Flash deadline、百分比，网页持续亮度仅定性显示。
没有动态S1、EN PWM、光度/光谱、电流、电源、热、保护电路或bit-exact结论。

原UIFlow驱动`brightness*time`与datasheet编码不符。已受验的100%/1300ms请求
实际2脉冲→90%/220ms；60%/1300ms实际10脉冲→90%/1300ms（仅波形qualified时）。
raw9/raw16及StickS3某原长闪保持unknown，不能用C中全16码测试替代guest准入。
官方原图、datasheet、原驱动和反馈见[前块研究](../2026-10-27-binary-checkpoint-admission/research/index.json)。

原失败各自保留：loader r1准入409、r2探针sys属性假设、r3非语义时间戳冲突；
FlashLight冷route无边沿unknown、256包配额429；Web r1错误读取正常304、r2截图DOM
脱离。最终各层独立重跑，不拼接失败轮。冷route需进一步观测，当前用真实EN
高→低及>500us shutdown验证恢复；没有constructor-only已知off结论。
最终独审另复现route历史缺口：Torch已知亮→unsupported route时撤灯→恢复GPIO
且无新边沿/reset时，旧known/active可能恢复；Flash在旧deadline前也有窗口。
这是实际C片段的宿主诊断，不是guest或硬件PASS。当前仅准入持续受验GPIO路径，
不承诺切换LEDC/RMT后资格持续失效；UNIT-HOST-38保持OPEN，
[最小C复现](acceptance/route-history/index.json)保留源码/命令/原始输出指纹。

Web r3的193条304明确无实体；另4个可选HTTP200 body观察为0 bytes，标为
`PARTIAL`捕获，不当作PNG或“实体不存在”。五阶段强制frame均来自独立非空GET，
mounted灯证据不依赖这些空体。display响应SHA是元数据，不是完整纹理传输追踪。
最终Web在自身始终为最新3D预览、无其它可见会话分配的窗口完成；并发3D slot
生命周期未由此关闭。硬件验证与AIFlow调用侧/SSE均NOT RUN。

矩阵的62项Xtensa绑定新源码/ROM；5项C6绑定既有RISC-V executable/ROM哈希，
本机缺C6 source receipt。papercolor-rgb原summary命令被后续checker覆盖；保留原文
与明确标注的重建命令，没有伪造捕获argv。旧Core2 IMU偶发问题不因单轮通过关闭。

各子目录索引保存原始/归档双SHA，并提供离线校验器。固件、ROM、ELF、原MPY
及含固件ZIP不入库，只保留指纹；原Markdown快照用`.md.txt`。工作流见
[实施计划](../../plans/2026-10-27-flashlight-and-uploaded-uiflow-base.md)。


最终收尾的文档/Unit测试、生成器、离线证据校验、凭据/ZIP检查和闲置资源检查见
[验收收据](acceptance/verification.json)、[隐私检查](acceptance/privacy.json)和
[服务清理](acceptance/idle-service.json)。

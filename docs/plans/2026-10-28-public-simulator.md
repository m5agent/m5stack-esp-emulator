# 公众模拟器与 GitHub Pages 准备

日期：2026-10-28。目标是可分享、能看懂、能操作的设备工作台；部署前先验收。

## 范围与验收

- 默认页面以设备与屏幕为中心，固件为主操作；设备选择、Unit 搜索、状态、串口分层呈现。长技术说明保留在可访问的折叠面板。
- 1440 / 1024 / 768 / 390 宽度可操作，无横向溢出；真实浏览器检查加载、空态、错误、切换和长 Unit 内容。
- 最新公开模型以固定 commit、文件白名单和 hash 导入。新增视觉模型不自动取得固件、协议或主机准入。
- 项目路径部署及 `?device=…&firmware=…` 分享不丢参数；未知设备不能静默替换。浏览器下载固件需处理 HTTPS/CORS、大小上限、取消、SHA256 及失败恢复。
- GitHub Pages 托管静态站及 WASM。现有 native QEMU / Linux 配置没有 browser-WASM 功能等价证据；新增浏览器 backend 与可选 HTTPS Device Service 必须分别准入。站点不代理任意 URL 抓取，不嵌入控制 token。
- 连接服务后经现有 firmware intake 创建可见 session；画面、输入、串口和 Unit 均绑定本 session。停止前请求 evidence，`purge=0` 保留历史。不能用模型渲染替代固件 PASS。
- 构建输出仅显式白名单；不包含 `.work`、token、固件、原始执行证据。可选 browser export 只附带经过来源/hash/许可审阅的 S3 ROM 与源码构建 WASM；它们不进入源码 Git。准备手动构建工作流，实际发布留至页面验收及用户部署决定。

## 执行安排

主 agent 负责公众工作台、Device Service 桥接、浏览器验收与汇总。并行分工为 Unit/会话页面信息层级、固定版本模型导入、Pages 构建与 URL/固件下载契约。所有修改在独立 worktree `codex/public-simulator-workbench`；主 checkout 的文档与 LAN 预览修改保留。

## 约束

不访问、停止或重启用户的 8787。功能验证使用独立端口、state 和 token。原始截图、ZIP、命令输出写入 ignored `.work` 或工作记录，源码仅放精简结论与重现命令。

## GitHub Pages 托管准备

`.github/workflows/public-site.yml` 仅接受手动触发，`publish` 默认为 `false`；默认构建源码固定的 WASM、静态站及普通 preview artifact。只有在 `main` 上明确指定 `publish=true`，才生成真正的 Pages artifact 并进入 `github-pages` 部署环境；发布权限仅授予部署 job，并发组避免重叠发布，运行中的构建不被新请求取消。工作流不启用 Pages，也不修改仓库的 Pages 来源。

2026-10-28 的只读审计显示，上游与 fork 均未启用 Pages；当前账号可以管理 fork，上游设置需仓库管理员配合。可管理目标为 `https://yuyun2000.github.io/m5stack-esp-emulator/`，构建前缀为 `/m5stack-esp-emulator/`。若选上游，对应地址为 `https://m5agent.github.io/m5stack-esp-emulator/`。

发布前先完成页面与功能验收、将审阅后的修改整合到所选仓库的 `main`，再由用户确认最终发布。得到确认后，管理员将 Pages 来源设为 GitHub Actions，并在 `main` 手动运行 `publish=true`，最后核查公开 URL、分享直开、固件下载及 WASM/模型加载。本地项目子路径导出与真实浏览器检查已有证据；GitHub Linux Actions 构建和公开部署尚未实际验证。

## 进度

- 已核查运行架构、当前页面和来源 pin；模型在独立 worktree 更新，模块闭合、同步器检查和独立完整浏览器模型回归已通过，默认配置边界见证据页。
- Unit / sessions 信息层级改造、公众首页四档布局、设备/Unit 搜索与失败契约已验证；Pages 子路径导出、URL 下载/取消/SHA、独立 Worker 后端已实现。
- 用户要求先研究 esp-online-tester 的全浏览器架构；已从固定源码独立重建 browser backend，并在 Chromium 跑通 PaperS3 / StopWatch 官方固件、真实帧、输入和暂停/停止。首页分享直开、实际DOM触摸与四档布局均已通过。CoreS3 plain受控原生示例也已同guest完成输入/帧/evidence/停止；创建收据丢失后以同key/body恢复同guest并安全停止已完成真实回归；独立审查进一步补齐有界停止和明确lease释放。更多stock/unified路径作为后续扩展，不作为两profile browser部署硬门禁。证据和不可继承边界见[纯浏览器调研](../browser-runtime-feasibility.md)。
- 尚未部署。browser backend 的限定结果不转授已有 native 板级、任意固件或完整 Unit 协议；部署前继续完成本地页面与证据验收。

## QEMU 到 WASM：按用户澄清恢复探索

用户先要求工作量较大则暂缓，随后明确澄清 Rust 项目只用于参考，并要求继续探索自己的 C/QEMU 到 WASM。当前恢复最小构建实验：保留固定 QEMU 9.2.2 与完整板级/Unit 补丁，回移官方基础 WASM/TCI 支持，用隔离 Emscripten 3.1.50 及依赖实测编译边界。此前的“两款 Rust 内核演示”保留为研究原型，不作为最终复用既有模拟能力的替代交付。

本轮已补齐定制QEMU 9.2.2的Emscripten构建、TCI/helper、GLib/libffi和
线程/协程支持；参考官方QEMU 10.1的基础WASM/TCI路线完成回移。宿主I/O、
实际guest停止重开及本项目Xtensa固件/板级验证仍需继续，不能从构建结果承诺功能等价。

源码回移与完整构建已实际通过；完整WASM在Chromium取得版本、板型枚举和
无固件QMP请求响应，256MiB初始配置CLI退出码为0。初版无固件quit没有退出
回调；显式process-exit修正后已退出码0及四Worker自然关闭，具体来源、补丁与证据见
[C/QEMU实验](../qemu-wasm-port-research.md)。后续再跑CoreS3真实UIFlow2/LVGL
显示、输入和一个Unit数据面，测量性能与停止重开。编译成功不授固件通过；
未验证设备不得扩大准入。SDK、依赖与原始证据留在ignored目录，不修改全局
环境或用户的8787。当前不发布两款原型方案，最终公开范围待这一实验结果和用户审阅。

## CoreS3 实际固件阶段

用户要求继续推进并持续同步main。本阶段先合并`origin/main@f3bab9c0`，后续又合并
`805925d8`（Core2 high-priority IRQ与classic RMT）；只处理开发worktree，主目录的
未提交文档/LAN预览和用户测试会话原样保留。后续仍在每个交付点fetch并检查
main新增内容，先整合再验证，不把旧runtime证据称为最新主线结果。

WASM源码在新目录重建，保留原30层补丁并明确补入0064；最新805925d8的
0065/0066因可选诊断和source-list上下文差异，通过0011在新目录移入相同新增代码，
不称33层原样apply。冻结的SDK与真实依赖复用，旧实验源与原产物保留。独立分工为最新源/构建、浏览器
QMP/UART/文件传输适配，以及官方UIFlow2/LVGL+PIR最小fixture。浏览器负责CPU
执行，服务只保留session、传输和证据，不允许拿native输出补浏览器缺证。

本阶段验收须在独立Device Service端口、state、token和同一可见session内
完成：固定固件SHA的ROM/应用串口、LVGL帧、触摸计数、Unit独立输入和guest
读回；记录冷启动、帧采集、线性内存与停止重开。停止前取evidence ZIP，
`purge=0`保留历史，核实际浏览器Workers和服务拥有的wrapper进程退出。
若出现TCI、总线或浏览器能力缺口，保留失败轮并按真实边界修复；不绕过
SoC/controller或关闭guest保护来制造通过。本阶段不发布站点或切换用户服务。

已完成本阶段限定CoreS3 fixture：同一固定Flash在独立native对照与浏览器CPU
分别执行；浏览器两场新会话已取得LVGL、真实触摸/PIR、两ZIP、历史与
自然退出证据，详见[阶段证据](../evidence/2026-10-28-qemu-wasm-cores3/README.md)。
主CPU jump的宿主栈恢复已通过独立Fiber/SjLj最小复现与真实64KiB Flash映射SP观察；
0007大栈仅为历史对照。默认wallclock的r11因LVGL queue full保留PARTIAL；
single/icount两组对照也未关闭缺口。显式vm-div8保留两个guest CPU和原WDT，
虚拟时间与WDT到期相对墙钟一起变慢，离线fixture的完整RGB/触摸/PIR/停止重开
已通过。新主线补丁须核源码兼容并绑定最终runtime再回归；随后进入公众页面的
资源/输入/帧/串口/停止接入及部署准入，不扩大设备/固件范围。


最终源码候选已包含805925d8的两项context port，并通过完整独立源码重放。
r15首场完整RGB/输入/PIR/暂停恢复/ZIP/自然退出通过，但第二场READY后QMP
请求超时，整轮FAIL保留。`wait_qmp`把握手超时笼统报为socket未出现，不能
据此声称路径被删除；已有观察也不足以证明guest停止。70秒无固件空闲控制
能恢复，普通EAGAIN不关闭watch。继续用独立诊断候选定位主循环/锁、screendump
或stdio watch，关闭后再做最终两场回归，不以先前r14替代最新源码验收。


r16诊断负控进一步核准40秒观察窗内socket始终存在、guest心跳继续推进，默认
main-loop也持续运行；QMP专用context从约7秒起不再访问fd0 poll，首screendump
未入monitor。具体GLib/watch内部机制尚未定。下一项0012明确只对Emscripten的
stdio QMP改用既有default main-loop context；原生及其它chardev保留原分支，
双guest CPU/TCI/板级不变。该配置不offered OOB，当前adapter未协商OOB，
in-band命令保持。须用无诊断最终产物重新完成双场功能与停止重开后再验收。


最终0012无额外共享诊断的产物已完成两场完整58检查，含每场两次触摸与PIR
完整转换、两ZIP、历史/Flash/lease与各5Worker自然退出。另三次cold session
完成完整boot RGB、Unit初值/QOM、ZIP和清理。独立5项nofirmware（20重连与
20真实EPIPE/迟回复隔离）及70秒无QMP空闲均通过。上述限定主循环宿主配置
关闭本轮控制通道验收，不声称已定底层GLib根因或完整长期稳定性；后续继续
公众浏览器资源/输入/串口/Unit及停止接入、默认时钟调度、持久化和Pages准入。

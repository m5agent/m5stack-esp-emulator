# Uniform LED live-browser r3 — PASS with visual framing limits

本分区保留独立 r3 整批原始记录：真实 Device Service → 同一 guest UART REPL
替换程序 → I2C/RMT 控制器 → QOM → 默认 UnitPanel → 实际 Led 组件/材质与浏览器
渲染。硬件验证 **NOT RUN**。r2 仍在相邻 `live-browser/`，没有替换或拼接其数据。

服务为本机端口 8787，PID 75112，worker generation 31；guest runtime SHA256 为
`b8de32a39be06162ae8ce8529b218370038936059dba067b9a7109a470e067d2`。
固件 SHA256 为
`0ede40601c1e37b7ba32c87a3ca55e4da7a448f6cf52957f005763bc7c7c78e8`。

| 组 | Session | Guest PID | 范围 |
| --- | --- | ---: | --- |
| i2c-hub | `2385a7553db04dc0b7aa495629ad3d87` | 81028 | 被动 HUB + Encoder(2灯) + 8Encoder(9灯)，真实 I2C 扫描精确为 0x40/0x41 |
| rmt-rgb | `26db63775ee748a596161bf5b6872e03` | 81278 | 独立直连 RGB(3灯)，原 RGBUnit/SK6812 RMT 路径 |

RGB 没有接入 I2C HUB。每组在同一 VM、PID、固件和 VM nonce 下连续运行四个
source revision：A 为每种 Unit 各自统一颜色，B 为合法非统一颜色，C 为另一组
统一颜色，D 为全零。各阶段核对新鲜 UART、execution/revision/source 身份、真实
设备帧和模型屏幕像素。A/C/D 的 2+9+3 个 Led 组件、材质发光、glow、brightness、
`runtimeKnown` 与 Encoder 前壳 diffusion 参数全部通过；默认 bindings 为 `{}`。
B 无灯位映射时撤下旧色、标记 unknown，同时保留电气顺序的读回数组。

两组各有一次明确的 browser-only `/units` HTTP 503 故障窗口。顶层报告全集记录
HUB 14 次、RGB 12 次，合计 26 次。UnitPanel 自然显示“灯光状态未知，模型颜色已撤下”，所有 Led 进入
unknown；随后恢复到同一 C 程序。该负控只改变浏览器请求结果，不伪造 guest
属性。独立真实 HTTP/QOM 和新鲜 UART 仍证明 guest 在运行。整批 unit-input POST、
物理事件回声、页面异常和资源加载异常均为零。

## 截图与视觉边界

`run/<group>/A..D-browser.png` 和 `A..D-iso-browser.png` 是完整实际 3D stage 的
locator 截图；`*-front-render.png`/`*-iso-render.png` 来自真实 renderer 输出。
截图前等待 render，检查整个 assembly 及每个 module 的 Box3 八角均在视口中，
并检查 renderer PNG 非空。另存每个 leaf 面板与整页总览。共 75 张 PNG 均可解码。
这修复了 r2 编辑器滚动后页面 clip 裁掉 3D 顶区的问题。

**front/iso 两视图不意味着全部 14 灯在同一图中可辨，也不证明无遮挡。** Box3
在视口内只能证明投影边界，不会排除模型之间的自然遮挡。HUB front 视图中的
8Encoder 沿视线被遮挡；iso 能清楚看到 8Encoder 的九灯，但 Encoder 位于后侧。
实际目视 A/C front/iso 未取得 Encoder 两灯 diffusion 的清晰独立颜色变化，
因此 Encoder 光学可读性仍未验收。此处组件和材质断言的 PASS 不扩大为该结论。
后续视觉验收应补各 Unit 的局部相机/closeup，并对 A/C、B unknown、D off 分别
取图；本轮不重跑或拼接其他 attempt。

已实际目视：RGB A 粉红三灯、C 青绿三灯清楚，B 撤色、D 全灭；HUB A/C iso
的 8Encoder 彩灯、B/D iso 无彩色发光；三个 503 面板均有明确 unknown 提示。
unknown 的撤色不代表真实电气 off。没有电气索引到物理灯位、转轴角度/方向、
突发时序或真实光学/机械行为结论。

## 程序能力与证据完整性

真实 GET `/devices` 与 `/devices/cores3` 验证：`main.py` 入口，bytecode-only
`.mpy` 依赖，`.mpy` 入口与 native MPY 均不支持，fresh exec globals，
interrupt-only cleanup。各组使用有效官方 `.mpy` 字节请求 `main.mpy` 入口，均为
HTTP 409 `unsupported_program_entrypoint`；原 execution 及新鲜 UART 继续，
最终 ZIP 各只有 A-D 四个 execution。这个边界不影响 `main.py` 在同一固件中
实时替换运行；不能把它描述为每次重新刷入固件。

各组先请求 evidence ZIP，再 stop `purge=0`。独立复查确认两个 PID 已退出、
mutable Flash 已释放、历史和末帧保留，服务 active sessions/leases 均为零。
每 ZIP 23 个成员、四个 execution、六个新鲜 UART 窗口；逐成员 size/SHA256、
最终 `units/state.json` 各 leaf 的 id、available、errors、guest-qom 来源及 D
全零状态、最后设备帧均严格核对。ZIP 内没有 Flash 或 ROM 二进制。

通用 `qom/snapshot.json` 受 500-node 上限截断，不作为完整 Unit raw QOM 证据。
每阶段独立 LED raw QOM、I2C 地址/transactions 或 RMT frame 计数保存在各组
`report.json` 的 `phases[].capture.qom.raw`。最终 ZIP leaf 状态另行核对。

| 原始文件 | SHA256 |
| --- | --- |
| 主报告 | `416ad34a113a5e4ae69d051af4460df5d647146cc896c6f5095f960034fe1a20` |
| HUB evidence ZIP | `4cab9a1e11ad15256f2de6996571f486ea87ac56fc2ecbd50120f8247d76343b` |
| RGB evidence ZIP | `2bba357b7bfda9db44df539b1fceba9f545a08f548ebd50417afa87bf2453295` |
| 运行 probe | `e1308a230b6aa0d335ba010f887994c12de5a202310ac038d7f35073d73e164c` |

`run/` 保留全部本轮原始输出和独立 `freeze-and-cleanup-check.json`；`sources/`
保留全部 21 份运行时冻结文件（包括 `device-shell-factory.js`）。`verification/`
保留离线 plan、Node/Python AST 预检、teardown throw 必须失败的负控与独立核查
脚本。`transport-fault-totals.json` 说明最终 26 次故障与组报告中的前缀计数
12/10 的区别；独立 freeze 收据中的同名计数沿用该前缀，不是最终总数。
guest `.py` 和冻结代码只追加 `.txt`，不改变原字节。120 个原文件的
original → archived、size、SHA256 索引见 `file-manifest.json`；原始报告中的
`.work` 路径是运行时出处，归档位置以索引为准。

复现前使用匹配代码/runtime 的本地服务，并填入当前 service PID、generation
和全新输出目录；不要复用本轮目录。

```bash
node platform/tests/test_live_uniform_led_service_browser.mjs --plan
node platform/tests/test_live_uniform_led_service_browser.mjs --check-sources
node platform/tests/test_live_uniform_led_service_browser.mjs --check-cleanup
M5_UNIT_SERVICE_E2E=1 \
M5_EXPECTED_RUNTIME_SHA256=b8de32a39be06162ae8ce8529b218370038936059dba067b9a7109a470e067d2 \
M5_EXPECTED_SERVICE_PID=<current-service-pid> \
M5_EXPECTED_WORKER_GENERATION=<current-generation> \
M5_UNIFORM_LED_LIVE_BROWSER_OUT=<new-absolute-directory> \
/opt/homebrew/bin/node platform/tests/test_live_uniform_led_service_browser.mjs
```

# Uniform LED live-browser r2 — DATA-PLANE-PASS

此分区保留 r2 的完整原始数据面 PASS；阶段 `*-browser.png` 因编辑器滚动后
使用 viewport 相对的 boundingBox 作页面 clip，裁掉卡片顶部 3D 区域。它们不能
作为完整外壳视觉展示。该截图限制不改变实际 14 个 Led 对象的材质/发光、QOM、
UART、模型屏幕像素与 source/execution 身份断言。后续完整可见截图应来自独立
整批 attempt，不拼接替换 r2 文件。

来源为本机端口 8787 Device Service，generation 31，runtime
`b8de32a39be06162ae8ce8529b218370038936059dba067b9a7109a470e067d2`。
这是虚拟设备验证，硬件验证 NOT RUN。源文件冻结位于 `sources/`，字节校验索引
为 `file-manifest.json`；原 guest `.py` 只追加 `.txt` 后缀归档，字节不变。

| 组 | Session | Guest PID | 批次范围 |
| --- | --- | ---: | --- |
| i2c-hub | `69756b14254e4bc1b9a045308e4af85e` | 78991 | 被动 HUB + Encoder(2灯) + 8Encoder(9灯)，真实扫描地址 0x40/0x41 |
| rmt-rgb | `882bfee3fe1c4476ab0beeb7923ad805` | 79128 | 直连 RGB(3灯)，原驱动 RMT 路径；没有将 RGB 并联到 I2C HUB |

每组使用同一 VM/PID/firmware 连续运行四个 source：A 为各型号统一颜色，B 为
合法非统一颜色，C 为不同统一颜色，D 为全灭。A/C/D 的所有目标均 known=true；
B 无 binding 时所有目标 known=false、旧材质发光清零，并保留原电气顺序数组。
两个独立 browser-only HTTP 503 负控使 UnitPanel 自然进入 unavailable，随后
同程序恢复；该负控不伪造 guest 属性，不代表真实 guest 控制器不可用。

`r2/<group>/A..D-frame.png` 为真实设备帧，四阶段实际程序 ID/修订 ID 与
浏览器模型屏幕像素分别核对。`A..D-browser.png` 有上述裁切限制；
`C-browser-transport-unknown.png` 是完整页面补充图，包含其他历史卡片。
主报告还保留全部 Led brightness、emissive、glow、runtimeKnown 与面板提示。
无物理灯位索引映射、计数角度、转轴方向、突发时序或光学真实性结论。

真实 GET `/devices` 与 `/devices/cores3` 验证入口仅 `main.py`，MPY 依赖为
bytecode-only，MPY 入口和 native MPY 均为 false。两个有效官方编译 `.mpy`
入口负控均收到 HTTP 409；各组最终 ZIP 只含四个 execution，旧程序的新鲜 UART
继续增长。所有 runtime readback 均没有 unit-input POST 或物理事件回声。

每组先请求 evidence ZIP，再 stop `purge=0`。两个 PID 已退出，Flash 已释放，
历史与末帧保留；见 `stopped.json` 和 `freeze-and-cleanup-check.json`。

通用 `qom/snapshot.json` 受 500-node 上限截断，不构成完整 Unit raw QOM 证据。
每阶段独立 LED raw QOM、I2C 地址/transactions 或 RMT frame 计数保存在各组
`report.json` 的 `phases[].capture.qom.raw`。ZIP 单独严格验证最终
`units/state.json` 中每个 leaf 的 id、available=true、errors={}、source=guest-qom
及 D 阶段全零数组。每个 ZIP 23 成员、四 execution、六个新鲜 UART 窗口均核验。

`attempts/r1/` 原样保留首轮 fixture 失败：legacy `/frame.png` 不包含要求的
preview execution headers；该会话已取 failure ZIP 并清理。r1 主报告 SHA256:
`3f9462f7625bac4399d315d238bc0bcfb85aeb96967a40b0f9660593b85ce020`。
r2 主报告 SHA256:
`bf6f9f5a9375987cd52626c7486137644c1725f84fc69062d155ef13d5181207`。
`verification/` 保留 offline plan、源码 AST 检查与 teardown throw 必须失败的
最小反例；r2 最终 source SHA256 为
`5794f0e6e5a383d18f4065dbf1ed53712fdc157c017141c35d97b91cbb5b4119`。

复现前先启动匹配代码与 runtime 的本地服务，替换 service PID、generation 和
全新输出目录；不要复用历史路径。归档 source 可查阅，运行应使用仓内最终脚本。

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

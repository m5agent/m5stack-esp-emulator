# 外壳接入浏览器验证

日期：2026-10-26（Asia/Shanghai）。证据类别：`browser-visual-integration`。
本目录只证明浏览器外壳、像素桥、输入意图和装配生命周期，不证明固件、
QEMU/esp-emu 数据面、电气行为、真机或全部 Unit 已完成功能仿真。

公开外壳源：<https://github.com/yuyun2000/m5stack-models>，固定提交
`48ab992f5ff63c1a91296051e1afcb5959877903`。未复制源工作树的脏文件或私有
research。导入许可与逐文件来源见
`platform/web/vendor/m5stack-models/THIRD_PARTY_NOTICES.md`、
`vendor-manifest.json`、`source-manifest.json` 和 `three-addon-manifest.json`。

验证命令：

```sh
node platform/tests/test_model_shell.mjs
python3 platform/tools/sync_visual_models.py --source /path/to/public/repo --check
```

浏览器探针自行启动只提供静态文件的本地 HTTP server；使用 Playwright 和
系统 Chrome，结束时关闭浏览器与 server。可通过
`PLAYWRIGHT_CHROMIUM_EXECUTABLE` 指定 Chrome，
`M5_MODEL_TEST_OUT` 指定输出目录。不启动或调用固件运行时。

[report.json](report.json) 记录 14 个主机和 27 个 Unit 的实际加载结果，覆盖：

- 每台主机均使用固定版本新外壳，所有 ESM 动态导入成功，无页面异常。
- RGB565、PNG 像素桥和各触摸屏的坐标；StamPLC 明确的原生 90° 面板变换。
- 已确认按钮的运行时 qcode、聚焦键盘按住/失焦释放。
- 27 个 Unit 的装配、组件路径、输入意图、输出不回圈、断开及资源清理。
- 每个 Unit 的实际组件 kind/meta 清单；HUB 三个真实子模块的递归装配、
  嵌套 CardKB 输入路径与父级断开时的递归清理。
- Fan 由显式 activity 输出启停图形动作，停止/断开释放活动状态；不向
  joint 的 RPM 状态写入推测值。该静态探针的 activity 是测试命令，
  真实 guest PWM 联动证据另见下列独立目录。
- 异步 Unit 加载竞争时销毁过期实例。
- Button 读回按下状态期间，用户仍能发送松手和下一次按压；机械行程
  从 0.35 mm 返回 0，延时读回不会变成输入事件。
- WebGL 创建失败后回退旧 DOM 外壳；回退仍可显示 PNG 帧和清理资源。

报告的 `integration_sha256` 固定本次集成源码和探针版本；`browser_version`
与 `captured_at` 固定浏览器版本和运行时点。后续集成代码变化需要相应重跑，
不能继承此处报告覆盖未测试的变化。

截图的蓝色 framebuffer 是浏览器像素桥测试输入；连接 Unit 的主机黑屏表示
未接固件，不能据此判定固件启动失败。风扇、编码器、传感器不会自动生成
转速或测量值。`SHA256SUMS` 可复核本次原始截图与报告。

尚未确认语义的 Nesso 控件不向运行时发送推测的按键；Tab5 电池卡扣不会
当作电源按钮。Tab5 Reset 使用单独复位意图。主机问题登记由
`docs/unit-integration-host-issues.md` 维护。

Unit 字段映射由 [unit-visual-mapping-report.json](unit-visual-mapping-report.json)
逐项记录，不把 27 个外壳都能加载写成全部双向功能完成。官方资料与尚未
绑定的机械/LED 位置解释见
[visual-bindings-and-component-gaps.md](../../unit-research/visual-bindings-and-component-gaps.md)。
面板 schema/并发/lifecycle 的独立 fixture 证据在
`../2026-10-26-unit-panel-browser/`；真实 Device Service/同 guest 的 Button、
Key RGB 与 Fan activity 证据分别在 `../2026-10-26-unit-service-browser/`、
`../2026-10-26-unit-key-service-browser/` 和
`../2026-10-26-unit-fan-service-browser/`，不能与本目录的 fixture 混作一类。

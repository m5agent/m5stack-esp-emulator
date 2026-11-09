# PaperDIY、PaperS3、初代 Cardputer、CoreMatrix 接入

外壳来源固定到 [m5stack-models de6cddc](https://github.com/yuyun2000/m5stack-models/tree/de6cddc065674ecb53bba29c7fe90d9ab4ee32f7)。
真实浏览器验证四款模型深链、尺寸和同一模型上的帧写入。CoreMatrix 核对 16 × 16 灰度字节到三处点位的映射。既有 Cardputer-ADV 也单独回归。模型检查本身只证明 WebGL 与宿主接口。

## PaperS3 浏览器原型对照

这是独立的 virtual-device validation。使用已有明确隔离的 esp32sim 参考原型，不改变生产 QEMU-WASM 准入。由固定源码重建的 WASM 和公开原厂 Factory v0.5 在静态工作台中执行。应用通过原控制器输出 540 × 960 帧，模型屏幕的两次实际指针点按都路由至 (116, 330)，应用图标区域发生变化。观察到实际 Worker 目标在停止后、关闭上下文之前消失。固件、ROM、WASM 和原始帧不纳入源码。首轮浏览器用例误将“浏览设备模型”当作禁用按钮，修正断言后复验。

- [浏览器摘要](papers3-browser-prototype-summary.json)
- [固定源码及本地构建步骤](../../../platform/web/vendor/esp32sim/UPSTREAM.md)
- [实际 Workbench 用例](../../../platform/tests/test_public_workbench_browser.mjs)

## 初代 Cardputer 原生工作台

工作台连接隔离的 Device Service，上传未改动的 Factory v0.9，聚焦初代 Cardputer 模型并按 A。浏览器的按键请求经 QMP 到达 m5cardputer。实际 240 × 135 会话帧在按键后从启动提示切换为应用菜单。先下载证据，再停止并保留会话历史。

- [工作台端到端摘要](cardputer-native-workbench-summary.json)
- [V0.8、V0.9 和官方 UIFlow2 的独立设备服务取证](../2026-11-09-cardputer-k132/README.md)

## PaperS3 与 PaperDIY 合并构建复测

在同一份包含 0168 和 0169 的 Xtensa QEMU 上，通过独立 Device Service 重放两款原厂演示。PaperS3 的 GT911 输入改变蜂鸣器图标区的 607 个像素。PaperDIY 的 A/B 按住、松开分别改变各自区域 533 个像素，松开后回到基线，另一按键区域保持原样。两个会话先导出证据，再停止并释放 Flash。

- [合并构建摘要](paper-native-combined-summary.json)
- [原厂固件及 UIFlow2 探针复现](../2026-11-09-paper-et047tc1/README.md)
- [CoreMatrix C158 单独后端的探针和官方固件对照](../../../tests/firmware/corematrix_backend_feasibility/README.md)

## 两款 Paper 的固件导入

四个正向 HTTP 试验接受正确型号的原厂样本与 UIFlow2 v2.5.4。两个交叉导入试验识别出另一型号的原厂项目，返回 HTTP 409 和 `firmware_board_mismatch`。未知项目仍走既有固件和外设约束。[导入摘要](paper-board-admission-summary.json)

## CoreMatrix 独立 3D 诊断工作台

C158 诊断运行器以 `--workbench` 在本机开放预建会话。Chromium 在 CoreMatrix 外壳上执行 A/B/C 和 A+C 组合输入，逐帧检查模型的 16 × 16 显示纹理、同会话串口以及 PM1 状态。诊断入口限制固件上传、创建会话、修改 QOM 和跨域访问。[诊断工作台摘要](../../../tests/firmware/corematrix_backend_feasibility/workbench-summary.json)

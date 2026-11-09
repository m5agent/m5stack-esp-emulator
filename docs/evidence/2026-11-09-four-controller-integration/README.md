# PaperDIY、PaperS3、初代 Cardputer、CoreMatrix 接入

外壳来源固定到 [m5stack-models de6cddc](https://github.com/yuyun2000/m5stack-models/tree/de6cddc065674ecb53bba29c7fe90d9ab4ee32f7)。
真实浏览器验证四款模型深链、尺寸和同一模型上的帧写入。CoreMatrix 核对 16 × 16 灰度字节到三处点位的映射。既有 Cardputer-ADV 也单独回归。模型检查本身只证明 WebGL 与宿主接口。

## PaperS3 浏览器原型对照

这是独立的 virtual-device validation。使用已有明确隔离的 esp32sim 参考原型，不改变生产 QEMU-WASM 准入。由固定源码重建的 WASM 和公开原厂 Factory v0.5 在静态工作台中执行。应用通过原控制器输出 540 × 960 帧，模型屏幕的两次实际指针点按都路由至 (116, 330)，应用图标区域发生变化。观察到实际 Worker 目标在停止后、关闭上下文之前消失。固件、ROM、WASM 和原始帧不纳入源码。首轮浏览器用例误将“浏览设备模型”当作禁用按钮，修正断言后复验。

- [浏览器摘要](papers3-browser-prototype-summary.json)
- [固定源码及本地构建步骤](../../../platform/web/vendor/esp32sim/UPSTREAM.md)
- [实际 Workbench 用例](../../../platform/tests/test_public_workbench_browser.mjs)

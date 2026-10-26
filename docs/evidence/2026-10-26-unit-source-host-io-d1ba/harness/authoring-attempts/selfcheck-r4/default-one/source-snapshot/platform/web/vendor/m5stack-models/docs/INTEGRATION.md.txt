# 与 m5stack-esp-emulator 的边界

核对日期：2026-10-25；下游快照 `e3c5d089c33397c1948fb611e776d75cb3c20bd8`。没有修改下游仓库或部署模拟器。

下游 `platform/web/three-device-viewer.js` 的 `ThreeDeviceShell` 接收 `modelFactory`，创建模型后调用 `DeviceViewer.mount(model)` 和 `model.display('lcd')`。显示数据通过 `writeRGB565` 或外部图片写入；`input` 事件映射到下游的逻辑控制 ID。

本库继续提供同一结构：

- 模型工厂返回 `Device` 子类；`root` 是 Three.js 对象树。
- `lcd` 的像素尺寸、物理面积和可见轮廓有独立记录，保持 framebuffer 映射。
- `Button` / 键盘网格只是视觉按键与命中区域，产生输入意图，不执行固件行为。
- LED 只接受外部渲染状态；不自行生成硬件事件、遥测或亮灯时序。
- Unit 提供几何、接口和可安装 Module，传感器锚点不提供模拟值或寄存器读写。
- 机械关节可暴露几何节点，旋转状态由外部驱动；不实现舵机物理学。

`catalog/products.json` 的 `emulatorId` 与下游设备 ID 对应；`integration.controlMap` 显式记录命名差异。下游的 Three.js import map / bundler 应使本库和 DeviceViewer 使用同一 Three.js 实例。

当前仅核对接口与模型层：没有把本库接入真实模拟器会话，不能将模型预览称为模拟器集成完成。

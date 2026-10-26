# UNIT-HOST-15：隔离的 HUB 布局候选

这是浏览器几何与交互候选，尚未推广到产品源。没有执行 Device Service、QEMU、固件或硬件测试。夹具中的读数只用于检查既有 rail 和 anchor 的显示关系。

## 适用范围

代码只自动处理 `m5stack.cores3` 的普通 CoreS3 module（`dinBase` 关闭），从直接 `grove` 端口接入一个 HUB。HUB 的直接子附件只允许 ENV III、ToF、Color、Button，允许其中部分槽为空。调用方传入 `unitPose`、其他 Unit、其他主机、DinBase、另一个 source 端口或更深 HUB 树均保留原布局；从候选场景切换到不支持的附件时，恢复尚存附件原来的 pose 和线缆选项。

完整四档场景仅验证 `grove-1=ENV III`、`grove-2=ToF`、`grove-3=Color`。Button 是 390px 下替换第一槽的交互与生命周期子例。没有用这两个场景证明全部排列、全部主机、另一固件或控制器路径。

## 依据和 API

固定的公开模型来源为 `yuyun2000/m5stack-models`，vendor manifest 的 commit 是 `48ab992f5ff63c1a91296051e1afcb5959877903`。

- `src/core/components/Port.js`、`src/core/Module.js`：口面原点，+Y 朝外，+Z 朝宿主正面；模块保持挂在原 Port 下，路径和事件向宿主递归。
- `src/units/hub/dimensions.js`：HUB 标称 24×32×10.8 mm；三个输出 x 坐标为 -7.5、0、7.5 mm。默认附件并列放置时，24 mm 宽的 Unit 外壳会重叠。
- `catalog/products.json` 和各 Unit 的 `dimensions.js`：ENV III、ToF、Color 为 24×32×8 mm 量级；布局直接测量当前模型自己的可见几何包络，排除线缆、透明 hit-only 体积和已挂的下级模块。
- `docs/GROVE-CABLE.md` 与 `src/modeling/grove-cable.js`：公开的 `unitFrame.setPose()`、`cable.setOptions()`、`getState()`；实际输入口绑定在线缆 target，保留原 `sensor` 和控制路径。

## 布局

保留 1:1 的模型 scale、全部原始外壳与控制几何，把 HUB 放在控制器左侧，三个子附件按输出编号放在上方一排。各 Unit 的正面与宿主正面一致，输入口朝向中间的线缆走廊。新 pose 由宿主坐标转换到每个实际 Port 的局部坐标，线缆仍由官方 API 从两个真实连接器端点重建。

子附件之间预留 14 mm 外壳间隙；附件排的底部离控制器或 HUB 顶部 28 mm。线束向上前方弯曲，主机到 HUB 的线束改走下方。没有重接逻辑总线、移动 connector 相对本体的位置、改线序或替换模型的控制命中区。

槽位顺序固定，但不是固定世界坐标：空槽保留 24 mm 标称宽度，ENV III 实际包络约 24.1 mm，附件变化时可能重新居中约 0.05 mm。本轮不承诺独立机械附件可任意移动后的自动碰撞求解。

## 失败隔离

布局放在 `ModelDeviceShell.updateUnitAssemblyLayout()` 的可选 presentation 边界。快照、包络或恢复抛错时返回明确 `unavailable`，已完成的 `Port.attach()` 不进入原有 dispose 分支。恢复使用一次有界事务回滚，不引入 timer、重试队列、POST 或新的渲染循环。

独立负控覆盖原本 try 外的 snapshot/getState 失败，以及 unsupported 分支的恢复中途失败；两者都保留已成功附件、兄弟附件身份与世界位置，并通过真实浏览器 pointer 验证原嵌套 Button 路径仍收到 down/up。原来的 inside-try pose 失败回滚测试也保留。

## 证据边界

默认 front 总览在 1440/1024/768/390 检查了完整外壳、主机 LCD/控制区、线缆实际投影、真实连接器和 rail。线缆表面抽样检查实际 TubeGeometry 的 8 条表面轨、每隔 2 个 ring 的线段；6144 段与可见外壳的世界包络先裁剪，再双向 raycast。故意恢复第一版错误走线产生碰壳命中，恢复候选后为零；这不是任意场景的连续碰撞证明。

全景中的原生 Button pad 约 23.76×19.07 px，真实 pointer 成功，但手机总览触控舒适度保持 **PARTIAL**。公开 `viewer.focus(path)` 的放大子例只证明原命中区在既有 focus 路径可交互，不代表全景保持可见。未新增产品 focus 控件，未改默认 camera fit 或 vendor hitbox。

候选解决本例 housing 叠放与线缆穿壳，不授予整体验收、物理等效、固件功能、真实硬件或全部主机/附件组合 PASS。

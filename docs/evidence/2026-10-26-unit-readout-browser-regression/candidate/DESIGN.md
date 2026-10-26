# Unit 实时读数候选：画布外 rail（未应用）

本目录只保存候选、冻结 base、最小补丁和 browser-only 回放。没有修改产品源，
没有新建 Device Service/QEMU session，不授予新增 guest 或硬件 PASS。

## 最终交互与范围

实时读数放在 WebGL 画布下方的独立 rail，数值保持 16px，保留全部有效标量，
不靠遮藏或缩字避让。每个外设的实际 sensor anchor、leader 和 rail 卡片使用同号。
投影跟随实际 camera/render，线与标记 pointer-events:none；读数卡完全在 canvas
外面，不挡宿主显示屏/按钮/触摸区域。rail 随内容增高，移动端正常纵向滚动。

外设卡名只用产品名，rail 标题为“实时读数”。普通输入明确标“模拟输入”；
Relay.output-level、Buzzer.frequency-hz/duty-pct 标“固件输出”。Thermal 的
control-word 同时可由QOM和guest写入，标“控制寄存器状态”；raw-fixture-ready
是模型根据注入原始数据派生的状态，标“模型状态”。字段来源是明确的presentation
映射，不由 inputs/outputs/readOnly 推导，未修改catalog或冻结contract。

degC仅显示别名°C，值不换算。raw16、Pa、%RH、mm、Hz等保留原单位语义；
布尔值显示true/false，不推断接点、负载、声学或机械响应。

目标12项为 ENV III、PIR、Ultrasonic I2C、Color、ToF、Light、Relay、NCIR、
Heart、Thermal、TVOC、Buzzer。只展示实际存在且符合冻结schema的number/integer/
boolean字段。数组与长原始块继续留在面板；Heart不推导心率，Thermal不生成热图。
这12项readout能力不能与现有机械/LED/按钮visual mapping状态混为一项或升级组件。

## 数据门与错误隔离

数值同时要求 session running、outer.source=live、unit.source=guest-qom、
unit.available=true、无errors、frozenDefinitions=true。字段须存在且类型、有限性、
minimum/maximum/enum匹配；不读default或pending input，不钳位越界值。持久化、
缺失来源、inventory fallback、启动/终态、不可用时清除数字并显示状态。

UnitPanel的optional annotation和既有visual painter分别try/catch，绘制错误不能
把成功输入ACK改成“输入未确认”，也不能改变release-intent/retry语义。
P2七个核心方法 projected/releaseValue/confirmRelease/recoverReleases/send/
setHeld/releaseHeld 逐字未变，见p2-continuity.json。

detach清理本端口与子路径；不支持注释的父Unit paint只清自身，不清孩子。
dispose注销render与ResizeObserver、移除rail/layer。零items时layout立即返回。
没有新动画循环、输入POST、controller假值或物理组件命令。

## 接口与补丁

CADUnit.js和ClassicUnit.js的sensor metadata role=visual-anchor；Component公开
object3d，ComponentHost.find解析真实嵌套路径。DeviceViewer公开camera、renderer
和render事件；getWorldPosition(Vector3).project(camera)只用于标号/leader坐标。
未改vendor几何。session样式保留420px桌面/460px移动画布，额外rail在其下展开。

candidate.patch是4文件完整候选；shell-and-rail.patch含新unit-annotations.js、
model-shell.js与unit-panel.css；panel-glue.patch仅UnitPanel接入，交root审查后
再应用。三份base见base-source-sha256.json；三个patch的apply-check均通过，均未
实际apply。生成候选的旧overlay版本保留在versions/overlay-before-rail/。

## 验证及视觉边界

rail-browser-only-results-5/report.json：15组检查PASS。独立ephemeral HTTP服务
只提供shadow静态资产；没有访问8787/API/QEMU。ENV/Relay读数回放自host9证据，
其余浏览器fixture不冒充新guest执行。独立离线contract测试覆盖17个正负例，包含
范围、双层来源、mutable inventory、Thermal来源与optional painter ACK/retry隔离。

ENV/Relay/nested各四档1440/1024/768/390，共12张PNG已逐一人工查看。全部有效
数值完整可读，卡片不相互重叠，不与实际宿主display/interactive投影bbox相交；
真实鼠标LCD touch仍收到start/end。M5Stack Web Design token audit为0问题。
设计沿用仓库m5 tokens：白/浅灰rail、细描边、深蓝标题、16px数值；无新增品牌色。

**readout placement PASS，不是完整场景视觉PASS。** nested三个外设housing在
原装配布局中仍互相叠放，属于UNIT-HOST-15 OPEN；本候选不调整线缆/模型排布，
不声称nested整体几何保真。visual-review.json将读数placement与该边界分别记录。

下一步由root审核并应用候选、运行现有browser回归，再在原goal授权下协调针对
ENV/Relay的可见真实session，绑定firmware/runtime/generation/DOM/HTTP/serial/
QOM与停止前ZIP。当前记录不替代该层验证。

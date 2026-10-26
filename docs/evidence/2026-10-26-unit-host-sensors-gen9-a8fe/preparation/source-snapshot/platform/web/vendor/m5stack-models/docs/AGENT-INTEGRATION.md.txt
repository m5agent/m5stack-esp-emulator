# 动态外壳接入：给下游 Agent

本库负责毫米尺度的外观、键帽行程、视觉关节、线缆和输入意图。下游负责固件、电气、总线、传感器值、设备状态及舵机/电机物理模型。默认模型静止；设置 `rpm` 只要求渲染器旋转，不表示给硬件通电。

## 先使用公开 API

```js
import {DeviceViewer} from 'm5stack-models.js/core';
import {loadModel, loadGroveModule} from 'm5stack-models.js/loaders';

const viewer = new DeviceViewer(container, {keyboard: 'focused'});
const host = await loadModel('sticks3');
viewer.mount(host);

// 按需加载，挂接后原有组件路径继续成立。
const fan = await loadGroveModule('fan', {
  propeller: true, cableLength: 85,
  cable: {slack: 16, bend: [0, 0, -1]},
});
host.port('grove').attach(fan);
host.get('grove/rotor').set({rpm: 120});
host.get('grove/unitFrame').setDistance(100);
host.get('grove/cable').setOptions({slack: 24});
viewer.fit();

// 输入事件交给下游。不要把外部视觉状态命令回送为输入。
const off = host.on('input', event => runtime.sendInput(event));
```

`runtime` 是下游提供的对象。示例没有实现它，也没有向真实设备发送命令。Three.js 应由下游 bundler 去重，避免模型与 Viewer 各用一个 Three.js 实例。仓库导出源码，使用 ESM bundler 接入；不要把所有模型一次打进首屏。

## 输入、按压与稳定开关

```js
host.button('btnA').press('external-preview');
host.button('btnA').release('external-preview');
// 失焦、捕获丢失、组件卸载时取消；不产生 click。
host.button('btnA').cancel('external-preview');

host.handle({type: 'press', target: 'btnA'});
host.handle({type: 'release', target: 'btnA'});
```

同一个来源必须成对释放。多来源同时按住时，最后一个来源释放才回弹。`press` / `release` 会产生输入意图，适合交互注入；不要用它们反馈固件自己的键状态，避免回声循环。电容区 `travel=0`，有输入意图但不伪造机械位移。

`button.getActuationState()` 返回只读的 `{depthMm, targetDepthMm, settled}`，用于观察视觉插值是否到达终点；`getState()` 保持原输入状态结构。不要通过 `cap.position` 判断所有按键的行程：Button U027 的原壳片绕固定根部弯曲，Limit U145 的金属柄绕固定铰链转动。二者继续使用相同的 `press/release/cancel` 和输入路径，`meta.visualMotion` 分别为 `flex-pad` / `lever`。行程和角度中未获机械图确认的值均为外观估计。

CardKB v1.1（U035-B）有50个独立实体按钮，例如 `key-q`、`key-1`、`key-esc`、`key-up`；挂载后使用 `grove/key-q`。本层只发送各键按压意图，下游负责矩阵扫描、字符、组合键及I2C字节。它不是CardKB2。Cardputer-ADV新增 `grove-power` 两档滑块，只同步Grove供电方向选择器的外观，不切换任何电气状态。

Unit Key U144 使用 `press` 和独立的 `rgb`。红色空心键帽与轴芯一起压放，1.6 mm 行程是外观估计。官方规格表总高22.6 mm与机械图24.3 mm冲突，两者均保留，当前可见外形依据机械图。

Unit 8Encoder U153 使用 `rotation-1`…`rotation-8`、`press-1`…`press-8`、稳定档位 `switch` 及 `rgb-1`…`rgb-9`。CH1靠Grove端，CH8靠开关端。0.35 mm按压与2.2 mm开关档距为外观估计；灯位编号只对应几何位置，不能据此推定电气串链编号。

`Button.latching=true` 的滑动开关在首次按下时切换稳定档位，松手不会回位。外部状态同步可用 `setPosition(0|1)` 或 `handle({action:'position', target, position:1})`，不会模拟电源逻辑。读取 `getState().position`。不要把所有带 `power` 的旧 ID 当成电源：Tab5 的 legacy `power` 指向电池卡扣，Nesso 的 legacy ID 也要结合 label/meta 确认含义。

使用 `DeviceViewer({keyboard:'focused'})` 后仅聚焦 canvas 时处理设备快捷键。失焦、标签隐藏、卸载和 pointer capture 丢失会取消按住的输入；默认 `keyboard:true` 保留上游全局快捷键习惯。表单输入不会触发设备键。

## 关节命令与寻址

```js
const robot = await loadModel('stackchan');
robot.handle({type: 'joint', target: 'yaw', angleDeg: 30, durationMs: 400});
robot.handle({type: 'joint', target: 'pitch', angleDeg: 35, durationMs: 400});
// 有连续轴的组件才接受非零 rpm。
robot.get('yaw').set({rpm: 5});
robot.get('yaw').set({rpm: 0});

const encoder = await loadModel('encoder');
encoder.get('rotation').set({angleDeg: 90});
const joystick = await loadModel('joystick-v11');
joystick.get('tilt-x').set({angleDeg: 12});
joystick.get('tilt-y').set({angleDeg: -8});
joystick.button('press').click();
```

| 产品 | 组件路径 | 用法 |
| --- | --- | --- |
| StackChan | `yaw` / `pitch` | 底座不动；颈部水平旋转；头部俯仰 |
| Fan | `rotor` | 裸轴或可选风叶一起旋转 |
| Encoder | `rotation` / `press` | 连续旋转及实体旋钮按压 |
| Angle | `rotation` | 外部绝对角度定位 |
| Joystick v1.1 | `tilt-x` / `tilt-y` / `press` | 两轴倾斜与倾斜后的局部按压 |
| Key | `press` / `rgb` | 实体键帽压放，灯光独立外驱 |
| 8Encoder | `rotation-1`…`rotation-8` / `press-1`…`press-8` / `switch` | 八路独立旋转/按压，开关保持档位 |

挂到 `grove` 后上述 Unit 路径都加 `grove/` 前缀。进一步嵌套的 HUB 同样按 Port 递归，不硬编码场景树 child 索引。可通过 `host.list('joint')`、`host.list('button')` 与组件 `.path` 枚举。

角度为度、`durationMs` 为毫秒、`rpm` 为视觉转速；传给关节的是它自身局部轴上的角度。StackChan 的 pitch 使用当前正视装配为 0，正角抬头，接受 `[0,90]`；这不是硬件舵机的校准零位。Angle/Joystick 的 demo 滑条范围只用于观察姿态，不能作为机械限位或传感器换算关系。轴线与范围依据见 [VISUAL-MOTION.md](VISUAL-MOTION.md)。

StackChan 的前侧 Power 板跟随 pitch，下端 Adapter 跟随 yaw，七根可见线束跨两组端点更新；底座 USB 固定。官方后部为开放机构，不能用虚构后盖封住。线束路线及隐藏舵机包装为视觉近似，不模拟材料、电气或碰撞求解。

`getState()` 提供 `angleDeg`、`targetAngleDeg`、`rpm`、`transitioning`、`continuous`、`rangeDeg`、`visualRangeDeg`、`demoRpmMax`。绝对角度命令停止原有 rpm；新的 rpm 命令取消原有角度插值。模型不自动运行点头、摆头、测量或固件逻辑。

## Grove 装配坐标

`Port` 原点在口面，局部 +Y 向外、+Z 朝宿主正面，1 单位 = 1 mm。`cableLength` 兼容旧入口，表示初始口面间距，曲线实际长度请读 `cable.getState().curveLengthMm`。

```js
const frame = host.get('grove/unitFrame');
// position 是 Unit 装配原点在宿主 Port 局部坐标的位置；rotation 为弧度。
frame.setPose({rotation: [0, 0, Math.PI / 6]});
// 保留当前旋转，把 Unit 的真实输入口对准 [0,90,0]。
frame.setDistance(90);
const geometry = host.get('grove/cable').getState();
// geometry.source / target 是两端真实口面的相对位置与朝向。
```

线缆跟随端点和方向，不做碰撞求解。调用方要避免任意摆放引起模型互穿或线缆穿过其他物体。详见 [GROVE-CABLE.md](GROVE-CABLE.md)。

## 外部灯光状态

```js
const keys = await loadGroveModule('8encoder');
host.port('grove').attach(keys);
host.get('grove/rotation-1').set({angleDeg: 135});
host.button('grove/press-1').press('preview');
host.button('grove/press-1').release('preview');
host.get('grove/rgb-1').set({color: '#22b477', brightness: 0.4});
host.get('grove/rgb-1').set({on: false});
```

灯光的 kind 为 `led`，用 `host.list('led')` 枚举。`Led.set({color,brightness})` 或 `handle({type:'led',target,…})` 更新外观，亮度范围0…1；`getState()` 返回颜色和亮度。它不会产生输入事件或与按键自动联动。demo的“灯光外观”面板使用相同公开API。

## 渲染与生命周期

`DeviceViewer` 自动调用 `host.update(dt, time)` 并在姿态变化时渲染。自建渲染器必须调用它，`dt` 和 `time` 单位均为秒；持续 rpm、插值与键帽动画会返回动画标志。外部的直接变换需要请求渲染；关节和线缆 setter 已请求。

```js
// 自建渲染循环：
host.update(deltaSeconds, elapsedSeconds);
renderer.render(scene, camera);

// 断开默认 dispose；复用时显式保留。
const saved = host.port('grove').detach({dispose: false});
host.port('grove').attach(saved);
host.port('grove').detach();
off();
viewer.unmount(host); // 卸载不销毁，允许缓存复用。
host.dispose();      // 最终清理 geometry/material/timer。
viewer.dispose();
```

同一 Module 实例再次 `attach` 到原接口是幂等操作；挂到另一兼容接口时会从旧口安全转移，保留实例状态和资源。兼容性与循环挂载检查发生在装配变更前。同步生命周期回调不能重挂正在装卸的同一实例或正在挂载的目标口，应等当前调用结束后再发起下一次装配。默认 `detach()` 销毁实例；需要缓存时使用 `detach({dispose:false})`，最终由调用方销毁。

拆卸前会沿原宿主链同步发出 `module:will-detach`，事件载荷为 `{port,module}`。此时旧路径和父子关系仍有效，适合取消将被移除子树中的外部输入；它是生命周期事件，不是新的 `input` action。查看器与 demo 只取消各自持有的输入，无关按钮继续保持。外部框架创建的 hold 应由该框架取消，并在更改父链前完成配对；取消使用 `button.cancel(source)`，不会产生 click。

同一 Viewer 重复 `mount(host)` 不重复订阅或更新；跨 Viewer 挂载会先解除旧 Viewer 的归属。`unmount` 取消旧 Viewer 持有的键盘/指针输入，但不销毁模型。若下游缓存带有持续运动的模型，需自行决定卸载时是否 `set({rpm:0})`；demo 切换模型时会停止连续轴，返回缓存时保持停止。

demo 的异步 Unit 加载在切换模型、接口或 Unit 后会作废旧请求，未挂载的过期实例会释放。连接刷新保留仍有效的按键检查位置和 LED 选位；DOM 控件被替换时取消其输入，明确的“保持按下”只在目标仍存在且仍被选中时保留。

## 修改后验证

从仓库根目录运行 `npm run check`、`npm run build`、`./manage.sh status`。专项测试覆盖真实帽位移/方向/回位、固定根部弯曲、刚性杠杆、多键与多旋钮、稳定档位、多来源取消、关节父子装配、静止与终帧、目录内Unit线缆端点与默认姿态穿壳。另检查所有真实主机Grove口、CoreS3 DinBase及StackChan组合姿态中的插头坐标与渲染线管表面轨迹；覆盖数以当前生成报告为准。

生命周期专项为 `scripts/check-port-lifecycle.mjs`、`scripts/check-viewer-lifecycle.mjs`、`scripts/check-demo-lifecycle.mjs`，已接入正常检查。Viewer 专项运行真实查看器与输入路由，以无 GPU renderer 和 DOM 边界替身检查所有权和取消顺序；这些替身不提供浏览器视觉证据。

还需打开 demo，实际操作按键按住/回弹、模型快捷键与表单焦点、连接/断开、端点旋转、风叶转动、摇杆倾斜与按压、StackChan 组合姿态。Node 几何测试不能替代浏览器画面，也不能证明下游模拟器、真实硬件、机械配合或硬件限位正确。

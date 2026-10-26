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

`loadModel()` 返回的模型按需构建。首次直接调用 `getState()` 也会建立真实组件并返回当前快照，不需要先访问 `root`、`get()` 或 `list()`。挂接模块仍在对应端口的 `module.state` 下递归返回；它不读取硬件或执行固件。

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

CardKB 的 `AltLeft` 显式映射到 Sym 实体键，仅在模型画布聚焦时处理该 Alt 键自身。Alt 与其他键的组合、未映射的修饰键和表单输入继续留给浏览器；失焦或键释放会清除已有的模型按压来源。

Unit Key U144 使用 `press` 和独立的 `rgb`。红色空心键帽与轴芯一起压放，1.6 mm 行程是外观估计。官方规格表总高22.6 mm与机械图24.3 mm冲突，两者均保留，当前可见外形依据机械图。

Unit 8Encoder U153 使用 `rotation-1`…`rotation-8`、`press-1`…`press-8`、稳定档位 `switch` 及 `rgb-1`…`rgb-9`。CH1靠Grove端，CH8靠开关端。0.35 mm按压与2.2 mm开关档距为外观估计；灯位编号只对应几何位置，不能据此推定电气串链编号。

`Button.latching=true` 的滑动开关在首次按下时切换稳定档位，松手不会回位。外部状态同步可用 `setPosition(0|1)` 或 `handle({action:'position', target, position:1})`，不会模拟电源逻辑。读取 `getState().position`。不要把所有带 `power` 的旧 ID 当成电源：Tab5 的 legacy `power` 指向电池卡扣，Nesso 的 legacy ID 也要结合 label/meta 确认含义。

demo 的“定格检查”列出所有 Button，包括稳定滑块与零行程电容区，均可选择后近看。瞬时键与电容区支持保持／弹起；滑块通过上方独立开关切档，保持／弹起按钮禁用。悬停只提供外观高亮，按下／释放不自动点灯；验证压程时应比较同一悬停状态，并以真实帽体运动为准。电容区只改变输入状态，机械行程保持0。

“近看”只缩放和平移，保留当前模型旋转。检查侧面或背面的按钮时先选择对应视角，再选择按钮并近看，避免被壳体遮住的帽体造成压程不可见。

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
| Roller485 U182 | `rotor` / `press` | 标准滑环版转盘与顶端 Grove 随转，底部实体弹舌压放 |
| Encoder | `rotation` / `press` | 连续旋转及实体旋钮按压 |
| Angle | `rotation` | 外部绝对角度定位 |
| Light U021 | `trim` | 金属微调头绕局部+Z定位，蓝色座固定 |
| Joystick v1.1 | `tilt-x` / `tilt-y` / `press` | 两轴倾斜与倾斜后的局部按压 |
| Key | `press` / `rgb` | 实体键帽压放，灯光独立外驱 |
| 8Encoder | `rotation-1`…`rotation-8` / `press-1`…`press-8` / `switch` | 八路独立旋转/按压，开关保持档位 |

挂到 `grove` 后上述 Unit 路径都加 `grove/` 前缀。进一步嵌套的 HUB 同样按 Port 递归，不硬编码场景树 child 索引。可通过 `host.list('joint')`、`host.list('button')` 与组件 `.path` 枚举。

Roller485 为 U182 标准滑环版，`rotor` 绕模型 `+Y`，接受外部角度或连续视觉转速。转盘、外转子、顶端 `grove-top` 和 `top-led` 一起转；基座的 `lcd`、`press`、双 RGB、`grove`、`pwr485` 和 `debug` 固定。`lcd` 在底面 `-Y`，为 64×48 白色单色 OLED，外部 RGB 帧仅在产品局部着色器中按亮度显示为白光。`press` 的 0.25 mm 自由端压程与隐藏支撑为外观推导。

```js
const roller = await loadGroveModule('roller485', {cableLength:85});
host.port('grove').attach(roller);
host.get('grove/rotor').set({angleDeg:90});
host.get('grove/rotor').set({rpm:20});
host.get('grove/rotor').set({rpm:0});
host.display('grove/lcd').fill('#ffffff');
roller.port('grove-top').attach(await loadGroveModule('env-iii'));
```

顶端挂接后的组件路径为 `grove/grove-top/…`，装配姿态相对该转动端口；线缆/子组件随接口坐标变换，调用方可另设 `unitFrame` 姿态。接口显示不传播供电或 I2C/RS485 信号。`rgb-1/rgb-2` 是空间位置编号，不推定电气链序；`top-led` 是固定红色，只接受亮度/开关的外观效果，不因挂接或电机状态自动点亮。`pwr485/debug` 保留真实连接器外形与元数据，不属于 Grove 连接菜单。

角度为度、`durationMs` 为毫秒、`rpm` 为视觉转速；传给关节的是它自身局部轴上的角度。StackChan 的 pitch 使用当前正视装配为 0，正角抬头，接受 `[0,90]`；这不是硬件舵机的校准零位。Angle/Joystick 的 demo 滑条范围只用于观察姿态，不能作为机械限位或传感器换算关系。轴线与范围依据见 [VISUAL-MOTION.md](VISUAL-MOTION.md)。

Light U021 的 `trim` 只旋转有厚度、带真实工具槽的金属头，位置为`[0,2.5,3.72]` mm，局部轴为`+Z`。它是位置式关节，拒绝非零rpm；`visualRangeDeg=[-135,135]`仅供demo观察，`rangeDeg=null`，额定机械限位、旋向和电气零位未确认。头半径1.5 mm、槽深0.32 mm及蓝色座尺寸均为照片估计。调用方直接指定外观角度，不在本层换算电阻、光强阈值、比较器结果或ADC值。

```js
const light = await loadModel('light');
light.get('trim').set({angleDeg:45});

const lightHost = await loadModel('sticks3');
lightHost.port('grove').attach(await loadGroveModule('light', {cableLength:70}));
lightHost.handle({type:'joint',target:'grove/trim',angleDeg:-45});
```

StackChan 的前侧 Power 板跟随 pitch，下端 Adapter 跟随 yaw，七根可见线束跨两组端点更新；底座 USB 固定。官方后部为开放机构，不能用虚构后盖封住。线束路线及隐藏舵机包装为视觉近似，不模拟材料、电气或碰撞求解。

`getState()` 提供 `angleDeg`、`targetAngleDeg`、`rpm`、`transitioning`、`continuous`、`rangeDeg`、`visualRangeDeg`、`demoRpmMax`。绝对角度命令停止原有 rpm；新的 rpm 命令取消原有角度插值。模型不自动运行点头、摆头、测量或固件逻辑。

## Encoder U135

`rotation`、`press` 与独立的 `led0/led1` 保留原寻址，挂到主机后使用 `grove/rotation`、`grove/press`、`grove/led0` 等递归路径。实际Ø10黑帽和轴绕原CAD collar拟合轴 `[-0.0130000268,7.9499998353,6]` mm旋转；0.35 mm按压仅为外观行程估计。固定支撑、PCB和Grove座保持静止，不生成编码计数、脉冲、I2C或固件行为。

两RGB位于Grove两侧下端，`led0/led1`分别表示正视左/右，尚未确认对应原理图LED1/LED2的电气顺序。官方视频显示白壳下端漫透；外部颜色/亮度驱动原前壳自身的局部emissive外观，默认熄灭，按压/转动不自动改变灯色。这不声明光学材料或光线输运模拟。

```js
const encoder = await loadGroveModule('encoder', {cableLength:70});
host.port('grove').attach(encoder);
host.get('grove/rotation').set({angleDeg:90});
host.button('grove/press').press('preview');
host.button('grove/press').release('preview');
host.handle({type:'led',target:'grove/led0',color:'#22b477',brightness:.4});
host.handle({type:'led',target:'grove/led1',on:false});
```

Thermal U016只保留`sensor`视觉anchor，不提供温度、热图、IR可见光或运动命令。其`grove`口面由旧`[0,-15.65,0]`改为`[0,-15.65,1.4]` mm；10×5.2 mm座体来自自身机械图，Z1.4由原CAD入口对齐推导。默认`loadGroveModule('thermal')`与`unitFrame.setDistance`按当前真实口对齐；显式`unitPose.position`仍是装配原点。依赖旧工程坐标的调用者读取当前Port变换，递归路径（如`grove/grove-1/sensor`）、插头与四芯线API保持。完整110°黑包体与小窗为外观实体，凹面深度、板形/高度和裁短脚含推导，见[Thermal建模记录](THERMAL-MODEL-NOTES.md)。

Angle U005保持`rotation`绝对角度接口和递归路径，例如`host.handle({type:'joint',target:'grove/rotation',angleDeg:37})`。本批将旧轴心Y7校正为自身图纸Y8，含齿帽直径遵循Ø9.5；固定包体/板/金属框不随动。实际Grove工程原点从`[0,-15.65,0]`改为`[0,-15.65,1.4]` mm，5.2 mm高度来自自身CAD槽底−1.2到前面+4的包络推导，非官方标注口高。默认模块自动对齐，显式unitPose仍是装配原点；依赖旧坐标的布局读取当前Port变换。网页名义厚度22与机械图总高22.3分开记录。`rpm`仍拒绝，viewer范围不等于机械限位或传感器换算。见[Angle建模记录](ANGLE-MODEL-NOTES.md)。

U135实际 `grove` 口面原点由旧 `[0,-15.65,0]` 更正为 `[0,-15.65,-0.6]` mm，Z取自该产品原壳 `-3.2…2` mm开口中点。`loadGroveModule`和`unitFrame.setDistance`按真实口面重新对齐；直接使用旧Port工程坐标的布局应读取当前Port变换，显式`unitPose.position`仍为装配原点。隐藏PCB/包体/焊腿、帽轴深度、口内尺寸和漫透亮斑范围仍为推导。公开来源与推导见[Encoder来源记录](../source-manifest.json)，专项审查见[Encoder审查记录](../artifacts/encoder-detail/public/review.json)，当前stage保持`modeled`。

NCIR U028保留`sensor`视觉anchor，不提供温度、热图、IR可见光或运动命令。真实`grove`口面由旧`[0,-15.65,0]`改为`[0,-15.65,1.4]` mm，座体10×5.2 mm和入口上下界有本款机械图／CAD依据。默认`loadGroveModule('ncir')`与`unitFrame.setDistance`按当前真实口对齐；显式`unitPose.position`仍是装配原点。依赖旧工程坐标的调用者读取当前Port变换，递归路径（如`grove/grove-1/sensor`）、插头与四芯线API保持。完整TO39的金属筒、凸冠、Ø3.5凹窗和真实环隙分开建模；PCB、安装yaw、脚裁长及局部台阶含推导，见[NCIR建模记录](NCIR-MODEL-NOTES.md)。

PCB孔内壁现按实际FrontSide几何检查，Thermal／Angle／Encoder修复不改变公开组件、Port坐标或外驱状态；下游接法保持。相关拓扑回归与历史证据边界见[PCB孔内壁说明](PCB-HOLE-WINDING.md)。

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

CardputerZero C154 的外围坐标在 2026-10-26 按官方正面及斜视照片校正。以正视屏幕时 +X 向右为基准，HDMI/音频/Grove 组移到右侧，USB-A/RJ45/Boot 组移到左侧；microSD 和顶部红外件同步修正。组件 ID、连接器类型、按键输入和帧缓冲 API 保留，依赖旧硬编码左右坐标的调用方需要迁移：

| 组件 ID | 当前口面位置 mm | 当前外法向 |
| --- | --- | --- |
| `grove` | `[42.04,13.1,0.85]` | `+X` |
| `hdmi` | `[42.04,-13.6,0.5]` | `+X` |
| `headset` | `[42.04,0.1,1.1]` | `+X` |
| `usb-c2` | `[42.04,13.1,6.65]` | `+X` |
| `usb-c` | `[-42.04,13.1,6.65]` | `-X` |
| `usb-a` | `[-42.04,13.1,-0.7]` | `-X` |
| `ethernet` | `[-42.04,-13.8,-3.1]` | `-X` |
| `micro-sd` | `[-18.1,27.03,6.0]` | `+Y` |
| `ext` | `[0,27.03,1.2]` | `+Y`，保持原位 |

默认 Grove 连接会跟随更正后的右侧真实口面，继续使用 `host.port('grove').attach(...)`。直接布局先调用 `host.root.updateMatrixWorld(true)`，再读取 Port 的 `object3d.matrixWorld` 或 `getWorldPosition/getWorldQuaternion`，不要复用旧 `[-42.04,13.1,0.85]`。Boot 固定原点变为 `[-41.85,0.4,5.6]`，按下沿世界 `+X` 向壳内移动，`boot` 的 press/release/cancel 用法保持。官方图稿存在不同 C1/C2 标号修订，模型不据印刷图案推断 USB 协商、供电或电气角色。

Heart U029 的工程坐标修正：依据其自身官方10×5.2 mm口图和原壳Z=−1.2…4的开口，`grove`口面中心由历史`[0,-15.65,0]`更正为`[0,-15.65,1.4]` mm。RS485 U034的中心仍是`[0,-15.65,1.4]`。两款现为真实开放顶槽、短锁定舌、四触点及5.2 mm外部座高；下部8.6 mm通道、6.8 mm上槽、短针及凹入内底、深度／壁厚和Heart PCB切口仍为外观推导，不声明实物公差。

`loadGroveModule('heart',{cableLength:70})`会从实际输入口重新对齐，默认目标口仍为宿主Port局部`[0,70,0]`，调用方法和递归路径保持。直接使用旧Heart Port工程坐标的布局应重新读取`heart.port('grove').object3d.position`；显式`unitPose.position`仍表示装配原点，不会静默加减1.4 mm。要按输入口定位，应在设旋转后调用`unitFrame.setDistance(...)`或读取真实Port世界变换。

HUB 可继续接 Unit，demo 的 Grove 接口菜单使用完整路径，例如 `grove/grove-1`，并排除已被上游线占用的 Module 输入口。连接/断开后保留有效选口；祖先模块拆卸后回到仍存在的祖先接口。

```js
const hub = await loadGroveModule('hub', {cableLength:70});
host.port('grove').attach(hub);
hub.port('grove-1').attach(await loadGroveModule('scroll', {cableLength:60}));
host.get('grove/grove-1/rotation').set({rpm:30});
host.button('grove/grove-1/press').press('external');
host.button('grove/grove-1/press').cancel('external');
host.get('grove/grove-1/rgb').set({color:'#22b477',brightness:.4});
```

Unit Scroll U186 的 `rotation` 沿自身 +X 转轴，`press` 使用独立输入来源，`rgb` 由外部控制。轮组、源 CAD 与隐藏支撑的视觉映射及按压估计见 [VISUAL-MOTION.md](VISUAL-MOTION.md)；不生成编码计数或 I2C 数据。

## 屏幕帧缓冲与目标选择

`host.list('display')` 返回包括挂接模块的屏幕，使用各组件的完整 `.path` 定位，例如 `lcd`、`grove/lcd` 或 `grove/grove-1/lcd`。通过 `host.display(targetPath).writeRGBA(rgba)`、`writeRGB565()` 或 `fill()` 写入外部像素；目标路径、像素内容和驱动协议由调用者提供。

demo 的“屏幕校准图”仅写当前所选屏幕。多屏时显示目标选择框；没有主机屏幕但接入带屏 Unit 时同样可用。选择、连接或拆卸只刷新目标，不清除其他屏已有的帧；同名路径替换后使用新的组件身份与校准状态。单色标记的 OLED 使用灰阶校准图，电子纸关闭校准时恢复纸色底。校准不是固件页面，也不模拟显示器驱动或刷新过程。

## 屏幕触点

```js
host.on('input', event => {
  if (event.kind === 'display' && event.id === 'lcd') {
    // action: start / move / end；x/y: 左上原点的整数像素。
    // pointerId 区分触点，points 为当前仍活动的点。
    externalRuntime.sendInput(event);
  }
});
const lcd = host.display('lcd');
lcd.touch('start',10,20,1);
lcd.touch('move',14,22,1);
lcd.touch('end',14,22,1);
lcd.setTouchEnabled(false);
```

指针取消和移出屏幕沿用 `end`，不增加新的输入 action。禁用会逐点结束活动触点；最终销毁静默清空并释放标记。`touch()` 是外部直接注入入口，仍可在指针触控禁用时使用；清理和销毁过程中不会重新创建触点。屏幕帧缓冲与触点输入相互独立，不自动执行设备页面或固件行为。

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

`invisible:true` 保留器件透镜及外部状态接口，但不产生人眼可见的 emissive 或 glow；demo 灯位菜单只列可见光器件。StickS3 的 `irTx` 继续接受原路径命令和状态查询，标记为不可见红外，不再渲染成红色指示灯。本库不模拟红外传输、波束或手机相机效果。

Heart U029 的 `red-led` 表示 MAX30100 靠 Grove 一端的可见红光孔，默认熄灭、颜色固定为`#ff2820`；任意`color`请求都保留红色，只接受外部开关／亮度。远 Grove 的圆窗是被动 SENSOR，不会跟着亮；IR 不绘为可见光。包体和两光心来自原厂p27，安装朝向由官方照片的非对称外形对应推导；绝对座深、透镜剖面、材质和视觉亮度仍为推导，不声明光学仿真。

```js
const heart = await loadModel('heart');
heart.handle({type:'led', target:'red-led', brightness:.6});
heart.handle({type:'led', target:'red-led', on:false});
host.port('grove').attach(await loadGroveModule('heart', {cableLength:70}));
host.handle({type:'led', target:'grove/red-led', brightness:.4});
```

demo会发现该灯位并禁用任意选色。调用方应明确给定亮度；本库不根据产品名、心率、测量模式、上电或挂接自动闪烁。原厂资料明确区分RED 660 nm与IR 880 nm，并说明纯心率模式的红灯关闭；不得从模型可见红光推断传感数据。

Color U009 的两颗白色补光使用`fill-left`、`fill-right`，默认颜色`#ffffff`、亮度0。两个路径标识左右可见封装，D1/D2与左右的对应尚未确认。官方原理图中两灯各经1K电阻接同一VCC，没有独立GPIO控制；按实际供电状态展示时，由调用方给两灯相同亮度。统一`Led`接口的`color`只是绘图参数，硬件仍为白灯，不据此声明RGB能力。本库不随挂接、上电或测量自动点灯；封装深度和光扩散为外观估计。

```js
const color = await loadModel('color');
for (const id of ['fill-left','fill-right']) color.led(id).set({brightness:.4});

const colorHost = await loadModel('sticks3');
colorHost.port('grove').attach(await loadGroveModule('color', {cableLength:70}));
colorHost.handle([
  {type:'led',target:'grove/fill-left',brightness:.4},
  {type:'led',target:'grove/fill-right',brightness:.4},
]);
```

所选旧版Relay U023保持无外驱灯组件。其[官方原理图](https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/577/UNIT-RELAY.pdf)中的D1为1N4148WS续流二极管，图中未含状态LED，对应正面照片也未定位可见灯。产品概述的“状态指示灯”表述与该来源冲突，反馈回执为`a3df6baaef22420dac639e23af0b302a`，仅代表接收待评估；在版本、物料位号和实际灯位得到确认前，不添加猜测灯或电气联动。

Cardputer-ADV 与 StamPLC 各有一颗 Stamp-S3A RGB，统一 ID 为 `stamp-rgb`，默认熄灭，例如 `host.handle({type:'led',target:'stamp-rgb',color:'#22b477',brightness:.65})`。StamPLC 文档中的红色下载指示是同一颗 RGB 的一种状态，模型不额外添加第二颗红灯；颜色／亮度由调用方给定，不实现下载启动顺序、GPIO38 供电门控或按键自动点灯。封装深度与光扩散仍是外观估计，原盖板的遮挡边缘保留。

StackChan 顶部 `touch-1`、`touch-2`、`touch-3` 为前／中／后三个零行程电容输入区，仍用 Button 的 `press/release/cancel`；左右各有 `rgb-left-1`…`rgb-left-6` 与 `rgb-right-1`…`rgb-right-6`。灯号表示从前向后的外观分段，不声明电气链顺序；边界、分段间距和光扩散为推导。全部随头部 pitch/yaw，触摸不会自动点灯。原来 pitch90° 中区被盖板挡住的问题已按源螺孔轴配准盖座修正，默认检查要求30姿态／90条整机顶面法向接近全部命中触区。该有限方向采样不保证任意相机角度可达，也不证明全局头颈datum、隐藏舵机或制造配合。

## Relay U023 的负载端子附件

默认 Relay 带开放的固定 3P 座。`terminal` 是独立的 `ht3.96-3p` 外观接口，三列从左到右为 COM、NO、NC，节距3.96 mm；它不会出现在 Grove 挂接目标中。`TerminalPlug` 是可拆附件，随附件出现的三颗工具槽螺钉可分别接收位置式转角：

```js
import {TerminalPlug} from 'm5stack-models.js/units/relay';

const relay = await loadModel('relay');
relay.port('terminal').attach(new TerminalPlug());
relay.handle({type:'joint', target:'terminal/screw-2', angleDeg:45});
relay.handle({type:'detach', target:'terminal'});

// 与真实 Grove 外观装配组合，路径按层级寻址。
host.port('grove').attach(await loadGroveModule('relay', {terminalPlug:true}));
host.handle({type:'joint', target:'grove/terminal/screw-1', angleDeg:-60});
host.handle({type:'detach', target:'grove/terminal'}); // 保留 Relay 与 Grove 线缆
```

`loadModel('relay', {terminalPlug:true})` 也可直接显示已插状态。demo 的“固定3P座／安装螺钉插头”配置可切换两种装配；已插状态显示三个螺钉角度控件。`screw-1`…`screw-3` 对应 COM／NO／NC，只转螺钉头，不接受非零 rpm，不实现螺纹升降、夹紧力、负载线路或触点通断。±180° 是查看范围，额定机械范围未确认。

`nominalMm` 保留官方规格表的24×48×8 mm基壳口径；`visualEnvelopeMm` 为官方机械图的24×48×14.6 mm外露装配，后螺钉另突出约0.055 mm。PCB、端子壁厚、内部接触深度和插头夹线结构为照片推导，接口类型名只用于本库几何配对，不证明不同厂家的实物通配。

## RS485 U034 的4P端子附件

U034 默认仍为空固定座。官方包装中随附的可拆4P端子由该产品入口导出的`TerminalPlug`提供，类型为`ht3.96-4p`；从左到右物理标签是B、A、12V+、12V-。可用`terminalPlug:true`直接装上，或单独挂接。它与Relay的3P附件分别导入，按各自连接器类型匹配。

```js
import {TerminalPlug as Rs485TerminalPlug} from 'm5stack-models.js/units/rs485';
const rs485 = await loadModel('rs485');
rs485.port('terminal').attach(new Rs485TerminalPlug());
rs485.handle({type:'joint',target:'terminal/screw-4',angleDeg:45});
rs485.handle({type:'detach',target:'terminal'});

host.port('grove').attach(await loadGroveModule('rs485', {terminalPlug:true}));
host.handle({type:'joint',target:'grove/terminal/screw-2',angleDeg:-60});
host.handle({type:'detach',target:'grove/terminal'}); // 保留Unit与Grove线缆
```

`screw-1`…`screw-4`随附件挂接出现，分别对应四个标签，只旋转真实工具槽螺钉头。固定座、接触孔、线入口和夹笼保持实体深度；不执行螺纹升降、夹线、RS485/UART、供电或电气连接。demo的固定4P座／安装4P螺钉插头配置可切换装配；±180°为查看范围，不是额定机械限位。官方未提供该附件工程图，局部尺寸与插入深度为照片推导，HT3.96-4P名称不证明厂牌通配。

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

同一 Module 实例再次 `attach` 到原接口是幂等操作；挂到另一兼容接口时会从旧口安全转移，保留实例状态和资源。兼容性与循环挂载检查发生在装配变更前。同步生命周期回调不能重挂正在装卸的同一实例或正在挂载的目标口，也不能拆卸正在挂接的新实例；这些操作会抛错，应等当前调用结束后再发起下一次装配（例如使用 `queueMicrotask`）。替换目标口旧实例时的正常拆卸不受影响。默认 `detach()` 销毁实例；需要缓存时使用 `detach({dispose:false})`，最终由调用方销毁。

拆卸前会沿原宿主链同步发出 `module:will-detach`，事件载荷为 `{port,module}`。此时旧路径和父子关系仍有效，适合取消将被移除子树中的外部输入；它是生命周期事件，不是新的 `input` action。查看器与 demo 只取消各自持有的输入，无关按钮继续保持。外部框架创建的 hold 应由该框架取消，并在更改父链前完成配对；取消使用 `button.cancel(source)`，不会产生 click。

同一 Viewer 重复 `mount(host)` 不重复订阅或更新；跨 Viewer 挂载会先解除旧 Viewer 的归属。`unmount` 取消旧 Viewer 持有的键盘/指针输入，但不销毁模型。若下游缓存带有持续运动的模型，需自行决定卸载时是否 `set({rpm:0})`；demo 切换模型时会停止连续轴，返回缓存时保持停止。

demo 的异步 Unit 加载在切换模型、接口或 Unit 后会作废旧请求，未挂载的过期实例会释放。连接刷新保留仍有效的按键检查位置和 LED 选位；DOM 控件被替换时取消其输入，明确的“保持按下”只在目标仍存在且仍被选中时保留。

## 修改后验证

从仓库根目录运行 `npm run check`、`npm run build`、`./manage.sh status`。专项测试覆盖真实帽位移/方向/回位、固定根部弯曲、刚性杠杆、多键与多旋钮、稳定档位、多来源取消、关节父子装配、静止与终帧、目录内Unit线缆端点与默认姿态穿壳。另检查所有真实主机Grove口、CoreS3 DinBase及StackChan组合姿态中的插头坐标与渲染线管表面轨迹；覆盖数以当前生成报告为准。

生命周期专项为 `scripts/check-port-lifecycle.mjs`、`scripts/check-viewer-lifecycle.mjs`、`scripts/check-demo-lifecycle.mjs`，已接入正常检查。Viewer 专项运行真实查看器与输入路由，以无 GPU renderer 和 DOM 边界替身检查所有权和取消顺序；这些替身不提供浏览器视觉证据。

还需打开 demo，实际操作按键按住/回弹、模型快捷键与表单焦点、连接/断开、端点旋转、风叶转动、摇杆倾斜与按压、StackChan 组合姿态。Node 几何测试不能替代浏览器画面，也不能证明下游模拟器、真实硬件、机械配合或硬件限位正确。

## 正式栅格贴纸

正式贴纸默认启用，`artwork: false`关闭本批栅格层。七款Unit另提供显式`stickerVariant: 'education-cn'`；独立模型与Grove模块分别传选项，父主机选项不自动传播。贴图固定于真实壳体、盖、帽或关节，外部框架无需逐帧重设贴纸坐标。覆盖、缺面、位图精度和许可边界见[贴纸记录](STICKER-COVERAGE.md)。旧照片裁切保持关闭。

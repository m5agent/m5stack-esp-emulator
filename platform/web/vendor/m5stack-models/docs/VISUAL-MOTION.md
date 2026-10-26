# 外部驱动的机械姿态

`VisualJoint` 只保存和绘制外部框架指定的机械姿态。默认角度0、转速0，不自行转动。`update(dt)` 的 dt 单位是秒；它只推进明确请求的视觉过渡或旋转。没有加入 PWM、舵机控制、寄存器、I2C、编码器计数、ADC、电气响应或传感器反馈。

Roller485 U182 标准滑环版使用 `rotor` 连续轴，模型 `+Y` 为转盘顶部。转盘、外转子、顶端 PCB/Grove 与单红灯随轴运动，底部 OLED、弹舌按键和固定连接器保持原位。`grove-top` 下挂接的子模块使用该移动端口坐标；原有 `grove` 为固定输入。`press` 通过原生塑料弹舌的可逆顶点形变显示 0.25 mm 估计压程，不以隐藏点击面的位置冒充真实壳体运动。轴的 `rpm` 只驱动画面，不对应额定转速、扭矩或编码器计数。

```js
import {StackChan, FanUnit} from 'm5stack-models.js';

const robot = new StackChan();
robot.handle({type:'joint', target:'yaw', angleDeg:35, durationMs:400});
robot.get('pitch').set({angleDeg:30, durationMs:400});

const fan = new FanUnit({propeller:true});
fan.get('rotor').set({rpm:120});
// 外部渲染循环逐帧调用：
fan.update(1 / 60);
fan.get('rotor').set({rpm:0});
```

## 命令与状态

所有关节的 kind 为 `joint`，可用 `device.list('joint')` 枚举；Module 挂载后可用 `host.get('unit/rotation')` 等嵌套地址。旧 Device/Module 入口、已有按钮、显示器和端口 ID 保留。

| 调用 | 效果 |
| --- | --- |
| `joint.set({angleDeg:30})` | 立即显示明确给定的角度，并停止先前转速/过渡 |
| `joint.set({angleDeg:30,durationMs:500})` | 从当前视觉角度线性过渡500ms；不自动推测最短路径或加速度 |
| `joint.set({rpm:60})` | 仅连续轴接受非零rpm；60rpm在1秒内转360° |
| `joint.set({rpm:0})` | 停止连续运动/未完成过渡，保持当前姿态，无自动滑行 |
| `joint.setAngle(deg,ms)` / `joint.setRPM(rpm)` | 上述调用的便捷方法 |
| `host.handle({type:'joint',target:'rotation',…})` | 同样的外部命令路径 |
| `joint.getState()` / `handle({type:'state',target:…})` | 返回下述视觉状态 |

```ts
type JointState = {
  angleDeg: number;
  targetAngleDeg: number;
  rpm: number;
  transitioning: boolean;
  mode: 'continuous' | 'position';
  continuous: boolean;
  rangeDeg: [number, number] | null;
  visualRangeDeg: [number, number] | null;
  demoRpmMax: number;
};
```

`rangeDeg` 是这个模型实际接受的角度区间，超出时抛 `RangeError`。`visualRangeDeg` 只是查看器滑条建议，不声明硬件限位；null 表示该模型没有施加已知绝对角度限位。`demoRpmMax` 只是便于观察的演示速率。`meta.axisEvidence`、`meta.rangeEvidence` 记录依据与约定。轴方向遵循右手规则。

输入必须有限，durationMs和dt不能为负；只有显式 continuous 轴接受非零rpm。非零rpm与带时长的目标角度不能在同一命令内并行。无效命令先验证再修改状态。过渡最后一帧的 `update()` 返回true以请求绘制精确终点，下一空闲帧返回false。

## 已接入的实体

| 产品 / ID | 真实可动实体与轴 | 范围 / 建议 |
| --- | --- | --- |
| StackChan `yaw` | 颈部机构和头的整体绕+Y转，底脚与base-usb固定 | 官方水平360°无限旋转；demo≤20rpm |
| StackChan `pitch` | 头壳、CoreS3、LCD、头部PCB/端口、左右联接件绕-X转 | 接受0…90°，0是现有正视姿态，正角抬头；官方确认总行程90°，绝对硬件零位未确认 |
| RollerCAN U188 `rotor` | D3504外转子、扩展盘、顶部PCB/Grove/红灯绕+Y转，下级Unit与线缆同帧随动 | 连续外驱；底部OLED、固定CAN/Grove及原生弹舌不转；`press`对真壳顶点形变 |
| RollerCAN Lite U188-Lite `rotor` | 裸D3504外转子绕+Y转 | 连续外驱；无顶部Grove，底部OLED/固定座/原生弹舌保持，动作不驱动CAN或电机物理 |
| Vibrator U059 `rotor` | 实际外露金属偏心轮绕电机输出轴转 | 连续外驱；默认静止，不自动抖动外壳/线缆，不换算振幅或PWM |
| Fan `rotor` | +Y轴上的实心输出轴；`propeller:true`时连同60mm双叶和轮毂 | 默认裸轴；只有外部给rpm后才转；demo≤240rpm |
| Encoder `rotation` | 整个带肋旋钮绕+Z转 | 连续轴；保留原 `press` 真帽压放；demo≤60rpm |
| Angle `rotation` | 电位器旋钮绕+Z转，底座不动 | 仅绝对角度；viewer建议−150…150°；官方机械总转角/零位未确认 |
| Light U021 `trim` | 位置`[0,2.5,3.72]` mm上的金属微调头绕+Z转，蓝色座和光敏电阻固定 | 位置式，不接受非零rpm；viewer建议−135…135°，额定机械限位/旋向/电气零位未确认 |
| Joystick `tilt-x`, `tilt-y` | 真实摇杆/帽在座口附近分别绕X/Y倾斜 | viewer建议每轴−20…20°；实际机械限位未确认；原 `press` 沿倾斜后的杆轴压放 |
| Joystick2 U024-V2 `tilt-x`, `tilt-y` / `press` | 原生红帽、柄和球体绕局部X/Y倾斜，Z按压沿倾斜后的杆轴，固定座和导光件不动 | 接受每轴−18…18°，0.4 mm帽行程；均为视觉估计，不代表霍尔标定或额定限位 |
| ByteSwitch U191 `switch-1`…`switch-8` | 八个独立钮子杆绕局部+Y摆动，固定开关座保持 | 稳定Button，`setPosition(0\|1)`切档；两档±22.5°为照片推导，不实现位图/DPDT通断 |
| ByteButton U192 `press-1`…`press-8` | 八个独立实体帽沿−Z压下与回弹，壳和LED导光体保持 | 瞬时Button，0.2 mm行程为视觉估计；支持独立输入来源和取消复位 |
| 8Encoder `rotation-1`…`rotation-8` | 八个独立带肋空心旋钮绕+Z转 | 连续外驱；各自 `press-1`…`press-8` 沿局部−Z压放0.35 mm，行程为外观估计 |
| Fader `slider` | 实体帽、杆和滑架沿+Y移动，轨道固定 | `kind:'slider'`，以毫米设置 `positionMm`；范围−17.5…17.5 mm，中位0；松手保持位置，不换算电阻或ADC |
| 8Angle `rotation-1`…`rotation-8` / `switch` | 八个帽与轴各绕+Z转；开关沿+X在两档间移动 | 旋钮接受−140…140°且拒绝非零rpm，280°总转角依据官方图，中位不是ADC零点；开关为稳定Button，2.2 mm档距为外观估计 |
| PaHUB v2.1 `dip-1`…`dip-3` | 三个独立拨码帽沿+X在两档间移动，开关座固定 | 稳定Button，`setPosition(0\|1)`；松手保持档位，0.9 mm档距为照片推导，不计算地址或I2C通道 |
| Scroll `rotation` | 官方原始滚轮与轴绕+X转 | 连续外驱；`press` 将轮与轴端插入件作为共同按压组，沿机身−Z压0.25 mm，隐藏支撑机理未确认 |
| 2Relay / 4Relay `terminal-N/screw-1`…`screw-4` | 随附4P插头内各自真实带槽螺钉头绕插入轴转 | 默认空座，`terminalPlug:true`装全部；只外驱头部角度，不模拟螺纹/夹线/触点通断；单独卸插头保留固定座和Grove线 |
| DMX U183 `termination` / `xlr-release` | 真实终端滑块保持两档，XLR PUSH释放片沿实际局部轴压放 | 稳定Button与瞬时Button，行程为照片推导；不模拟终端电阻或锁线 |
| CAN U085 `terminal/screw-1`…`screw-4` | 随附4P插头内各自真实带槽螺钉头绕插入轴转 | 默认空座，`terminalPlug:true`装入；仅头部角度，不模拟螺纹/夹线/电气隔离或CAN收发 |
| Relay `terminal/screw-1`…`terminal/screw-3` | 可拆3P插头中各自带工具槽的螺钉头绕局部轴转 | 仅位置式角度；demo ±180°不代表额定限位，不模拟螺纹升降、夹紧或触点通断；拆除`terminal`后这些路径随附件移除 |
| RS485 U034 `terminal/screw-1`…`terminal/screw-4` | 随附4P插头中B/A/12V+/12V-各螺钉头绕局部+Z转 | 默认空座，`terminalPlug:true`或产品`TerminalPlug`附件安装后出现；只外驱角度，不模拟螺纹、夹线或通信/供电 |
| Weight-I2C U180 `terminal/screw-1`…`terminal/screw-4` | 随附4P插头中A+/A−/E−/E+各螺钉头绕局部+Z转 | 默认空座，`terminalPlug:true`安装；仅位置式角度，demo ±180°不是机械限位；不模拟螺纹、夹线、激励或称重 |
| 8Servos U165 `terminal/screw-1`…`terminal/screw-4` | 随附4P插头中HPWR/GND/GND/5V各螺钉头绕局部+Z转 | 默认空座，`terminalPlug:true`安装；仅位置式角度，demo ±180°不是机械限位；不模拟螺纹、夹线、供电或PWM |

Fader的毫米位置命令、拖动与输入取消见[Agent接入](AGENT-INTEGRATION.md)；PaHUB拨码和六口挂接见[多接口Unit](MULTIPORT-UNITS.md)。Weight-I2C与8Servos的可拆插头、路径前缀及生命周期见[可拆端子](UNIT-TERMINALS.md)。

Joystick2与Byte系列的详细多级连接见[可动输入Unit](INTERACTIVE-INPUT-UNITS.md)。

Relay与DMX的多插头、滑块和释放片见[Relay与DMX](RELAY-DMX-UNITS.md)。

CAN端子与固定传感器的边界见[CAN与环境/测距Unit](CAN-ENV-TOF-UNITS.md)。

RollerCAN标准/Lite与Vibrator的真实随转件和接线见[旋转Unit](ROTATING-UNITS.md)。

StackChan前侧Power板属于pitch，下端Adapter属于yaw，七根实体线束的两端跟随各自装配坐标。后部真实开放，底座USB保持固定。隐藏舵机包装和线束路线为外观近似，不声明实物制造配合。

旋钮/摇杆按压继续使用既有 Button API，例如 `button('press').press('framework')` 与对应 `release('framework')`。按钮记录的是输入意图和帽的位置，不生成编码器脉冲、摇杆ADC或按键寄存器。StackChan的 `power`/`reset` 保留原ID，继承CoreS3真正的可动帽并跟随头部姿态。

## Light微调头

U021官方原理图确认R3为10K可调电阻，正面照片可见蓝座中的金属工具槽。`trim`只驱动该实体头；半径1.5 mm、槽深0.32 mm、局部座位和蓝色座尺寸均为照片估计，工具槽保留真实凹腔。`visualRangeDeg=[-135,135]`是demo范围，`rangeDeg=null`，不声明270°额定转角、转数、端挡或电气零位，也不换算电阻/光强阈值/LM393输出。

```js
import {loadModel, loadGroveModule} from 'm5stack-models.js/loaders';

const light = await loadModel('light');
light.get('trim').set({angleDeg:45});

const host = await loadModel('sticks3');
host.port('grove').attach(await loadGroveModule('light', {cableLength:70}));
host.handle({type:'joint',target:'grove/trim',angleDeg:-45});
```

## 弯曲片与杠杆按压

Button U027直接分离原CAD的10.2 mm按压片，保留U形开口和三条凹槽；固定根部不动，自由端向内弯曲0.35 mm。这个平滑形变只描述外观，不计算塑料刚度。Dual Button U025使用直径11.5 mm、3 mm高的闭合实体彩帽，两中心相隔14 mm；官方机械图区分8 mm基壳、12 mm白座、15 mm含帽总厚，0.35 mm按压行程为估计。

Limit U145的16 mm金属柄绕固定Z铰链转动，并带动接触柱。静止8°到按下0°是照片推导的观察姿态，尚未获额定行程机械图确认。它是 `Button` 子类，调用 `button('press').press(source)` / `release(source)`；`getState().leverAngleDeg` 仅表示当前视觉角度。

Key U144 的红色空心键帽与青色轴芯同属 `press`，沿−Z压放1.6 mm；透明固定轴壳保持不动。该行程为外观估计。8Encoder各帽在真实盲轴孔上独立压放，`switch` 是保持档位的滑块；两款RGB均由外部单独指定，不随按压改变。

上述非直线组件继承多来源持有、取消和嵌套寻址。用 `getActuationState()` 读取 `{depthMm,targetDepthMm,settled}`：depth是供外观插值的标量，杠杆会把它换算成弧形姿态，因此不能把 `cap.position` 当成统一运动测量。检查见 `scripts/check-unit-actuators.mjs`、`scripts/check-limit-lever.mjs` 和 `scripts/check-cardkb.mjs`。

## 创建新的关节

```js
import {VisualJoint} from '../core/components/VisualJoint.js';
const joint = host.add(new VisualJoint({
  id:'rotation', label:'Moving cap',
  position:[0,7,6], axis:[0,0,1], continuous:true,
  meta:{axisEvidence:'Product drawing …', demoRpmMax:60}
}));
joint.adopt(capGroup); // mount之后，将中性姿态实体归到轴下；保留当前世界姿态
```

用独立 Object3D 组归属真实移动零件。两个轴嵌套时先构造/挂载各关节，再让外轴 `adopt(inner.object3d)`；不要移动外壳上的固定座、接口或接触平面。`adopt` 不应在非中性姿态反复重绑部件。

## 依据与验证

StackChan轴线/分组、原孔盖座和舵机轮廓/输出轴事实见 `source-manifest.json` 的 `motionStructures` 与 StackChan 产品的 `movingAssembly`、`coverSeatReview`、`servoOutlineReview`；原始变换记录见 `src/devices/stackchan/cad-map-motion.json`。Angle/Joystick/Light的精确机械限位和硬件零位仍未确认。

```sh
node scripts/check-visual-motion.mjs
node scripts/check-stackchan-assembly.mjs
```

检查覆盖按需渲染终帧、显式转速/停止、转轴层级、固定底座、真实帽压放、倾斜后的局部压轴、部件与端口刚性跟随、Module嵌套调用和销毁。浏览器动态视图、实物机械限位和实机行为须分别验证；本层只提供几何。

StackChan 隐藏舵机配合另用 `node scripts/check-stackchan-servo-fit.mjs` 输出数值诊断。当前结果为 `fit-unresolved`，加 `--strict` 时以2退出；正常运动检查通过不代表该机械配合通过。运行装配已按两组原STL孔轴将白盖、灰盖相对cradle注册，并采用官方顶视支持的不等半径齿轮盖轮廓；小半径、深度、隐藏台阶、Adapter板形和线束路线仍含推导。`--candidate-xy` 现在只临时对已注册盖座施加先前被拒绝的独立PDF XY偏移，结束后恢复运行变换；该扰动破坏原孔同轴关系，不是当前已合入的盖座修正。全局cradle/head定位及right fixture轴向座位仍是未合入候选，隐藏电机/板件安装继续待确认；未缩小电机、切削原壳或移动关节轴来掩盖干涉。数值结果见 `artifacts/stackchan-servo-fit-check.json`，该诊断不作制造配合验收。

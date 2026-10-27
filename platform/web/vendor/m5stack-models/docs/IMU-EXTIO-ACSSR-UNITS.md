# Mini IMU / EXT.IO2 / ACSSR

本批提供独立`Model`和含实体四芯线的`GroveModule`，坐标为毫米、+X右/+Y上/+Z正面。每款同时加入对应贴纸，使用同型号官方照片准确绘制PNG并标记`reference-redraw`；原始照片、私有表、矢量、生成器和中间件不分发。

| ID | 型号与真实实体 | 组件边界 |
| --- | --- | --- |
| `mini-imu` | U095，24×24×8 mm；完整原壳、PCB、MPU6886/稳压与电平转换封装 | `grove`、`sensor`视觉锚点；无虚构灯、按键或传感器数值 |
| `extio2` | U011-B；模型轴24×32×10.2 mm；原壳、PCB、STM32F030、真实2×5弯针 | `io`为10针物理接口，`sensor`纯锚点；不因IO能驱动RGB/舵机而虚构板载灯/电机 |
| `acssr` | U139；80×45×31 mm规格对应SSR与控制板套件，控制器原壳不拉伸替代整套 | 真实瞬时`button`，`rgb`、控制板固定红`power-led`、SSR固定红`ssr-led`独立外驱；两端可拆4P端子 |

外部框架负责IMU数据、GPIO/ADC/PWM、设备状态、I2C/RS485/Modbus和电气。模型只提供外观、输入意图与物理接口坐标；Grove多分支示例只证明几何挂接和寻址，不证明HUB能执行相应协议。Mini IMU不注册虚构的传感器读取API；EXT.IO2内部SWD仅按真实可见结构建模，未虚构外部插口。

```js
import {loadModel, loadGroveModule} from 'm5stack-models.js/loaders';

const host = await loadModel('sticks3');
const hub = await loadGroveModule('hub', {cableLength:60});
host.port('grove').attach(hub);
hub.port('grove-1').attach(await loadGroveModule('mini-imu', {cableLength:65}));
hub.port('grove-2').attach(await loadGroveModule('extio2', {cableLength:80}));
hub.port('grove-3').attach(await loadGroveModule('acssr', {
  cableLength:95, terminalPlug:true,
}));

// 外部输出不回送按键输入，也不自动改变其他指示灯。
host.get('grove/grove-3/rgb').set({color:'#37c98b', brightness:.6});
host.get('grove/grove-3/power-led').set({brightness:.3});
host.get('grove/grove-3/ssr-led').set({brightness:.45});

// 真实帽的压放/取消与下游输入意图；不在模型内切换负载或工作模式。
const button = host.get('grove/grove-3/button');
button.press('external-ui');
host.update(.2);
button.cancel('external-ui'); // 回到原位，不发click
host.update(.2);

const acssr = hub.port('grove-3').module;
acssr.port('terminal-1').module.get('screw-1').set({angleDeg:45});
const saved = acssr.port('terminal-1').detach({dispose:false});
acssr.port('terminal-1').attach(saved); // 另一端子和Grove线保留

host.handle({type:'pose', target:'grove/grove-3/unitFrame',
  position:[45,120,8], rotation:[.1,-.2,.15]});
host.handle({type:'cable', target:'grove/grove-3/cable',
  slack:12, bend:[0,0,-1]});
host.dispose();
```

demo配置可切换“固定4P座”与“安装两只4P螺钉插头”。ACSSR 默认空固定座，`terminalPlug:true`安装包装内两只4P插头。产品入口导出的`TerminalPlug`也可手动装到`terminal-1`/`terminal-2`，全局别名为`AcSsrTerminalPlug`。插头`screw-1`…`screw-4`只接受外部头部角度；螺钉查看角度不表示螺纹升降、夹紧力或额定机械行程。固定红灯保持真实颜色，按键不自动联动任何灯或SSR状态。

EXT.IO2的`io`类型为`header-2x5-2.54mm-male`。ACSSR本体`ssr-screw-1`…`ssr-screw-4`对应四个真实端子螺钉，其中上两为负载、下两为控制输入；ID编号不表示四个端子都是负载。

`io`和端子使用各自真实连接器类型，拒绝Grove模块；接口类型只约束本库几何配对，不作为实物电气兼容判断。PCB、隐藏安装、连接器内构和按键行程的照片推导范围见各产品research。

```js
const bare = await loadModel('acssr', {artwork:false});
const wiredBare = await loadGroveModule('mini-imu', {artwork:false});
```

贴纸依附对应实体。只有实物连续贴膜跨原生服务口时使用薄膜；关闭贴纸保留原孔与后方PCB/封装。每个模块分别传`artwork`选项，父主机选项不自动传播。

必要检查为`node scripts/check-imu-extio-acssr-units.mjs`，覆盖三个真实产品、四芯装配、被动锚点、10针类型、独立灯、按压取消回位、两端子/八螺钉、贴纸开关与实体缓冲/姿态不变、独立拆离。canvas与连接类型探针为Node边界替身；未做逐面浏览器、全量目录或硬件验收，阶段保持`modeled`。

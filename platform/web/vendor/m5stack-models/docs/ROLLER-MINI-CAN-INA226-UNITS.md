# Roller485 Lite / Mini CAN / INA226-10A 接入

2026-10-26。本批U182-Lite、U179、U200均导出 `Model` / `GroveModule` / `TerminalPlug` / `spec`，保留真实四芯Grove、固定端子及随附可拆四螺钉插头。模型只负责实体外观、输入意图和外驱形状，电机控制/反馈、串口/CAN/I2C、电流电压功率、保护和电气由外部框架实现。

| 产品ID | SKU | 主要外部接口 |
| --- | --- | --- |
| `roller485-lite` | U182-Lite | `grove`、`pwr485`、`debug`、`press`、`lcd`、`rgb-1` / `rgb-2`、`rotor` |
| `mini-can` | U179 | `grove`、`terminal`，非隔离TJA1051T/3 |
| `ina226-10a` | U200 | `grove`、`terminal`，10A本款隔离/分流实体 |

毫米尺度，三款的轴向、厂商名义尺寸、原壳包络与含固定端子的实际包络分别见各 `dimensions.js`、`cad-map.json` 和研究记录。Mini CAN完整原壳24×32×8mm、含固定端子24×32×10.2mm。INA226原壳24×56×8mm、含端子24×58×10.2mm，端子伸出量含安装推导；厂商58mm长度与所链56mm壳图的归属澄清反馈为 `692e32ec722240559336c5c6fb24a03f`。Roller485 Lite官方标称40³、本款原壳/电机装配包络分别记录，生产装配基准缺失反馈为 `b6a2e2bf5b174a788c7be66dab54c907`；该反馈不宣称厂商40mm一定错误。保留本款完整原壳，不以缩放消除名义值与实体装配的差异。隐藏安装、板位、插头配合和局部封装仍含记录在案的外观推导，数字检查不表示制造公差或实物配合。

## 三分支四芯连接

```js
import {loadModel, loadGroveModule} from '../src/loaders.js';

const host = await loadModel('sticks3');
const hub = await loadGroveModule('hub');
host.port('grove').attach(hub);
const motor = await loadGroveModule('roller485-lite', {terminalPlug: true, cableLength: 65});
const can = await loadGroveModule('mini-can', {terminalPlug: true, cableLength: 80});
const meter = await loadGroveModule('ina226-10a', {terminalPlug: true, cableLength: 95});
hub.port('grove-1').attach(motor);
hub.port('grove-2').attach(can);
hub.port('grove-3').attach(meter);

host.handle({type: 'pose', target: 'grove/grove-1/unitFrame',
  position: [0, 165, 8], rotation: [.1, -.2, .15]});
host.handle({type: 'cable', target: 'grove/grove-1/cable',
  slack: 12, bend: [0, 0, -1]});
```

每支线渲染四根导线与两端插头。`unitFrame`改变本体姿态，`cable`只改变线形。标签只记录实际接口，挂接不会建立电源、RS485、CAN或I2C行为。Mini CAN与INA226没有虚构的按钮、灯、转子或数值传感器锚点。

## Roller485 Lite：旋转、压放与屏幕

Lite采用本款固定底壳、实际3504电机/转子和单HT3.96插座，不套用CAN Lite的双插座或标准Roller485的滑环输出。`rotor`只带真实旋转件；固定壳体、PCB、Grove、PWR485、debug及OLED不跟随转动。没有 `grove-top` 或顶部乐高扩展接口。

```js
host.handle({type: 'joint', target: 'grove/grove-1/rotor', rpm: 12});
host.update(1 / 60);
host.handle({type: 'joint', target: 'grove/grove-1/rotor', angleDeg: 90, durationMs: 200});
host.update(1 / 60);
host.handle({type: 'joint', target: 'grove/grove-1/rotor', angleDeg: 0, rpm: 0});
host.handle({type: 'led', target: 'grove/grove-1/rgb-1', color: '#48a2ff', brightness: .4});
host.handle({type: 'display', target: 'grove/grove-1/lcd', fill: '#dedede'});
```

外驱RPM只积分视觉角度；角度过渡和RPM不同时启用。不生成FOC、编码器反馈、电流/速度环、负载、扭矩或真实电机能力。两颗RGB可独立外驱，默认关闭，不随旋转、接线或OLED联动。`lcd`接外部64×48 framebuffer，按白色单色OLED渲染，不自带菜单或设备状态。

`press`对应真实原壳舌，压下时变形原壳顶点，释放/取消后恢复原始位置和法线；只发输入意图，不执行配置菜单。

```js
host.on('input', event => {
  // event.id uses the full mounted path, for example grove/grove-1/press.
});
motor.button('press').press('controller');
host.update(1 / 60);
motor.button('press').release('controller');
// On pointer/device cancellation, use cancel with the same source instead.
```

## 三款随附端子插头

默认构造保留裸座，`terminalPlug:true`装入本款随附 `TerminalPlug`。Roller485 Lite的端子ID是 `pwr485`，另两款是 `terminal`；均为 `ht3.96-4p`，不接受Grove模块。

四枚 `screw-1`…`screw-4`可分别外驱 `angleDeg` / `durationMs`，拒绝非零RPM。仅改变螺钉头方向，不表示压线行程、扭矩或电气连接。

```js
host.handle({type: 'joint', target: 'grove/grove-2/terminal/screw-1',
  angleDeg: 45, durationMs: 120});
host.update(1 / 60);
const plug = can.port('terminal').detach({dispose: false});
can.port('terminal').attach(plug);
```

插头及其四枚螺钉一起拆装，不改变固定座、本体Grove和兄弟分支。Mini CAN保留真实TJA1051T/3、稳压器/电感；INA226-10A保留本款隔离电源、I2C隔离封装、5mΩ分流及保险丝，不套用1A款。内部LED若没有确认外露光路，仅建封装实体，不伪造外部发光接口。

## 同步印刷、开关与释放

本批7张PNG：Roller485 Lite三张与Mini CAN两张为本款官图代码重绘 `reference-redraw`；INA226-10A正背两张为精确本款原稿恢复的 `source-vector-raster`。确切数量与配准以单品冻结记录和本批进度为准。只采用机身稿，排除包装或其他版本，不裁产品照片、不编造不可辨文字。原表、私有链接/映射、原稿名、矢量、生成器和中间件留在仓库外。

各入口传 `artwork:false`关闭印刷，原壳、PCB、封装、真实开口/腔壁、胶贴物理载体、插头及所选配置保持。贴纸不替代结构背衬。必要专项 `node scripts/check-roller-mini-can-ina226-units.mjs`覆盖实际三分支四芯、转子/固定件归属、按键压放取消、独立灯及OLED、三只四螺钉插头、端口类型与内部命令边界、各配置印刷全物理attributes/index/world matrix一致性。来源及单品smoke在对应研究目录，综合范围见[本批进度](../artifacts/roller-mini-can-ina226-expansion/progress.json)。

通过 `hub.port('grove-2').detach()`可独立释放Mini CAN分支。使用 `detach({dispose:false})`保留的模块由调用方重新装入或释放；`host.dispose()`释放仍挂载的整个装配树。

总入口别名为 `Roller485LiteUnit` / `Roller485LiteUnitModule` / `Roller485LiteTerminalPlug`、`MiniCanUnit` / `MiniCanUnitModule` / `MiniCanTerminalPlug`、`Ina22610aUnit` / `Ina22610aUnitModule` / `Ina22610aTerminalPlug`。保持 `modeled`，没有逐面浏览器、全量历史或实物验收。

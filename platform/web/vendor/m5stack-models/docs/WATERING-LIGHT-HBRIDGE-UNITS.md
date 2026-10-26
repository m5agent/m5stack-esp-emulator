# Watering / HBridge v1.1 / DLight 接入

2026-10-26。本批新增U101、U160-V11、U136。三款提供`Model`、`GroveModule`、`spec`、四芯`grove`与被动`sensor`。模型负责真实外观、配件形状、可见控件和输入意图；水、湿度、电机、PWM、保护、lux、协议和电气行为由外部框架实现。

| 型号 | 模型轴名义尺寸 mm | 真实结构与形状能力 |
| --- | --- | --- |
| `watering` U101 | 26.5×192.8×33 | 完整泵/探针组件、电容极板、进出水口；可拆双软管及外驱管线形状 |
| `hbridge-v11` U160-V11 | 24×56×10.2 | 四芯固定座/插头/四螺钉，可选470µF电容；壳内电源选择器和四位DIP，开盖配置可观察 |
| `dlight` U136 | 24×32×8 | 完整壳、光学窗口、透明BH1750FVI封装/PCB；无灯/按钮/可动件 |

采用+X右、+Y产品顶部、+Z正面。厂商尺寸顺序见各款`dimensions`；Watering原生壳约24×112×32.973，与完整26.5×192.8×33探针装配分开记录，柔管另列包络。端口、芯片、内部背衬与PCB是物理几何，贴纸不遮缺件。隐藏安装、管口/软管尺寸、组件布局和附件配合保留明确外观推导，未称制造配合或额定机械行程。

## 四芯三分支连接

```js
import {loadModel, loadGroveModule} from '../src/loaders.js';

const host = await loadModel('sticks3');
const hub = await loadGroveModule('hub');
host.port('grove').attach(hub);
const watering = await loadGroveModule('watering', {hoses: true, cableLength: 65});
const bridge = await loadGroveModule('hbridge-v11', {
  covers: false, terminalPlug: true, capacitor: true, cableLength: 80,
});
const light = await loadGroveModule('dlight', {cableLength: 95});
hub.port('grove-1').attach(watering);
hub.port('grove-2').attach(bridge);
hub.port('grove-3').attach(light);

host.handle({type: 'pose', target: 'grove/grove-1/unitFrame',
  position: [0, 160, 8], rotation: [.1, -.2, .15]});
host.handle({type: 'cable', target: 'grove/grove-1/cable',
  slack: 12, bend: [0, 0, -1]});
```

每个分支实际渲染4根线。`unitFrame`控制产品姿态，`cable`控制线缆形状。拆除一支保留兄弟分支；`host.dispose()`释放装配树。使用`detach({dispose:false})`保留配件后，调用者负责重新装入或释放。

## Watering：双软管与真实泵体

`inlet`和`outlet`均为`silicone-tube-4mm`机械口，拒绝Grove模块。默认构造不装管；`hoses:true`给两口各安装独立`Hose`。产品入口导出`Hose`，总入口别名为`WateringHose`。配置菜单第一项`supplied-hoses`带双管，第二项裸组件。

软管组件`shape`接受外部指定的毫米中心线，坐标属于当前水口的Module局部帧。要求3…16点、各轴位于±500mm；首点固定`[0,0,0]`，第一段沿+Y且至少6mm，相邻点至少相距1mm。实际管壁与两端开口保留：

```js
host.handle({type: 'shape', target: 'grove/grove-1/inlet/shape',
  points: [[0, 0, 0], [0, 18, 0], [15, 42, 8], [26, 75, 12]]});
const hose = watering.port('inlet').detach({dispose: false});
watering.port('inlet').attach(hose);
```

`shape.getState()`包含当前`points`、内外径、壁厚、曲线长和坐标说明。外径6mm/内径4mm/壁厚1mm、默认曲线路径和套接深度是官图推导的外观参数，不能视作原厂管长或装配标定。无效点集拒绝后保持旧几何；修改进水管保留泵体、极板、出口管和Grove帧。

Watering使用电容式极板；泵和传感板各自存在。隐藏转子不生成外露关节，模型不渲染水流、不自动抖动，也不根据湿度启动泵。`sensor`不接受水泵/湿度/ADC命令，没有可见LED或实体按钮。

## HBridge v1.1：闭壳、开盖和可拆端子

严格使用U160-V11的STM32F030/RZ7899/INA199及电源组件。`terminal`是`ht3.96-4p`，实际位置标记为HV、G、M−、M+；标签只说明物理位置。`terminalPlug:true`安装随附四螺钉插头；`capacitor:true`需要同时开启插头，把470µF电容跨装在同一插头前两槽，不生成额外插口或电气连续性。电容条纹、端盖与引线用物理几何表现。

产品入口导出`TerminalPlug`，总入口别名为`HbridgeV11TerminalPlug`。`terminal/screw-1`…`screw-4`只外驱真实头部角度，支持`angleDeg`/`durationMs`，拒绝非零RPM；不表示扭矩、轴向螺纹、压线或极性。

```js
host.handle({type: 'joint', target: 'grove/grove-2/terminal/screw-1',
  angleDeg: 45, durationMs: 120});
host.update(1 / 60);
```

`source`和`address-1`…`address-4`保留裸板上的真实位置，分别为电源选择器和四位稳定DIP。它们位于外壳内部；闭壳不接受穿壳指针输入，外部仍可设置真实档位。`covers:false`隐藏原生壳的显示层供装配检查，原壳数据保持，露出真实控件后可按压/释放/取消。配置菜单同时保留闭壳裸座、插头、插头+电容和开盖检查形状。

```js
host.handle({type: 'button', target: 'grove/grove-2/source',
  action: 'position', position: 1});
host.handle({type: 'button', target: 'grove/grove-2/address-1',
  action: 'position', position: 0});
host.on('input', event => externalFramework.receive(event));
```

0/1仅是稳定物理档位；释放后保留档位，取消输入发送取消的`up`并省略`click`。外部设置档位不回送输入，不计算地址、电源电压、PWM、前进/后退、制动、释放或保护。每帧调用`host.update(dt)`推进形状插值。本款未确认外露灯，没有虚构电机或发光控件。

## DLight与同步贴纸

DLight是U136数字环境光检测Unit，保留原生光学开窗，后方有真实透明BH1750FVI封装及PCB背衬。它接收光，不发光；没有光束、lux读数或光学模拟。P1/P2只作隐藏焊盘实体，不增造用户接口。只有`grove`及被动`sensor`。

本批同步5张PNG：Watering机背精确原稿恢复栅格1张`source-vector-raster`，转换丢失的fill按对应预览恢复并保留原轮廓；电机铭牌可辨部分另重绘1张，不编造模糊小数值行。HBridge正背2张和DLight背面1张均为对应型号官图代码重绘，共4张`reference-redraw`。原稿恢复不宣称未经修改的直接导出，配准与恢复范围见各款`docs/research/<id>/artwork`记录。

私表、私有链接、原稿名、矢量、原始官方图/CAD、生成器与中间件留在仓库外，只分发普通PNG、衍生几何及自写说明。每个模型/模块分别传`artwork:false`关闭印刷层；所有盖板、软管、插头/电容配置的物理attributes/index和世界姿态保持。

## 必要检查与入口

运行`node scripts/check-watering-light-hbridge-units.mjs`检查真实StickS3→HUB三分支四芯线、独立外驱双管、五个真实稳定控件及闭壳/开盖边界、四螺钉和电容插头、机械类型、被动锚点与配置贴图开关。单品smoke及来源冻结见各款研究目录；两构建、在线资源字节与隐私结果见[本批进度](../artifacts/watering-light-hbridge-expansion/progress.json)。

总入口提供`WateringUnit`/`WateringUnitModule`/`WateringHose`、`HbridgeV11Unit`/`HbridgeV11UnitModule`/`HbridgeV11TerminalPlug`、`DlightUnit`/`DlightUnitModule`。保持`modeled`，未执行逐面浏览器、全量历史或实物验收。公开main的85款`ad5d062`是上次Git同步快照，后续本地增量未自动再次推送。

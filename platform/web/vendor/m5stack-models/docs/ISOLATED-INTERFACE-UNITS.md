# RS485-ISO / AIN4-20mA / AC Measure 接入

2026-10-26。本批新增U094、U162、U164，各款导出 `Model` / `GroveModule` / `TerminalPlug` / `spec`，提供真实四芯 `grove` 与实际 `terminal`。只负责实体、配件装拆、外驱灯光/头角；UART/RS485、供电切换、ADC、电流电压功率、隔离和电气功能由外部框架实现。没有虚构的数值传感器、按钮或本体转子。

| 产品ID | SKU | 模型轴名义尺寸 mm | 本款真实附件与接口 |
| --- | --- | --- | --- |
| `rs485-iso` | U094 | 24×56×10.2 | `vh3.96-4p`，可拆4螺钉插头、可选120Ω终端电阻；独立外驱指示灯 |
| `ain4-20ma` | U162 | 24×56×11.3 | `ht3.96-4p`，可拆4螺钉插头、五个真实跳帽位置/占针约束 |
| `ac-measure` | U164 | 24×56×10.3 | `ht3.96-4p`，可拆4螺钉插头、实际隔离/采集封装与原稿印刷 |

毫米尺度，+X右、+Y产品顶部、+Z正面。厂商尺寸顺序、原CAD壳体与含固定座的总厚分别见 `dimensions.js` / `cad-map.json`；不要缩掉实际端子去凑壳厚。壳、PCB、实际封装、孔壁、插座/触点和深腔背衬均为物理几何；贴纸不补缺件。隐藏安装、帽/插头配合和电阻姿态保留外观推导。

## 三分支四芯连接

```js
import {loadModel, loadGroveModule} from '../src/loaders.js';

const host = await loadModel('sticks3');
const hub = await loadGroveModule('hub');
host.port('grove').attach(hub);
const bus = await loadGroveModule('rs485-iso', {
  terminalPlug: true, terminator: true, cableLength: 65,
});
const ain = await loadGroveModule('ain4-20ma', {
  terminalPlug: true, jumpers: 'three-horizontal', cableLength: 80,
});
const ac = await loadGroveModule('ac-measure', {terminalPlug: true, cableLength: 95});
hub.port('grove-1').attach(bus);
hub.port('grove-2').attach(ain);
hub.port('grove-3').attach(ac);

host.handle({type: 'pose', target: 'grove/grove-1/unitFrame',
  position: [0, 160, 8], rotation: [.1, -.2, .15]});
host.handle({type: 'cable', target: 'grove/grove-1/cable',
  slack: 12, bend: [0, 0, -1]});
```

每支Grove线实际渲染4根导线；`unitFrame`改变本体姿态，`cable`改变线形。各分支/配件独立拆装，结束时 `host.dispose()`释放装配树。用 `detach({dispose:false})`保留的配件由调用方重新装入或释放。

## 随附四螺钉插头

默认构造不装端子插头，`terminalPlug:true`装入各自本款的 `TerminalPlug`；配置菜单保留裸座/带插头形状。四枚 `terminal/screw-1`…`screw-4`仅外驱头部 `angleDeg` / `durationMs`，拒绝非零RPM，不表示轴向压线、扭矩或电气连接。

```js
host.handle({type: 'joint', target: 'grove/grove-2/terminal/screw-1',
  angleDeg: 45, durationMs: 120});
host.update(1 / 60);
const plug = ain.port('terminal').detach({dispose: false});
ain.port('terminal').attach(plug);
```

插头/螺钉外驱不回送输入，也不移动固定座、Grove帧或其他配件。端口类型精确匹配；RS485-ISO是 `vh3.96-4p`，另两款是 `ht3.96-4p`，均拒Grove模块，不因同为3.96mm就自动跨类型配对。

## RS485-ISO：隔离本体和终端电阻形状

本款保留CA-IS3082W及实际电源/PCB。端子前视物理顺序为B/A/NC/SHIELD；不套旧非隔离RS485的电源/接地定义。`terminator:true`须同时 `terminalPlug:true`，把随附120Ω电阻及两引线装在同一插头B/A入口，随该插头拆装，不新增插口或总线功能。该安装姿态含照片推导，不声称量产装配标定。

`power-led` 默认关闭，只接受独立外驱开关/亮度。固定白色是预览估计，`meta.colorConfirmed:false`，不是官方确认色值或RGB规格；重设颜色保持预览单色。它不随端子、电阻、UART或电源状态自动联动。

```js
host.handle({type: 'led', target: 'grove/grove-1/power-led', brightness: .4});
```

本款官方引用了跨SKU尺寸图，CAD确有同源几何；图归属和灯色缺证的反馈见单品来源，不把跨SKU引用直接当作尺寸错误。

## AIN4-20mA：单通道与可拆跳帽

U162是单通道4…20mA单元，保留STM32G030、HCNR200和SGM321等真实封装；不是四通道。`jumpers`可为默认 `'three-horizontal'`、`'two-vertical'` 或 `false`，只表示三横帽、两纵帽、裸针三种物理配置，不执行供电/测量功能。帽位经实际开口外露；`covers:false`仅供开盖检查，原壳数据保持。

| 跳帽Port ID | 占用物理针位 |
| --- | --- |
| `jumper-p2-12` | P2.1 / P2.2 |
| `jumper-p2-34` | P2.3 / P2.4 |
| `jumper-p3-12` | P3.1 / P3.2 |
| `jumper-p2-2-p3-1` | P2.2 / P3.1 |
| `jumper-p2-3-p3-2` | P2.3 / P3.2 |

五口均为 `pin-header-2.54-2p`，针位在 `port.meta.physicalPins` / `port.physicalPins`。产品另导出 `Shunt`，可 `new Shunt()`。占用针冲突会在修改附件前拒绝，不允许两帽同时穿过同一实体针；释放/重新安装只管理物件，不建立电路。

```js
const slot = ain.port('jumper-p2-12');
const shunt = slot.detach({dispose: false});
slot.attach(shunt);
```

切换横/纵位置前先取下冲突帽。两纵配置只安装两只帽，多余未装附件由调用方保留或释放。没有LED、按钮、本体关节或数值传感器锚点。

## AC Measure：原稿印刷与真实采集本体

完整保留STM32G030、HLW8032、B0505ST16-W5、EL357及本款PCB/端子。端子前视实际标签序为L2/N2/L1/N1，只是物理位置记录，不是接线建议。官方N1/PE表述与原理图/连接器标注存在矛盾，已提交反馈，详见单品来源；模型不把该表转成电气连接或计量行为。本体无额外灯、按钮、关节或传感器锚点，不虚构外置互感器或线。

两张机身印刷从本款精确矢量原稿恢复为 `source-vector-raster` PNG，保留原有颜色，仅修正转换导致的 `evenodd` / `nonzero`字腔填充差异。包装贴纸排除。另两款各两张 `reference-redraw`，按本款官图代码重绘，不裁产品照片、不编造不可辨文字、不用印刷遮缺件。字体、颜色、安装尺寸与配准推导以各款研究为准。

## 必要检查与导出

每个独立模型/模块传 `artwork:false`关闭印刷，保留对应盖板/插头/电阻/跳帽配置的所有物理attributes/index及世界矩阵。私表、私有链接、原稿名、矢量、官图CAD原件、生成器/中间件只留仓库外；公开最终普通PNG、衍生几何与安全来源说明。错误类别候选的拒用细节仅留私有台账。

必要专项 `node scripts/check-isolated-interface-units.mjs`覆盖真实StickS3→HUB三分支四芯、三只四螺钉插头/原位恢复、实际电阻/独立指示灯、五帽位占针/装拆和三种帽配置、各配置印刷开关、机械/内部数值功能边界。单品smoke与来源见各研究目录；综合范围见[本批进度](../artifacts/isolated-interface-expansion/progress.json)。

总入口别名：`Rs485IsoUnit` / `Rs485IsoUnitModule` / `Rs485IsoTerminalPlug`、`Ain420maUnit` / `Ain420maUnitModule` / `Ain420maTerminalPlug` / `Ain420maShunt`、`AcMeasureUnit` / `AcMeasureUnitModule` / `AcMeasureTerminalPlug`。保持 `modeled`，没有逐面浏览器、全量历史或实物验收；公开Git85款 `ad5d062`是已同步基线，后续本地增量未自动再次推送。

# BLDC Driver / RCA / Puzzle 接入

2026-10-26。本批新增U181、U155、U193。各款导出 `Model` / `GroveModule` / `spec` 和真实四芯 `grove`；三款均为实际输出/连接装配，没有虚构的 `sensor` 锚点。模型负责实体、外驱形状/灯光和输入意图，不实现电机、PWM、保护、电气、音视频、串行协议或像素自动转发。

| 产品ID | SKU | 本款尺寸口径 mm | 实体与外驱能力 |
| --- | --- | --- | --- |
| `bldc-driver` | U181 | 壳24×32×8；含固定端子24×32×11.3 | STM32G030/DRV11873、真实4P固定座、可拆四螺钉插头 |
| `rca` | U155 | 壳24×32×8；含RCA座24×36.4×14.7 | 单个RCA母座，壳内单枚双通道稳定滑钮 |
| `puzzle` | U193 | 24×24×15 | 实际8×8共64颗RGB封装、原生隔光栅格、输入/输出Grove与固定孔 |

采用毫米尺度，+X右、+Y产品顶部、+Z正面。RCA官方规格表的8mm描述壳厚，尺寸图给出含插座14.7mm，不能压扁插座去凑壳尺寸。官方CAD、完整装配包络与照片推导分别见各款 `dimensions.js`、`cad-map.json` 和研究。固定插座、PCB/封装、孔壁与深腔背衬是真实几何，贴纸不遮缺件；隐藏配合和局部安装保留外观推导。

## 三分支四芯连接

```js
import {loadModel, loadGroveModule} from '../src/loaders.js';

const host = await loadModel('sticks3');
const hub = await loadGroveModule('hub');
host.port('grove').attach(hub);
const driver = await loadGroveModule('bldc-driver', {terminalPlug: true, cableLength: 65});
const rca = await loadGroveModule('rca', {covers: false, cableLength: 80});
const puzzle = await loadGroveModule('puzzle', {cableLength: 95});
hub.port('grove-1').attach(driver);
hub.port('grove-2').attach(rca);
hub.port('grove-3').attach(puzzle);

host.handle({type: 'pose', target: 'grove/grove-1/unitFrame',
  position: [0, 160, 8], rotation: [.1, -.2, .15]});
host.handle({type: 'cable', target: 'grove/grove-1/cable',
  slack: 12, bend: [0, 0, -1]});
```

Grove线各有4根实际导线；`unitFrame`改变产品姿态，`cable`改变线形，分支可独立拆装。每帧 `host.update(dt)` 推进按键/关节形状插值；结束时 `host.dispose()` 释放装配树。通过 `detach({dispose:false})` 保留的附件由调用者重新装入或释放。

## BLDC Driver：固定相线座与随附插头

本款提供真实U/V/W/COM四位固定座，`terminal` 类型为 `ht3.96-4p`。默认裸座；`terminalPlug:true` 安装随附 `TerminalPlug`，配置菜单同时提供带插头和裸座。产品入口导出 `TerminalPlug`，总入口别名为 `BldcDriverTerminalPlug`。四个 `terminal/screw-1`…`screw-4` 只外驱实际螺钉头角度/时长，拒绝非零RPM，不表示轴向压线、扭矩或电气连接。

```js
host.handle({type: 'joint', target: 'grove/grove-1/terminal/screw-1',
  angleDeg: 45, durationMs: 120});
const plug = driver.port('terminal').detach({dispose: false});
driver.port('terminal').attach(plug);
```

固定座和Grove帧在插头拆装时保持。本款没有随附电机、外露转子、按钮或旋钮，不造电机动效。实际绿色SYS_LED位于闭合不透明壳内，没有确证外露光路，因此只保留隐藏实体，不注册穿壳灯或光晕。外部框架自行处理PWM、转速、方向、驱动和保护逻辑。

## RCA：单枚双通道滑钮和真实母座

`rca` 是实际RCA母座，保留金属外筒、中心触点、绝缘体和开放插入腔；不是Grove，不能插入Grove Module。包装没有确证随附RCA线，本批不虚构附件。模型不生成音频、视频、扫描、显示屏或扬声器，也不把一个实际插孔扩成两个声道插孔。

`channel` 是PCB上单枚SW-SPDT稳定滑钮，双通道描述不代表两枚实体开关。默认闭壳不接受穿壳pointer，`covers:false` 检查配置才可看/操作；隐藏显示层保留原壳数据，贴层随真实盖板隐藏，PCB的固定I1/I2字样不随滑块移动。

```js
host.handle({type: 'button', target: 'grove/grove-2/channel',
  action: 'position', position: 1});
host.on('input', event => externalFramework.receive(event));
```

0/1只表示稳定物理档位。外驱档位不回送输入；压放产生 `down` / `up` / `click`，取消产生带取消标志的 `up` 并省略 `click`。档位不切换模拟信号或音视频功能。无LED、关节或传感器锚点。

## Puzzle：64真实灯珠与外驱矩阵

原生8×8隔光栅格后有64颗实际WS2812E-1313封装，默认全部关闭，不用一张发光图片代替实体。独立 `pixel-0`…`pixel-63` 按正视左上至右下的行优先外观布局索引；该坐标约定不声称等同原厂WS2812串行线序。

`matrix` 接受64色或256个RGBA字节，`brightness` 可选且为0…1，RGBA的alpha只乘可见亮度。帧数据在更改灯光前整体验证，错误输入保持原状态；颜色和帧命令不产生输入事件。

`matrix.getState()` 每次从真实64颗 `Led` 读回 `{width:8,height:8,order:'row-major-top-left',pixels:[{color,brightness},…]}`，逐灯外驱后读回也立即更新，没有陈旧的帧缓存。

```js
const colors = Array.from({length: 64}, (_,i) =>
  i % 9 === 0 ? '#fb8e34' : '#204060');
host.handle({type: 'matrix', target: 'grove/grove-3/matrix', colors, brightness: .6});
host.handle({type: 'led', target: 'grove/grove-3/pixel-63',
  color: '#34a866', brightness: .25});

const rgba = Array.from({length: 64}, () => [230, 80, 45, 128]).flat();
host.handle({type: 'matrix', target: 'grove/grove-3/matrix', rgba, brightness: .5});
```

逐灯外驱和矩阵帧都只更新实际发光封装的外观，不添加MCU、动画、按键、限流、热状态或单线协议。模型不会根据官方亮度建议自动改变调用方的数值；硬件使用建议仍由官方文档和外部框架处理。

## Puzzle：实际Grove级联

主输入 `grove` 对应J2，输出 `out` 对应J1，可接另一真实GroveModule，继续渲染四芯线与下级实体：

```js
const second = await loadGroveModule('puzzle', {cableLength: 60});
puzzle.port('out').attach(second);
host.handle({type: 'matrix', target: 'grove/grove-3/out/matrix',
  colors: Array(64).fill('#13a67d'), brightness: .4});
const retained = puzzle.port('out').detach({dispose: false});
puzzle.port('out').attach(retained);
```

级联建立几何、四芯线和装配所有权，不自动转发像素数据、电源或串行信号；上游矩阵更新不会改变下游灯光。上层必须分别写各块矩阵。级联输出也可接其他已支持的Grove Module，实际电气/协议兼容由外部框架决定。原壳固定孔按真实PCB背衬终止，不能把完整成品误当作前后贯穿孔。

随附连接扩展件另导出独立 `Bridge` Device，总入口别名 `PuzzleBridge`，包括原CAD的carrier/rear cap、实际PCB/双四孔插座和背标。它只展示真实附件外形，没有注册装配Port或命令；隐藏安装基准不足，暂不声称已经核准两块成品的刚性配合。上面的 `out` 示例仍使用真实四芯Grove线。独立构造 `new Bridge({artwork:false})` 可关闭附件印刷并保留物理结构。

## 同步贴纸和必要检查

私表没有本批三款精确原稿，按已授权本型号官图代码重绘高清PNG并标 `reference-redraw`。BLDC Driver正背印刷、RCA背标/PCB固定丝印、Puzzle背面双Grove/方向标分别记录；Puzzle正面矩阵是实体而非贴纸。具体PNG数、可辨文字、字体/颜色与配准限制见单品研究和[本批进度](../artifacts/bldc-rca-puzzle-expansion/progress.json)。不裁照片、不编造小字、不以贴纸遮缺件；私表、私有链接/原稿名、矢量、官图CAD原件、生成器和中间件留仓库外，公开最终普通PNG/衍生几何/安全来源。

每个模型/模块分别传 `artwork:false`，保留对应插头/闭壳/开盖配置的完整物理attributes/index及世界矩阵。必要专项 `node scripts/check-bldc-rca-puzzle-units.mjs` 检查真实StickS3→HUB三分支四芯、四螺钉插头、单枚壳内稳定滑钮和开盖边界、64独立灯/矩阵格式/无效帧拒绝、第二块Puzzle四芯级联且无自动数据转发、机械类型/内部功能边界及各配置印刷开关。综合结果以本批进度为准。

总入口提供 `BldcDriverUnit` / `BldcDriverUnitModule` / `BldcDriverTerminalPlug`、`RcaUnit` / `RcaUnitModule`、`PuzzleUnit` / `PuzzleUnitModule` / `PuzzleBridge`。保持 `modeled`，没有逐面浏览器、全量历史或实物验收；公开Git85款 `ad5d062` 是已同步基线，后续本地增量未自动再次推送。

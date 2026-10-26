# DCSSR / NCIR2 / Reflective IR 接入

2026-10-26。本批新增U140、U150、U175。每款导出 `Model`、`GroveModule`、`spec`，提供四芯 `grove` 和被动 `sensor`。模型负责实体形状、可见控件、外驱灯光和输入意图；固件、电气、继电、温度、距离和声音由外部框架实现。

| 产品ID | SKU | 本款实体与外驱能力 |
| --- | --- | --- |
| `dcssr` | U140 | 完整直流SSR套件、控制板、中央按钮、三盏独立灯、四SSR螺钉、两可拆4P插头及各四枚螺钉 |
| `ncir2` | U150 | TO39测温头、真实蜂鸣器实体、原壳舌按钮、侧面复位按钮和RGB |
| `reflective-ir` | U175 | 两颗IR收发封装、真实背面电位器孔和调节头、独立红指示灯 |

采用毫米尺度，+X右、+Y产品顶部、+Z正面。厂商标称、官方CAD包络和含实际附件的装配包络分别见各款 `dimensions.js`、`cad-map.json` 及研究记录。DCSSR官方45×30.7×11.5 mm描述控制板含叉片，不能当成整套SSR尺寸；整套安装关系保留照片推导。NCIR2标称厚8 mm与原壳凸起的8.55 mm包络分开。Reflective IR壳厚8 mm与含收发管12 mm总厚分开；官图明确的背面调节孔已按照片重建，避免用贴纸代替实体孔。

## 真实三分支四芯接线

```js
import {loadModel, loadGroveModule} from '../src/loaders.js';

const host = await loadModel('sticks3');
const hub = await loadGroveModule('hub');
host.port('grove').attach(hub);
const ssr = await loadGroveModule('dcssr', {terminalPlug: true, cableLength: 65});
const ncir = await loadGroveModule('ncir2', {cableLength: 80});
const ir = await loadGroveModule('reflective-ir', {cableLength: 95});
hub.port('grove-1').attach(ssr);
hub.port('grove-2').attach(ncir);
hub.port('grove-3').attach(ir);

host.handle({type: 'pose', target: 'grove/grove-1/unitFrame',
  position: [0, 160, 8], rotation: [.1, -.2, .15]});
host.handle({type: 'cable', target: 'grove/grove-1/cable',
  slack: 12, bend: [0, 0, -1]});
```

每支Grove线实际有4根导线。`unitFrame`改变产品姿态，`cable`改变线缆形状；独立拆除一支保持其他分支。每帧调用 `host.update(dt)` 推进按键和关节形状插值，结束时 `host.dispose()` 释放装配树。调用 `detach({dispose:false})` 后由调用者重新安装或释放保留配件。

## DCSSR：完整直流套件与独立灯光

U140对应直流SSR，不能借用交流U139的标签或参数。`button` 为瞬时按钮，压下/释放/取消只发送输入意图；没有自动切换继电器或模式。`rgb` 接受外部颜色/亮度，`power-led` 和 `ssr-led` 是独立固定红色灯，只接受外部开关/亮度，重设颜色不会把它们变成RGB。

```js
host.handle({type: 'led', target: 'grove/grove-1/rgb',
  color: '#37c98b', brightness: .6});
host.handle({type: 'led', target: 'grove/grove-1/power-led', brightness: .3});
host.handle({type: 'led', target: 'grove/grove-1/ssr-led', on: true});
host.on('input', event => externalFramework.receive(event));
```

`ssr-screw-1`…`ssr-screw-4` 只外驱SSR四枚真实螺钉头角度；`terminal-1` / `terminal-2` 均为 `ht3.96-4p`，拒绝Grove。默认构造不装插头，`terminalPlug:true` 分别安装两只独立 `TerminalPlug`，各提供 `screw-1`…`screw-4`。配置菜单同时提供带插头和裸座形状。产品入口导出 `TerminalPlug`，总入口别名为 `DcssrTerminalPlug`。

```js
host.handle({type: 'joint', target: 'grove/grove-1/ssr-screw-1',
  angleDeg: 45, durationMs: 120});
host.handle({type: 'joint', target: 'grove/grove-1/terminal-1/screw-1',
  angleDeg: 35});
const plug = ssr.port('terminal-1').detach({dispose: false});
ssr.port('terminal-1').attach(plug);
```

头部角度不代表扭矩、螺纹轴向、压线、电气连续性或继电器动作；拒绝非零RPM。插头拆装保持固定座、另一插头、控制板和Grove帧。

## NCIR2：原壳舌与真实复位键

`button` 是正面原生U形壳舌，`reset` 的外露执行件也是前壳原有的一体侧舌；两者直接对各自原顶点做弹性形状变化，释放后精确回到原CAD，不另贴凸帽或新增穿壳控件。两者均为瞬时 `Button`，无需开盖。`press()` / `release()` 产生 `down`、`up`、`click`，`cancel()` 结束输入并省略 `click`，多层地址随装配树冒泡。复位按钮不直接执行MCU复位。

```js
ncir.button('button').press('external-pointer');
host.update(1 / 60);
ncir.button('button').release('external-pointer');
ncir.button('reset').press('external-pointer');
ncir.button('reset').cancel('external-pointer');
host.handle({type: 'led', target: 'grove/grove-2/rgb',
  color: '#e59528', brightness: .5});
```

TO39金属筒、光学窗口、PCB和蜂鸣器为独立实体，不能靠印刷填满开口。没有显示屏、蜂鸣声、温度读数、报警阈值或自动灯光逻辑。`sensor` 只作视觉锚点，不接受温度或告警命令。

## Reflective IR：背面电位器与红灯

`threshold` 为真实背面电位器的调节头，只改变可见头角和外观插值，范围−135…135°，拒绝非零RPM。该角度是保守展示范围，不是原厂额定止挡；`getState()` / `meta` 保留限制和证据。两颗IR发射/接收封装保留真实透明度和颜色，不渲染可见IR光束或虚构发光。

```js
host.handle({type: 'joint', target: 'grove/grove-3/threshold',
  angleDeg: 70, durationMs: 120});
host.handle({type: 'led', target: 'grove/grove-3/status-led', brightness: .4});
```

`status-led` 是实际PCB上的固定红色灯，位于闭合壳内，默认关闭；允许独立外驱亮度，但不新增外壳窗口，也不显示穿壳光晕。它不跟电位器、按键、检测距离或输入状态自动联动。`sensor`、`emitter`、`receiver` 均为被动视觉锚点，不实现比较器、电压、发射功率、接收光学或检测距离。

## 同步贴纸、来源与必要检查

本批三款各2张，共6张 `reference-redraw` PNG，均按本型号官方照片代码重绘，私表没有精确原稿。DCSSR分别保留控制器和直流SSR标签；NCIR2正背印刷保留真实壳舌和孔口；Reflective IR正面收发符号、背面型号/阈值方向/接口标保留实际电位器孔。字体、颜色、局部注册和不可辨小字的限制见各款研究记录，不把重绘称原厂矢量导出，不裁产品照片，不用贴纸遮缺件。

每个模型/模块分别传 `artwork:false` 关闭印刷，所有实体、真实孔和附件配置的物理attributes/index及世界矩阵保持。私表、私有链接、原稿名、矢量、原始官方图/CAD、生成器和中间件均在仓库外；公开普通PNG、衍生几何和安全来源说明。

必要专项：`node scripts/check-dcssr-ncir2-reflective-ir-units.mjs`。检查真实StickS3→HUB三分支四芯、实际按钮压放/取消/原位恢复、独立灯、两插头和12枚螺钉头、有限调节头角、被动锚点与各配置印刷开关。单品smoke/来源/推导见各研究目录；两构建、在线资源字节和隐私结果见[本批进度](../artifacts/dcssr-ncir2-reflective-ir-expansion/progress.json)。

总入口别名为 `DcssrUnit` / `DcssrUnitModule` / `DcssrTerminalPlug`、`Ncir2Unit` / `Ncir2UnitModule`、`ReflectiveIrUnit` / `ReflectiveIrUnitModule`。全部保持 `modeled`；未执行逐面浏览器、全量历史或实物验收。公开Git85款 `ad5d062` 是已同步的基线，后续本地增量未自动再次推送。

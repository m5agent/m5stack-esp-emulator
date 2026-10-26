# Thermal2 / FlashLight / GPS SMA 接入

2026-10-26。本批新增U149、U152、U190。每款导出 `Model`、`GroveModule`、`spec`，提供实际四芯 `grove`；Thermal2和GPS SMA另有被动 `sensor`，FlashLight为实际 `mode` / `light` 输出装配，没有传感器锚点。模型负责实体、输入意图、外驱灯光与可动形状；成像、温度、声音、固件、电气、GNSS和线缆物理由外部框架负责。

| 产品ID | SKU | 模型轴名义尺寸 mm | 本款结构与外驱能力 |
| --- | --- | --- | --- |
| `thermal2` | U149 | 24×48×8 | 黑色下凹MLX90640采集头、ESP32-PICO-D4/PCB/蜂鸣器实体、两原壳舌和独立RGB |
| `flashlight` | U152 | 24×32×8 | 实际固定白光灯珠和壳内模式选择器，闭壳/开盖配置 |
| `gps-sma` | U190 | 24×71.4×8 | ATGM336H/屏蔽模组、SMA和可拆带线有源天线，同轴与末端puck外驱形状 |

采用毫米尺度，+X右、+Y产品顶部、+Z正面；厂商尺寸顺序、CAD包络和实际组件包络见各款 `dimensions.js` / `cad-map.json`。保留本款原壳和真实开口后的PCB/封装/深腔背衬，贴纸不代替实体。隐藏安装、按键行程、光学内部、同轴直径/配合与曲线保留外观推导，不声称制造配合或物理性能验证。

## 三分支四芯接线

```js
import {loadModel, loadGroveModule} from '../src/loaders.js';

const host = await loadModel('sticks3');
const hub = await loadGroveModule('hub');
host.port('grove').attach(hub);
const thermal = await loadGroveModule('thermal2', {cableLength: 65});
const flash = await loadGroveModule('flashlight', {covers: false, cableLength: 80});
const gps = await loadGroveModule('gps-sma', {antenna: true, cableLength: 95});
hub.port('grove-1').attach(thermal);
hub.port('grove-2').attach(flash);
hub.port('grove-3').attach(gps);

host.handle({type: 'pose', target: 'grove/grove-1/unitFrame',
  position: [0, 160, 8], rotation: [.1, -.2, .15]});
host.handle({type: 'cable', target: 'grove/grove-1/cable',
  slack: 12, bend: [0, 0, -1]});
```

每支Grove线实际渲染4根导线；`unitFrame`改变产品姿态，`cable`改变Grove线形。各分支可独立拆装；每帧 `host.update(dt)` 推进形状插值。`host.dispose()`释放装配树；通过 `detach({dispose:false})` 保留的附件由调用者重新安装或释放。

## Thermal2：真实采集头和双原壳舌

Thermal2严格使用本款黑色下凹MLX90640滤光封装、ESP32-PICO-D4及真实声学实体。与NCIR2共享外壳来源不代表传感器、MCU和印刷相同；没有显示屏或内生热成像framebuffer。

`button` 和 `reset` 对应本款正面与侧面实际外露的原壳舌，使用原始顶点形变，完整保留壳三角；释放/取消后精确回到原CAD。两者均为瞬时按钮，只发输入意图，复位键不直接执行MCU复位；`rgb` 独立外驱，不跟按键、温度或告警自动联动。

```js
thermal.button('button').press('external-pointer');
host.update(1 / 60);
thermal.button('button').release('external-pointer');
thermal.button('reset').press('external-pointer');
thermal.button('reset').cancel('external-pointer');
host.handle({type: 'led', target: 'grove/grove-1/rgb',
  color: '#e59528', brightness: .5});
host.on('input', event => externalFramework.receive(event));
```

输入地址保留装配路径。正常压放产生 `down` / `up` / `click`，取消产生带 `cancelled:true` 的 `up` 并省略 `click`。`sensor` 仅为视觉锚点，不接受温度、像素、告警或声音命令。外观印刷保留官图可辨文字，RGB引脚标签与原理图的冲突见单品来源/反馈；印刷不构成GPIO语义。

## FlashLight：白灯与真实壳内模式开关

`light` 为本款单颗固定白灯外观，默认关闭，只外驱 `on` / `brightness`，重设颜色不会把它变成RGB。官方正文、原理图和背贴标5000…5700K，规格表另标6000…6500K，生产色温范围的冲突待官方确认；预览固定色 `#fffaf0` 不代表校准色温。不自动生成闪光脉冲、频闪时序、Torch模式、功率或热行为，不画虚构光束。冲突反馈见单品来源记录。

`mode` 保留在PCB上的实际内位。默认闭壳不接受穿壳指针输入；`covers:false` 为开盖检查配置，才可看到并操作真实选择器。开盖隐藏盖板显示层及其印刷，原壳数据保持；PCB的固定模式标属于PCB，随开关位置保持不动。模式只表示稳定物理档位，不改变灯亮度或执行闪光/常亮逻辑。

```js
host.handle({type: 'led', target: 'grove/grove-2/light', brightness: .55});
host.handle({type: 'button', target: 'grove/grove-2/mode',
  action: 'position', position: 1});
```

模式档位的外部设置不回送输入，输入意图交给调用方决定功能。闭壳与开盖配置均保留完整物理装配和真实光路，不能把隐藏选择器移到壳面或为它新增假孔。

## GPS SMA：可拆有源带线天线

本款使用真实SMA接口和带线有源天线，不套LoRa胶棒，也不添加不存在的铰链。`antenna:false` 为裸本体，`antenna:true` 装入完整天线附件；配置菜单可直接选择。产品入口导出 `Antenna`，总入口别名为 `GpsSmaAntenna`。`sma` 拒绝Grove模块，端口类型、实际公母针和配对信息见 `meta` / 单品来源。

官方天线puck为38×36×13 mm，线长1m。名义线长与当前可见曲线长度分别记录；默认曲线、2.8mm同轴外径、弯曲与端部姿态为外观推导，不是线缆力学或RF模型。附件的 `shape` 接受毫米中心线 `points`，坐标属于SMA附件局部帧。要求3…32个有限xyz点，每轴位于±1500mm；首点精确为 `[0,0,0]`，第二点x=z=0且y≥18mm，相邻点距离至少2mm。没有恒定总曲线长度约束。

```js
const shape = gps.port('sma').module.get('shape');
const points = shape.getState().points.map(point => [...point]);
points.at(-1)[0] += 25;
host.handle({type: 'shape', target: 'grove/grove-3/sma/shape', points});
const antenna = gps.port('sma').detach({dispose: false});
gps.port('sma').attach(antenna);
```

`shape.getState()` 包含 `points`、`nominalCableLengthMm:1000`、`curveLengthMm`（从固定尾套 `[0,10,0]` 起算）、`cableOuterDiameterMm:2.8`、`puckMm:[38,36,13]`、`puckCableEntryPositionMm`、`puckQuaternion` 与 `space:'module-port'`。曲线命令更新同轴和末端puck，保持固定SMA/Grove与本体；无效点集被拒后保持旧几何和状态。插拔附件不改变内部模组、其他分支或主机屏幕。没有卫星、定位、NMEA、信号强度、RF、电气或线缆物理逻辑；实际蓝1PPS没有确证外露光路，因此不注册LED或穿壳光晕。

## 贴纸、来源与必要检查

三款私表均无精确原稿，同步采用已授权本型号官方照片代码重绘高清PNG，标 `reference-redraw`。不裁照片，不混用相近型号，不编造不可读小字，不用印刷掩盖缺件。具体面、PNG数量、字体/颜色与配准限制见单品研究和[本批进度](../artifacts/thermal2-flashlight-gps-expansion/progress.json)。私表、私有链接、原稿名、矢量、官图/CAD原件、生成器与中间件仅留仓库外；公开最终普通PNG、衍生几何和安全来源说明。

每个独立模型/模块传 `artwork:false` 关闭印刷，保留各闭壳/开盖/天线配置的全部物理attributes/index和世界矩阵。必要专项为 `node scripts/check-thermal2-flashlight-gps-units.mjs`，检查真实StickS3→HUB三分支四芯、双原壳舌压放取消/原位恢复、灯独立、壳内稳定选择器边界、天线曲线及独立插拔、机械类型/被动锚点与配置印刷开关。单品来源、局部smoke和限制见各款研究目录；综合范围以本批进度为准。

总入口提供 `Thermal2Unit` / `Thermal2UnitModule`、`FlashlightUnit` / `FlashlightUnitModule`、`GpsSmaUnit` / `GpsSmaUnitModule` / `GpsSmaAntenna`。保持 `modeled`，没有逐面浏览器、全量历史或实物验收；公开Git85款 `ad5d062` 是已同步基线，后续本地增量未自动再次推送。

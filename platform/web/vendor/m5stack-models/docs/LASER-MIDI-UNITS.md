# Laser TX / Laser RX / MIDI

本批提供独立 `Model` 和含两个插头、四根实体线的 `GroveModule`。坐标单位为毫米，+X 向右、+Y 向上、+Z 正面；原生壳、PCB、光学件、插座与控件分别保留。固件、光学传播/感应、信号、MIDI、合成和音频由外部框架实现。

| 产品 | 模型轴名义尺寸 | 外观和组件 |
| --- | --- | --- |
| `laser-tx` / U066 | 24 × 32 × 8 mm；厂商顺序32 × 24 × 8 | 完整壳体、PCB、实际发射头/透镜和Grove；`emitter` 为独立外驱固定红色发射孔外观，`sensor` 为被动锚点 |
| `laser-rx` / U065 | 24 × 32 × 8 mm；厂商顺序32 × 24 × 8 | 自身接收封装、非发光深色光窗、PCB和Grove；只有 `grove` 与被动 `sensor`，不把接收头注册为灯 |
| `midi` / U187 | 40 × 48 × 25 mm；厂商顺序48 × 40 × 25 | 原生双壳/光导、PCB/SAM2695/光耦、2个DIN母座和3个3.5mm插座；稳定 `mode`、固定绿 `power-led`、`grove` 与被动 `sensor` |

模型的名义尺寸、原CAD包络和含贴层的可视包络分别保存；不会通过缩放外壳消除来源口径差别。隐藏PCB、光学头剖面/安装深度、插座内构和滑块行程的推导边界见 [TX](research/laser-tx/modeling.md)、[RX](research/laser-rx/modeling.md)、[MIDI](research/midi/modeling.md)。

## 发射与接收外观

```js
import {loadModel, loadGroveModule} from 'm5stack-models.js/loaders';

const tx = await loadModel('laser-tx');
const rx = await loadModel('laser-rx');
tx.get('emitter').set({brightness:.6});
tx.get('emitter').set({on:false});
```

TX官图/实物背标可辨650nm印字，发射孔只保持固定红色外观，接收任意 `color` 也不会变成另一发光颜色。亮度是归一化视觉参数，不换算为功率、占空比或物理光强。默认关闭，不投射光束、光斑或通信动画。RX保持非发光的真实接收头和原孔；TX外观改变不会更新RX状态，没有两Unit之间的自动光学连接。

两款使用同一官方壳体blob，但分别建各自实际发射/接收内构和印刷。不能用同壳推断同电路。`sensor` 只是视觉锚点，没有send/read/light-level、收发码、传播或感应命令。Grove分别记录TX的GND / 5V / DIN / NC和RX的GND / 5V / NC / DOUT；TX背贴印OUT与正文DIN分别保留为印刷/接口来源记录，不把印刷差异变成模拟行为。

## MIDI滑块、指示灯与真实接口

```js
const midi = await loadModel('midi');
midi.button('mode').setPosition(1); // 0=左Bypass，1=右Separate；只改变外观档位
midi.update(.2);
midi.get('power-led').set({brightness:.4});

midi.on('input', event => {
  // 外部框架接收mode按下/弹起/点击意图后决定实际路由。
  console.log(event.id, event.action);
});
```

`mode` 为真实稳定拨选滑块，松开后保持目标档位；固定DIN/TRS/Grove口不随滑块移动。`power-led` 使用原生光导，固定绿色、默认关闭、独立外驱；改档不自动点灯或改变信号。模型不实现Bypass/Separate路由、UART、MIDI消息或音频合成，也不加载演奏音效。

| 端口ID | 机械配对类型 | 可见用途 |
| --- | --- | --- |
| `midi-in-din` / `midi-out-din` | `din-5pin-female` | 2个真实5孔DIN母座；孔壁、触点和后方插座保持实体深度 |
| `midi-in-trs` / `midi-out-trs` | `audio-3.5mm-trs` | MIDI输入/输出的3.5mm机械插座 |
| `audio` | `audio-3.5mm-trs` | 合成器音频输出机械插座 |
| `grove` | `grove` | GND / 5V / UART_RX / UART_TX机械挂接与四芯线 |

TRS三口共享机械配对字符串，不表示MIDI和耳机音频在电气上等价。DIN/TRS拒绝Grove模块；接口约束仅管理几何装配，不证明实物引脚、音频/MIDI接线、电平或电气兼容。正文表格将三个TRS统称音频口，模型根据实际端口标记分别保留用途。产品波特率文字与教程存在差别，来源记录单独说明，不据此在模型中执行协议。

## 三分支装配与层级地址

```js
const host = await loadModel('sticks3');
const hub = await loadGroveModule('hub', {cableLength:60});
host.port('grove').attach(hub);
hub.port('grove-1').attach(await loadGroveModule('laser-tx', {cableLength:65}));
hub.port('grove-2').attach(await loadGroveModule('laser-rx', {cableLength:80}));
hub.port('grove-3').attach(await loadGroveModule('midi', {cableLength:95}));

host.handle({type:'led', target:'grove/grove-1/emitter', brightness:.55});
host.handle({type:'led', target:'grove/grove-3/power-led', brightness:.4});
host.get('grove/grove-3/mode').setPosition(1);
host.handle({type:'pose', target:'grove/grove-3/unitFrame',
  position:[35,120,8], rotation:[.1,-.2,.15]});
host.handle({type:'cable', target:'grove/grove-3/cable', slack:12, bend:[0,0,-1]});
host.update(.2);

const saved = hub.port('grove-2').detach({dispose:false});
hub.port('grove-2').attach(saved);
host.dispose();
```

示例只证明三分支机械挂接、实际四芯线姿态和组件寻址，不声明HUB能够路由这些不同的模拟/数字/UART协议，也不建立TX/RX光学链路。

## 同步贴纸与检查范围

已优先检索用户提供的贴纸表，暂无三款精确型号原稿。各面使用同型号官方图中的可辨文字和图形代码重绘为高清PNG并标 `reference-redraw`，不裁产品照片；不可辨细字在单品记录中保留缺项。像素、来源、配准和摘要见各款 `artwork.json`，贴图不替代实体零件或遮盖缺口。

```js
const bare = await loadModel('laser-tx', {artwork:false});
const wiredBare = await loadGroveModule('midi', {artwork:false});
```

每个独立模型/模块各自接收 `artwork:false`，主机选项不自动传播。关闭印刷保留完整壳体、原孔、PCB、光学件、插座、光导和实际滑块。私有CSV、下载链接、矢量原稿、映射、生成器和中间件始终留在仓库外；公开只最终普通PNG、配准和来源说明，印刷/标识保留各自权利。

必要专项为 `node scripts/check-laser-midi-units.mjs`，单品结构/API记录在 `docs/research/<id>/smoke.json`。覆盖真实三款四芯线、独立固定色光、被动锚点、真实稳定滑块/固定接口、DIN/TRS拒绝Grove、贴纸关闭的物理不变与独立拆离。Node图形边界替身不提供浏览器像素证据；未做逐面浏览器、全量历史目录、实物/电气/光学/MIDI/音频验收，阶段保持 `modeled`。

# 2Relay / 4Relay / DMX 接入

三款都提供独立 `Model` 和带四芯 Grove 线的 `GroveModule`。保留官方壳体，补 PCB、主要封装和接口腔体。继电器通断、GPIO、I2C、DMX512、终端电阻与真实供电由下游处理。

| ID | 型号 | 可拆附件 / 机械控制 | 独立外驱指示灯 |
| --- | --- | --- | --- |
| `2relay` | U131 | `terminal-1` / `terminal-2`，每只4P插头有 `screw-1`…`screw-4` | `led-1` / `led-2`，固定蓝色 |
| `4relay` | U097 | `terminal-1`…`terminal-4`，每只4P插头有 `screw-1`…`screw-4` | `led-1`…`led-4`，固定绿色 |
| `dmx` | U183 | 保持档位的 `termination`，瞬时 `xlr-release` | `power-led`，固定红色 |

两款 Relay 默认空座，`{terminalPlug:true}` 安装全部随附插头；预览中的 `socket` / `plug` 配置对应这两种外观。产品入口导出 `TerminalPlug`；共享入口分别导出 `TwoRelayTerminalPlug` 和 `FourRelayTerminalPlug`。端子 connector 为 `ht3.96-4p`，产品内保留各自的实际几何。

```js
import {loadModel, loadGroveModule} from 'm5stack-models.js/loaders';

const host = await loadModel('sticks3');
const hub = await loadGroveModule('hub', {cableLength:60});
host.port('grove').attach(hub);
const relay = await loadGroveModule('4relay', {terminalPlug:true, cableLength:70});
const dmx = await loadGroveModule('dmx', {cableLength:80});
hub.port('grove-1').attach(relay);
hub.port('grove-2').attach(dmx);

host.get('grove/grove-1/terminal-2/screw-3').set({angleDeg:45});
host.get('grove/grove-1/led-2').set({brightness:.5});
host.get('grove/grove-2/termination').setPosition(1);
host.get('grove/grove-2/power-led').set({on:true});

// 输入注入：PUSH片压下、松手或取消后回位。
const release = host.button('grove/grove-2/xlr-release');
release.press('external-preview');
release.cancel('external-preview');
host.update(1 / 60);

// 单独卸下一只端子，固定座、其他插头、Unit和Grove线保留。
const port = relay.port('terminal-2'), plug = port.module;
port.detach({dispose:false});
port.attach(plug);
host.dispose();
```

螺钉只接受头部角度，不模拟螺纹升降、夹线、扭矩或端子电流。端子安装/拆离不改变独立灯光状态。灯接受 `on` / `brightness`，保持实际固定色；它们不随螺钉或滑块自动亮灭。密封继电器封装不虚构外露活动机构。

DMX 的 XLR-3 母座保留真实三孔、接触件和筒腔，接口类型与 Grove 分开。`termination` 只移动实际滑块，松手保档；`xlr-release` 只显示实际释放片的压放意图和估计行程，不实现锁线。未建配套外部 XLR 线。官方图文、原理图或尺寸口径不同处，以及内部布局、材质、螺钉槽和行程等推导，分别记录在产品 research。

必要检查入口为 `node scripts/check-relay-dmx-units.mjs`，覆盖真实三分支 Grove 连接、六只插头、24个螺钉、固定色灯光、DMX滑块与释放片、独立拆离。canvas为Node替身，不代表浏览器像素或硬件验收。按用户要求未进行逐面浏览器复核，印刷后置，阶段保持 `modeled`。

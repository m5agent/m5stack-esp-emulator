# CAN / ENV Pro / ToF4M 接入

本批三个模型都可独立展示，也可用四芯 Grove 线挂接主机或 HUB。完整官方壳保留，内部 PCB、器件、接口腔体及光学/通风口后的封装用实体构造。隐藏布局、材质和安装位置的推导范围见各产品 research。

| ID | 型号 | 可见部件与 API |
| --- | --- | --- |
| `can` | U085，CA-IS3050G | 固定4P座、可拆 `terminal`、`terminal/screw-1`…`screw-4`、固定白色 `power-led` |
| `env-pro` | U169，BME688 | 通风孔、PCB、实际金属传感器封装；`sensor` 仅视觉锚点 |
| `tof4m` | U172，VL53L1X | 光窗、实际光学封装及发射/接收部分；`sensor` 仅视觉锚点 |

CAN 默认空座，`{terminalPlug:true}` 装上随附4P插头；预览 `socket` / `plug` 配置对应两种外观。产品入口导出 `TerminalPlug`，共享入口别名为 `CanTerminalPlug`。螺钉只旋转头部，不模拟螺纹升降或夹线。白灯独立接受 `on` / `brightness`，保持实际颜色，不根据总线或端子状态自动点亮。

```js
import {loadModel, loadGroveModule} from 'm5stack-models.js/loaders';

const host = await loadModel('sticks3');
const hub = await loadGroveModule('hub', {cableLength:60});
host.port('grove').attach(hub);
const can = await loadGroveModule('can', {terminalPlug:true, cableLength:65});
hub.port('grove-1').attach(can);
hub.port('grove-2').attach(await loadGroveModule('env-pro', {cableLength:70}));
hub.port('grove-3').attach(await loadGroveModule('tof4m', {cableLength:75}));

host.get('grove/grove-1/terminal/screw-1').set({angleDeg:45});
host.get('grove/grove-1/power-led').set({brightness:.4});
host.handle({type:'pose', target:'grove/grove-3/unitFrame',
  position:[15,90,8], rotation:[.1,.2,-.15]});
host.handle({type:'cable', target:'grove/grove-3/cable',
  slack:10, bend:[0,0,-1]});

const port = can.port('terminal'), plug = port.module;
port.detach({dispose:false}); // 固定座、Unit、指示灯和Grove线保留
port.attach(plug);
hub.port('grove-2').detach(); // 单独卸下ENV Pro分支
host.dispose();
```

模型不实现 CAN 收发、电气隔离、I2C、寄存器、温湿度/气压/气体值或距离。`sensor` 不能接收虚构的测量命令。ENV Pro不添加原理图中不存在的灯；ToF4M不画人眼可见激光束，不模拟发光、测距或扫描。

必要接线/API检查命令为 `node scripts/check-can-env-tof-units.mjs`，覆盖三分支实际产品、四芯线、CAN端子/螺钉/固定色灯、测量边界、姿态和独立拆离。canvas为Node替身，不代表浏览器像素、光学或硬件验收。按用户要求不做逐面浏览器复核；新款印刷后置，阶段保持 `modeled`。

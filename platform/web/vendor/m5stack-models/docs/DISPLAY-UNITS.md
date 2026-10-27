# OLED / LCD Unit 的画面与接线

`oled`（U119）与 `lcd`（U120）沿用主机的 `Display` API。两款都有完整壳体、PCB、屏组件和 Grove 插座，支持独立模型与带四芯线的模块。屏幕只是外部 framebuffer 的显示表面；SH1107、ST7789V2、I2C、固件和自动刷新逻辑由下游实现。

| 产品 ID | 立式模型 X × Y × Z / mm | framebuffer | 显示表面 |
| --- | --- | --- | --- |
| `oled` | 24 × 56 × 8 | 64 × 128 | 单色 OLED |
| `lcd` | 24 × 48 × 8 | 135 × 240 | 彩色 LCD |

U119 厂商标称为 128×64；模型按外壳立向展示，画面坐标转为 64×128。像素原点始终为模型正面所见屏幕的左上角。单色内容由外部提供；通用 framebuffer 接口不模拟控制器的显存打包或阈值转换。

```js
import {loadModel, loadGroveModule} from 'm5stack-models.js/loaders';

const screen = await loadModel('lcd');
screen.display('lcd').fill('#18a4d0');
screen.display('lcd').writeRGBA(rgbaBytes);
// 也支持 writeRGB565 / writeRGB888、局部矩形及画布 present()。

const host = await loadModel('sticks3');
const hub = await loadGroveModule('hub', {cableLength: 60});
host.port('grove').attach(hub);
hub.port('grove-1').attach(await loadGroveModule('oled', {cableLength: 65}));
hub.port('grove-2').attach(await loadGroveModule('lcd', {cableLength: 75}));

host.handle({type: 'display', target: 'grove/grove-1/lcd', fill: '#eeeeee'});
host.handle({type: 'display', target: 'grove/grove-2/lcd', fill: '#18a4d0'});
host.handle({type: 'pose', target: 'grove/grove-2/unitFrame',
  position: [15, 65, 8], rotation: [.2, -.3, .1]});
host.handle({type: 'cable', target: 'grove/grove-2/cable',
  slack: 12, bend: [0, 0, -1]});

// 只卸 OLED，保留主机、HUB、LCD 和各自画面。
hub.port('grove-1').detach();
host.dispose();
screen.dispose();
```

示例中的 `rgbaBytes` 由调用者提供，长度应匹配目标画面。外部画面写入、模型更新、Unit 姿态及线缆变化相互独立；模型不自行产生测量值、应用画面或通信。

本地预览支持选择已接入层级中的屏幕，再点击校准画面；目标切换本身不会覆盖其他屏幕。OLED 校准画面为灰阶。独立入口分别为 `?model=oled` 与 `?model=lcd`。

CO2 U103 使用 `loadModel('co2')` / `loadGroveModule('co2')`，其中 `sensor` 为视觉锚点。它不拥有显示屏，不会在模型中生成 CO2 浓度、温湿度或通信状态。详细封装与尺寸推导见各产品 `docs/research/`。

本批仅做必要的有限结构/API、真实产品多屏接入夹具与构建。运行 `node scripts/check-display-units.mjs` 可复核独立画面、嵌套地址、姿态保留画面和分支拆离；表单与 canvas 为轻量替身，不代表浏览器像素或硬件验收。产品保持 `modeled`。

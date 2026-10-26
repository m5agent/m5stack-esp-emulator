# UWB / TMOS PIR / Mini ToF-90 接入

2026-10-26。本批增加U100、U185、U196，各款导出 `Model` / `GroveModule` / `spec`。模型负责真实壳体、PCB、封装、窗口、四芯Grove与外驱可见灯；RF、AT命令、定位、人体存在、温度、测距、固件和电气由外部框架实现。

| 产品ID | SKU | 模型轴名义尺寸 mm | 实际外部接口 |
| --- | --- | --- | --- |
| `uwb` | U100 | 24×48×8 | `grove`，内置天线，没有额外传感器锚点或SMA |
| `tmos-pir` | U185 | 24×32×8 | `grove`、被动 `sensor`，真实STHS34PF80滤窗 |
| `mini-tof-90` | U196 | 24×24×8 | `grove`、被动 `sensor`、固定红色 `power-led` |

毫米尺度，+X右、+Y顶部、+Z正面。Mini ToF-90的收发面朝+Y，两块PCB固定90°，没有铰链或关节。三款均无外露按键、屏幕或本体关节。UWB采用BU01/DW1000模组自身铜天线；TMOS PIR不套用旧PIR的Fresnel半球；Mini ToF保留实际VL53L0X封装、双光窗和板间连接。

TMOS PIR官方规格表写32×24×5.2mm，但本款尺寸图及STL总厚均为8mm；模型不缩放原壳，分别保留表值和图值，反馈ID为 `052dc71fcd6b48e5a17651bb4f438896`。尺寸决策、隐藏安装与局部外观推导见各产品的 `dimensions.js`、`cad-map.json` 和研究记录。

## 三分支四芯连接

```js
import {loadModel, loadGroveModule} from '../src/loaders.js';

const host = await loadModel('sticks3');
const hub = await loadGroveModule('hub');
host.port('grove').attach(hub);
const uwb = await loadGroveModule('uwb', {cableLength: 65});
const tmos = await loadGroveModule('tmos-pir', {cableLength: 80});
const tof = await loadGroveModule('mini-tof-90', {cableLength: 95});
hub.port('grove-1').attach(uwb);
hub.port('grove-2').attach(tmos);
hub.port('grove-3').attach(tof);

host.handle({type: 'pose', target: 'grove/grove-3/unitFrame',
  position: [90, 190, 8], rotation: [.1, -.2, .15]});
host.handle({type: 'cable', target: 'grove/grove-3/cable',
  slack: 12, bend: [0, 0, -1]});
host.handle({type: 'led', target: 'grove/grove-3/power-led', brightness: .4});
```

每支线均渲染四根导线与两端插头。`unitFrame`改变整款Unit姿态，`cable`只改变线形。UWB Grove标注为GND/5V/UART_RX/UART_TX；另两款为GND/5V/SDA/SCL。这些标签记录实际物件，不创建串口、I2C或供电行为。

`sensor`仅提供真实感测实体的位置与朝向，状态为空，不接受presence、distance等数值命令。不要假设每款都有该锚点：UWB只有实际 `grove` 端口。

## Mini ToF-90导光件

`power-led`默认关闭，接受 `on` / `brightness`，固定预览红色 `#ff2020`，不接受RGB变色。驱动的是原CAD里Grove旁的L形导光件材质，不增加Sprite、光晕、检测锥或可见红外束。位置、透明度和发光预览含安装推导，不代表光学标定。

灯光命令不改变几何、Grove帧或其他分支，不回送用户输入，也不自动跟随电源/测距状态。与其他Unit相同，外部框架应明确设置状态；默认构造不假装设备已通电。

## 贴纸与生命周期

三款各同步两张PNG。UWB标准正背两张为精确本款原稿恢复的 `source-vector-raster`；TMOS PIR、Mini ToF-90共四张为按本款官图代码重绘的 `reference-redraw`。不采用包装稿，不裁产品照片，不编造不可辨小字。原表、私有链接、原稿名、矢量、生成器和中间件留在仓库外，公开仅最终普通PNG及安全来源说明。

`artwork:false`关闭印刷，真实标签载体、原壳、PCB、封装、光窗和连接器保持。物理背衬独立于贴图，避免以贴纸填补缺件。PNG配准与隐藏元件位置仍含研究记录中列明的外观推导。

通过 `hub.port('grove-2').detach()`可独立释放TMOS分支，其余两支保持。`detach({dispose:false})`取下的模块可重新装入；最终由持有者调用 `dispose()`。根主机 `host.dispose()`会释放其仍挂载的装配树。

总入口别名为 `UwbUnit` / `UwbUnitModule`、`TmosPirUnit` / `TmosPirUnitModule`、`MiniTof90Unit` / `MiniTof90UnitModule`。必要专项为 `node scripts/check-ranging-presence-units.mjs`；来源及单品smoke见各研究目录，综合范围见[本批进度](../artifacts/ranging-presence-expansion/progress.json)。保持 `modeled`，没有逐面浏览器、全量历史或实物配合验收。

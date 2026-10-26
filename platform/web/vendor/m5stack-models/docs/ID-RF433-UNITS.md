# Unit ID / RF433R / RF433T 接入

2026-10-26。本批U124、U113、U114均导出 `Model` / `GroveModule` / `spec`，本体接口只有真实四芯 `grove`。模型负责真实壳体、PCB、芯片/天线、胶贴载体、外驱姿态和接线；加密/身份/密钥/认证、RF/ASK/收发数据、I2C、固件及电气由外部框架实现。

| 产品ID | SKU | 模型轴名义尺寸 mm | 本款实体 |
| --- | --- | --- | --- |
| `unit-id` | U124 | 24×24×8 | ATECC608B-TNGTLSU-G、稳压器与PCB |
| `rf433r` | U113 | 24×48×8 | SYN531R接收器、外围和固定PCB铜天线 |
| `rf433t` | U114 | 24×48×8 | SYN115发射器、外围和固定PCB铜天线 |

毫米尺度，+X右、+Y顶部、+Z正面；原CAD选择、名义/原壳/含薄膜的视觉包络见各 `dimensions.js`、`cad-map.json` 和研究记录。R/T保留各自本款路径所核的同源原壳，芯片、板上器件和印刷分别建形，不把接收/发射款互换。SYN531R为本款SOP-8，SYN115为本款SOT23-6；隐藏板位、铜天线走形/厚度、封装安装和贴纸配准仍含外观推导，不作制造公差或RF设计/性能结论。

R/T原壳正面标签区有原生开口，模型保留源三角，以实际外观中的独立实体胶片跨支承边，内部另有完整PCB和器件；不宣称胶片下面本来有完整原壳墙。后胶片贴原壳凹面，印刷关闭时物理胶片仍在。其他实际腔口保留连接器壁、触点和真实背衬，不用PNG补空，也不挖假芯片/天线观察窗。

三款没有 `sensor`、LED、按钮、关节、显示屏或喇叭。R/T天线在PCB内部固定，没有外置弹簧、SMA、胶棒或铰链，不创建 `antenna` 装配端口或可见RF波动效。RF433R原理图的 `E1 ANT_IPEX` 符号不足以确认量产外置接口；相关PCB/BOM资料已反馈 `4b666d887ad44a0f88d5ebb78bfc73df`，本模型按产品内置PCB天线描述保留固定结构，隐藏布局仍为推导。Unit ID的芯片只是实体，不生成或读取真实密钥/序列号，不执行认证或加密。

## 三分支四芯连接

```js
import {loadModel, loadGroveModule} from '../src/loaders.js';

const host = await loadModel('sticks3');
const hub = await loadGroveModule('hub');
host.port('grove').attach(hub);
const id = await loadGroveModule('unit-id', {cableLength: 65});
const rx = await loadGroveModule('rf433r', {cableLength: 80});
const tx = await loadGroveModule('rf433t', {cableLength: 95});
hub.port('grove-1').attach(id);
hub.port('grove-2').attach(rx);
hub.port('grove-3').attach(tx);

host.handle({type: 'pose', target: 'grove/grove-2/unitFrame',
  position: [45, 175, 8], rotation: [.1, -.2, .15]});
host.handle({type: 'cable', target: 'grove/grove-2/cable',
  slack: 12, bend: [0, 0, -1]});
```

每支线渲染四根导线与两端插头。`unitFrame`改变整款姿态，固定板/天线随本体一起放置；`cable`改变线形。挂接不会建立I2C、GPIO、射频或供电行为；R/T同时放入场景也不会自动互发数据或改变彼此状态。接口标注只记录实物外观，不能用作此模型提供的接线/电气功能。

不要假设每个Unit都有被动 `sensor`：本批只有 `grove`。向本体连接器发送身份、密钥、加密或RF收发命令会拒绝，模型不持有这些内部状态。下游框架可按自身协议实现功能，并通过现有姿态/装配API驱动外形。

## 印刷与释放

本批6张PNG均为严格本款官图代码重绘 `reference-redraw`：Unit ID、RF433R、RF433T各正背2张。没有匹配的精确机身原稿，不采用包装或别款印刷，不裁产品照片、不编造不可辨小字；字体/颜色及物理配准含照片推导。CSV、私有链接/映射、矢量原稿、生成器和中间件保留仓库外，仅公开最终普通PNG、衍生几何和安全来源。

两入口传 `artwork:false`关闭印刷，完整原壳、PCB、器件/固定天线、Grove和实际胶片载体保持，全部物理attributes/index与世界矩阵不变。`hub.port('grove-2').detach()`可独立释放接收款分支，其余两支保持；`detach({dispose:false})`保留的模块由调用方重新装入或释放。最终 `host.dispose()`释放仍挂载的装配树。

总入口别名为 `IdUnit` / `IdUnitModule`、`Rf433rUnit` / `Rf433rUnitModule`、`Rf433tUnit` / `Rf433tUnitModule`。必要专项 `node scripts/check-id-rf433-units.mjs`覆盖实际StickS3→HUB三分支四芯、grove-only接口与内部命令拒绝、两入口印刷全物理一致性、姿态/线形和独立装拆、主机framebuffer保持。单品本款原壳/PCB/天线/腔/胶片、FrontSide与定向闭合检查见各研究目录smoke，综合范围见[本批进度](../artifacts/id-rf433-expansion/progress.json)。保持 `modeled`，未做逐面浏览器、全量历史或实物验收。

此前三旧端子的当前修订基线保持，其SHA及历史快照关系见[端子闭合修复](TERMINAL-TONGUE-CLOSURE.md)。

# Accel / OP90 / OP180 接入

2026-10-26。本批U056、U057、U058均导出 `Model` / `GroveModule` / `spec`，本体接口只有真实四芯 `grove` 与被动 `sensor` 外观锚点。模型负责物件外形、装配姿态和接线；加速度/倾斜/落体/振动、光电遮挡/计数/数字电平、I2C、固件与电气由外部框架实现。

| 产品ID | SKU | 模型轴名义尺寸 mm | 本款结构 |
| --- | --- | --- | --- |
| `accel` | U056 | 24×32×8 | ADXL345、HT7533、AO3400A与固定PCB |
| `op90` | U057 | 24×32×12.8 | 固定90°安装的光电叉、相对收发窗与检测槽 |
| `op180` | U058 | 24×36×8.8 | 固定180°安装的光电叉、相对收发窗与检测槽 |

毫米尺度，+X右、+Y顶部、+Z正面。厂商长宽顺序、壳CAD和含器件/薄膜的实际视觉包络分别见 `dimensions.js`、`cad-map.json` 与研究记录。三款保留自己的完整原壳，不缩放壳体凑含器件规格。隐藏板位、引脚安装、局部颜色与贴纸配准仍含外观推导，不作制造公差或实物配合结论。两光窗的左右收发身份与安装位置仍含推导；OP180的5.5mm槽深按本款尺寸图比例估计，不作光学或量产标定。

OP90和OP180的数字表示本款固定结构，不能当作可调角度或视觉关节。两款检测槽是物件正常工作所需的真实空气通道，必须保持开放；槽两侧的遮光塑壳、实际收发窗口、内部实体和PCB另行建形。没有可见IR光束、发光窗口、检测锥、虚构机械按钮或开闭叉动画。Accel封闭壳体没有为展示芯片而挖出的假窗口。

## 三分支四芯连接

```js
import {loadModel, loadGroveModule} from '../src/loaders.js';

const host = await loadModel('sticks3');
const hub = await loadGroveModule('hub');
host.port('grove').attach(hub);
const accel = await loadGroveModule('accel', {cableLength: 65});
const op90 = await loadGroveModule('op90', {cableLength: 80});
const op180 = await loadGroveModule('op180', {cableLength: 95});
hub.port('grove-1').attach(accel);
hub.port('grove-2').attach(op90);
hub.port('grove-3').attach(op180);

host.handle({type: 'pose', target: 'grove/grove-2/unitFrame',
  position: [45, 175, 8], rotation: [.1, -.2, .15]});
host.handle({type: 'cable', target: 'grove/grove-2/cable',
  slack: 12, bend: [0, 0, -1]});
```

每支Grove线渲染四根导线与两端插头。`unitFrame`改变整款姿态，`cable`改变线形；挂接不会建立供电、I2C或数字检测行为。各款 `sensor` 只提供实际感测实体的位置与朝向，`getState()`为空，不接受加速度、倾斜、遮挡、计数或角度数值命令。三款均无LED、按钮、关节、显示屏或喇叭。

需要移动/转动整个Unit时，驱动 `unitFrame`；不要向OP90/OP180的 `sensor`发送 `joint`命令。实际光路或障碍物判断由外部框架基于物件几何自行实现，模型本身不判断“已遮挡”或自动改变状态。

## 印刷、关闭与释放

本批4张PNG均为严格本款官图代码重绘 `reference-redraw`：Accel正背2、OP90背标1、OP180背标1。本款没有的正面贴纸不虚构，包装和其他版本印刷不采用。没有匹配的精确机身原稿，不裁产品照片、不编造不可辨文字；字体/颜色及物理配准含照片推导。CSV、私有链接/映射、矢量原稿、生成器和中间件留在仓库外，公开仅最终普通PNG、衍生几何及安全来源。

两入口传 `artwork:false`关闭印刷，原壳/PCB/器件/光学腔壁、Grove和真实胶贴载体保持，所有物理attributes/index及世界矩阵不变。标签不替代PCB或结构背衬，也不覆盖检测空气槽。

`hub.port('grove-2').detach()`可独立释放OP90分支，其余两支保持。`detach({dispose:false})`保留的模块由调用方重新装入或释放，最终 `host.dispose()`释放仍挂载的装配树。

总入口别名为 `AccelUnit` / `AccelUnitModule`、`Op90Unit` / `Op90UnitModule`、`Op180Unit` / `Op180UnitModule`。必要专项 `node scripts/check-accel-opto-units.mjs`覆盖真实StickS3→HUB三分支四芯、被动锚点/数值与关节命令拒绝、两入口印刷全物理一致性、姿态/线形和独立装拆、主机framebuffer保持。槽/窗口/PCB的本款结构与FrontSide/闭合检查见各研究目录smoke，综合范围见[本批进度](../artifacts/accel-op90-op180-expansion/progress.json)。保持 `modeled`，未做逐面浏览器、全量历史或实物验收。

此前三旧端子的当前修订基线保持，其SHA及与历史快照的关系见[端子闭合修复](TERMINAL-TONGUE-CLOSURE.md)。

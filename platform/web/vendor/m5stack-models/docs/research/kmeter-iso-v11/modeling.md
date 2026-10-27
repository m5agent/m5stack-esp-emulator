# Unit KMeter-ISO v1.1 · U133-V11

本模型保留本款官方 STL 的两件原壳：component 0 前壳 2252 三角，component 2 后壳 2032 三角；两者同用平移 `[0,-16,-4]`，没有独立移动、缩放、切壳或填孔。component 1、3 是移开副本。原生前后凹台、卡扣、M5 浮雕、Grove 开口、热电偶接口开口、安装孔和接缝继续由原几何承载。

模型单位为 mm，+X 右、+Y 热电偶端、+Z 标签正面。官方 56×24×8 归一化为 X×Y×Z = 24×56×8。两个原生安装孔中心为 `[-8,-16]`、`[8,-16]`，原孔面没有重写。状态保持 `modeled`。

实体包括有安装孔、插座退让和焊脚孔的 PCB，STM32F030F4P6、CA-IS3641HW、MAX31855KASA+T、MD5333、贴片元件、隐藏 SWD 焊盘、固定螺钉、红色开顶 Grove 及 PCC-SMP-K-100-CE 插座。K 插座有两个不等宽的实际扁槽、完整内壁、凹入金属弹片、实心后止挡、金属卡带、折脚和通孔端子；Grove 有四触点及穿板折脚。它不是用 Grove 零件改色代替 K 型插座。

PCB 轮廓、板厚/高度、器件安装位置/包络、脚弯、焊盘及插座内部尺寸参考本款裸板与端面照片重建。模型中的 K 槽中心 X 为 ±4，宽度分别 2.5/3.3、高 0.9、中心 Z 0.8，轴向深度 12.1；这些是按本款照片与原壳比例推导的外观尺寸，不能用于生产配合。具体可视形状与原壳闭合不依赖贴纸。公开图片没有给出附送探头的已装机械尺寸，本次没有提供探头附件。

`Model` 是独立设备，`GroveModule` 包含同一整机与四根线、两个插头。外部框架可寻址以下组件：

| ID | 类型 | 用途 |
| --- | --- | --- |
| `grove` | Port / `grove` | 黑 GND、红 5V、黄 SDA、白 SCL；外观接线 |
| `thermocouple` | Port / `thermocouple-k-mini-flat` | K 型扁口，T+ Chromel、T− Alumel；拒绝 Grove 附件 |
| `sensor` | Component | 被动外观锚点，状态 `{}`，不处理测温命令 |
| `unitFrame` | 仅 GroveModule | 整机可视姿态 |
| `cable` | 仅 GroveModule | 四芯线、两插头的姿态与弯曲 |

```js
import { Model, GroveModule } from './src/units/kmeter-iso-v11/index.js';

const unit = new Model();
const linked = host.port('grove').attach(new GroveModule({ cableLength: 70 }));
host.handle({ type: 'pose', target: 'grove/unitFrame', position: [0, 110, 0], rotation: [0.15, 0, 0.2] });
host.handle({ type: 'cable', target: 'grove/cable', slack: 12, bend: [0, 0, -1] });
const kSocket = linked.port('thermocouple');
console.log(kSocket.connector); // thermocouple-k-mini-flat
host.update(1 / 60);
```

示例假设主机端口 ID 是 `grove`；使用其他端口时替换路径前缀。Port 完成几何挂接和寻址，不实现 I2C、热电势、温度、冷端补偿、采样、开短路、隔离电气或器件协议。没有按钮、旋转关节或模拟热胀。v1.1 原理图的红色 LED1 只建隐藏非发光封装；本款照片与原壳没有独立证实外露光路，因此没有注册指示灯，也没有从旧 U133 ESP32-C3 版本引入白色电源灯。

贴纸与标记见 [artwork.md](artwork.md)。按模型分别传入 `{ artwork: false }` 可关闭最终 PNG；原壳、所有实体、接口与物理矩阵不会改变。

[smoke.json](smoke.json) 记录有限本地检查：完整原壳指纹与包络，安装孔贯穿和 FrontSide 孔壁、两种 K 扁槽的深度/壁面/金属弹片/实体止挡、Grove 四芯与姿态/接拆/资源释放、被动接口和贴纸开关物理不变。没有浏览器逐面检查、硬件、电气、温度或生产配合验收。

官方产品页特性写 ±2%、规格表写 ±2°C，已通过 M5Stack 官方助手提交资料反馈，回执 `8db82bebd10244b0ad7e3c875f0fa3ad`。本模型不选择或实现其中一种精度。来源及指纹见 [sources.json](sources.json)。官方 CAD 衍生保留 [M5_Hardware MIT](../../../licenses/M5_Hardware-MIT.txt)。

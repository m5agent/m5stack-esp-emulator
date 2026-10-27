# Mini PDM / Mini BPS v1.1 / MIC 接入

2026-10-26。本批U089、U090-B、U096均导出 `Model` / `GroveModule` / `spec`，保留真实四芯 `grove` 与被动 `sensor` 外观锚点。MIC另有真实外露调节头的 `threshold` 视觉关节。模型负责实体和外驱形状，PDM时钟、音频/录音/采样、压力/温度/海拔、ADC/比较阈值、固件和电气由外部框架实现。

| 产品ID | SKU | 本款真实感测实体 | 额外外驱形状 |
| --- | --- | --- | --- |
| `mini-pdm` | U089 | SPM1423数字MEMS麦克风、声孔/腔深与PCB | 无 |
| `mini-bps-v11` | U090-B | QMP6988金属气压封装、气孔与HT7533/PCB | 无 |
| `mic` | U096 | 驻极体圆麦克风、MAX4466/LM393与PCB | `threshold` 调节螺槽头 |

毫米尺度，+X右、+Y顶部、+Z正面，具体封装/锚点朝向见各 `dimensions.js`、`cad-map.json` 与研究记录。无虚构按钮、灯、屏幕、喇叭、可视声波或压力动画。声学/气压孔保留真实开放和内部深度，封装、PCB及标签物理载体独立于PNG，印刷不补缺件。

Mini BPS严格v1.1 U090-B/QMP6988/24×24×8mm，不混用旧U090的BMP280、13mm或印刷。Mini PDM官方表标称24×24×13mm，本款尺寸图与完整原CAD为24×24×8mm，模型保留原壳不缩放并分别记录名义/实际包络；尺寸矛盾已反馈 `dcd6f74080ea478f8745ce19d5542ab8`。PDM的SPM1423封装按芯片资料3.760×4.720×1.310mm、Ø0.840声孔建形，不套用通用小盒。MIC本款24×32×8mm，实际驻极体、蓝色电位器固定杯与金属调节头分别建形。PDM与BPS的原壳均为8mm，含各自推导薄膜后的视觉总厚分别为8.05mm、8.04mm，不能把这点膜厚当作厂商尺寸公差。隐藏安装、局部颜色、板位及配准仍含已记录的外观推导，不作制造或声学标定。

## 三分支四芯连接

```js
import {loadModel, loadGroveModule} from '../src/loaders.js';

const host = await loadModel('sticks3');
const hub = await loadGroveModule('hub');
host.port('grove').attach(hub);
const pdm = await loadGroveModule('mini-pdm', {cableLength: 65});
const bps = await loadGroveModule('mini-bps-v11', {cableLength: 80});
const mic = await loadGroveModule('mic', {cableLength: 95});
hub.port('grove-1').attach(pdm);
hub.port('grove-2').attach(bps);
hub.port('grove-3').attach(mic);

host.handle({type: 'pose', target: 'grove/grove-3/unitFrame',
  position: [90, 190, 8], rotation: [.1, -.2, .15]});
host.handle({type: 'cable', target: 'grove/grove-3/cable',
  slack: 12, bend: [0, 0, -1]});
host.handle({type: 'joint', target: 'grove/grove-3/threshold',
  angleDeg: 90, durationMs: 120});
host.update(1 / 60);
```

每支线渲染四根导线和两端插头。`unitFrame`改变整款姿态，`cable`改变线形；挂接不建立时钟、I2C、模拟/数字输出或供电行为。各款 `sensor` 只给真实感测实体的位置/朝向，状态为空，拒绝音频、压力、温度或海拔数值命令。

## MIC调节头

`threshold`只旋转本款可见金属螺槽头，固定蓝色杯体、麦克风、PCB、Grove及标签保持。支持 `angleDeg` / `durationMs`，范围为视觉预览约束 `[-135,135]`，并非量产机械止挡或10K阻值标定；拒绝非零RPM，越界命令保留旧状态。角度0恢复原始中性姿态。

外驱不回送用户输入，也不改变比较电压、增益、数字电平或音频。需要设置实际设备/模拟器阈值时，由外部框架自行定义和驱动；不能把视觉角度当作电气参数。

## 印刷与释放

本批5张PNG均为严格本款官图代码重绘 `reference-redraw`：Mini PDM正背2、Mini BPS v1.1正背2、MIC背标1。没有匹配的精确机身原稿，不借旧型号或包装稿，不裁产品照片、不编造不可辨小字。字体/颜色及配准含照片推导。CSV、私有链接/映射、矢量原稿、生成器及中间件留在仓库外，仅公开最终普通PNG、衍生几何和安全来源。

两入口传 `artwork:false`关闭印刷，壳/PCB/封装/声孔/气孔/胶贴物理载体及所有物理attributes/index/世界矩阵保持。用 `hub.port('grove-2').detach()`可独立释放BPS分支，其余分支保持。`detach({dispose:false})`保留的模块由调用方重新装入或释放；最终 `host.dispose()`释放仍挂载的装配树。

总入口别名为 `MiniPdmUnit` / `MiniPdmUnitModule`、`MiniBpsV11Unit` / `MiniBpsV11UnitModule`、`MicUnit` / `MicUnitModule`。必要专项 `node scripts/check-audio-pressure-units.mjs`覆盖三分支四芯、被动锚点/内部命令拒绝、MIC实际调节头有限角/插值/精确回位及固定件保持、两入口印刷全物理一致性与独立装拆。单品来源及smoke见各研究目录；综合范围见[本批进度](../artifacts/audio-pressure-expansion/progress.json)。保持 `modeled`，没有逐面浏览器、全量历史或实物验收。

当前基线含此前AC Measure/AIN4-20mA/BLDC Driver的端子闭合修订，其新SHA及历史快照关系见[端子修复](TERMINAL-TONGUE-CLOSURE.md)，本批不修改那些产品源。

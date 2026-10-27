# ADC v1.1 / AMeter / VMeter 接入

2026-10-26。本批新增U013-V11、U086、U087。三款均导出`Model`、`GroveModule`、`TerminalPlug`、`spec`，提供`grove`、`terminal`和被动`sensor`。模型负责外观、可拆附件和外驱螺钉头，不执行ADC采样、电流/电压、校准、熔断、隔离、固件或电气行为。

| 型号 | 模型轴名义尺寸 mm | 端子与真实外驱实体 | 同步印刷 |
| --- | --- | --- | --- |
| `adc-v11` U013-V11 | 24×32×10.2 | `terminal`=`ht3.96-2p`，随附两螺钉插头；没有灯或按钮 | 正背2张参考重绘PNG |
| `ameter` U086 | 24×56×8壳体 | `terminal`=`ht3.96-4p`，随附四螺钉插头；`power`单指示灯 | 正背2张参考重绘PNG |
| `vmeter` U087 | 24×56×8壳体 | `terminal`=`ht3.96-4p`，随附四螺钉插头；`power-led`单指示灯 | 正背2张参考重绘PNG |

采用+X右、+Y测量端子端、+Z正面。厂商尺寸顺序ADC为32×24×10.2，两款电表为56×24×8。两款电表的8mm指原壳；固定端子凸出后总厚另按各自`dimensions`与catalog的`visualEnvelopeMm`记录，不缩掉端子来凑名义壳厚。隐藏PCB布局、封装厚度、插头弹片、安装深度和配合间隙保留明确的外观推导，未做量产配合验收。

## 连接、姿态和生命周期

```js
import {loadModel, loadGroveModule} from '../src/loaders.js';

const host = await loadModel('sticks3');
const hub = await loadGroveModule('hub');
host.port('grove').attach(hub);
const ids = ['adc-v11', 'ameter', 'vmeter'];
for (const [i, id] of ids.entries()) {
  const unit = await loadGroveModule(id, {
    cableLength: 65 + i * 15,
    terminalPlug: true,
  });
  hub.port(`grove-${i + 1}`).attach(unit);
}

host.handle({type: 'pose', target: 'grove/grove-1/unitFrame',
  position: [0, 85, 8], rotation: [.1, -.2, .15]});
host.handle({type: 'cable', target: 'grove/grove-1/cable',
  slack: 12, bend: [0, 0, -1]});
```

各Grove分支渲染四芯线。`unitFrame`控制产品位置/旋转，`cable`控制线缆形状，二者只影响视觉。`hub.port('grove-2').detach()`拆除AMeter并释放该分支，其他两支保持；`host.dispose()`释放当前装配树。保留拆下附件时使用`detach({dispose:false})`，由调用者负责重新装入或释放。

## 可拆测量插头与螺钉

三款默认显示真实固定座；`terminalPlug:true`安装随附插头。可以从产品入口导入`TerminalPlug`，或从总入口导入`AdcV11TerminalPlug`、`AmeterTerminalPlug`、`VmeterTerminalPlug`。对应主模型/模块别名为`AdcV11Unit`/`AdcV11UnitModule`、`AmeterUnit`/`AmeterUnitModule`、`VmeterUnit`/`VmeterUnitModule`。

```js
host.handle({type: 'joint', target: 'grove/grove-1/terminal/screw-1',
  angleDeg: 45, durationMs: 120});
host.update(1 / 60); // 每帧推进视觉插值

const ameter = hub.port('grove-2').module;
const plug = ameter.port('terminal').detach({dispose: false});
ameter.port('terminal').attach(plug);
```

ADC的`screw-1`…`screw-2`、两款电表的`screw-1`…`screw-4`只改变实际螺钉头角度。`angleDeg:0`回到各自原始中立朝向；`durationMs`可做外部指定插值，非零`rpm`抛错。没有紧固扭矩、轴向螺纹、压线、电气连接或测量状态。固定座、PCB、其他螺钉及Grove帧保持，外驱命令不回送用户输入。端子接口拒绝Grove模块，机械类型不执行导通判断。端子文字顺序与电气针号分别按各款来源记录，不从四孔外观猜测网络。

## 指示灯与外部框架

AMeter的`power`、VMeter的`power-led`各自默认关闭，可独立设置亮度：

```js
host.handle({type: 'led', target: 'grove/grove-2/power', brightness: .43});
host.handle({type: 'led', target: 'grove/grove-3/power-led', on: true});
```

两款都有本款照片与壳口支持的单灯光路，但现有官方资料未确认实际发光色。AMeter暖白`#fff6d5`、VMeter中性白`#ffffff`均为固定预览色，仅作外观估计，元数据保留`colorConfirmed:false`与证据说明，不能当成官方白灯规格或RGB硬件能力。按外部亮度显示，不接受任意改色，也不自动与Grove供电、电流、电压或螺钉动作联动。ADC v1.1没有虚构可见灯、按键或旋钮。

`sensor`只作视觉锚点；ADC采样、数值、寄存器、通信、保险丝状态与保护行为由外部框架持有。各款PCB、器件封装和背贴框图是实体或固定印刷，均不表示已实现对应电路。ADC文档中ADS1110/ADS1100与基准/采样率差异按自身原理图区分并保存官方反馈；不据冲突文字生成运行行为。

## 同步贴纸与必要检查

本批私表无精确原稿，按用户授权使用各自同型号官方照片代码重绘正背6张高清PNG，全部标`reference-redraw`。未裁产品照片当贴纸，不套相似型号。来源、可辨文字与配准范围见各款`docs/research/<id>/artwork`记录。公开普通最终PNG与自写说明；私表、下载链接、原稿名、矢量、原始官图和生成中间材料留在仓库外。

每个模型或Grove模块单独传`artwork:false`，仅移除印刷层，原壳、真实孔、PCB、触点、插头、螺钉及物理世界姿态保持。专项同时覆盖插头显示/隐藏两种配置。

运行`node scripts/check-adc-meter-units.mjs`执行真实StickS3→HUB三分支四芯线、两/四/四螺钉头插值与精确复位、可拆端子、灯独立、非Grove类型、被动锚点和贴图物理不变检查。单品smoke与冻结来源见各款研究目录；构建、在线资源字节与隐私结果以[本批进度](../artifacts/adc-meter-expansion/progress.json)为准。

阶段保持`modeled`，未执行逐面浏览器、全量历史或实物配合验收。GitHub `main`的`ad5d062`保存85款同步快照；本批属于随后本地增量，没有自动再次提交推送。

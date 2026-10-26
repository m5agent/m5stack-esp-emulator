# TimerPWR / ExtEncoder / NFC 接入

2026-10-26。本批新增 U189、U161、U216；每款提供 `Model` / `GroveModule`、`grove` 及被动 `sensor`。模型负责实体外观、外驱形状和输入意图，外部框架负责固件、协议、数值和电气行为。官方来源、隐藏安装推导、几何和贴纸配准分别保存在 `docs/research/<id>/`，不把隐藏安装估计当作量产配合基准。

| 产品 | 模型轴尺寸 mm | 真实接口与控件 | 对应印刷 |
| --- | --- | --- | --- |
| `timerpwr` U189 | 24×40×11 | `lcd` 64×48白单色OLED；`button-a`左 / `button-b`右；`power-led`固定红；`usb` / `battery` / `grove` | 4张同型号官图参考重绘PNG |
| `extencoder` U161 | 24×32×10.7 | `encoder`五芯座、可选随附五螺钉插头、`grove`；本体没有旋钮/按钮/LED | 2张同型号官图参考重绘PNG |
| `nfc` U216 | 24×48×8 | `grove`；ST25R3916板、平面天线与匹配器件实体；没有灯/按钮/可动件 | 2张精确机身原稿恢复栅格PNG |

尺寸按 +X右、+Y顶部、+Z正面。厂商尺寸顺序分别为40×24×11、32×24×10.7、48×24×8。各款原生壳保持尺度和孔口，PCB、屏幕深度、插座、触点和端口后的实体独立存在；贴纸不用于遮盖缺件。

## 三分支四芯连接

```js
import {loadModel, loadGroveModule} from '../src/loaders.js';

const host = await loadModel('sticks3');
const hub = await loadGroveModule('hub');
host.port('grove').attach(hub);
const timer = await loadGroveModule('timerpwr', {cableLength: 65});
const encoder = await loadGroveModule('extencoder', {
  cableLength: 80, terminalPlug: true,
});
const nfc = await loadGroveModule('nfc', {cableLength: 95});
hub.port('grove-1').attach(timer);
hub.port('grove-2').attach(encoder);
hub.port('grove-3').attach(nfc);

host.handle({type: 'pose', target: 'grove/grove-1/unitFrame',
  position: [0, 85, 8], rotation: [.1, -.2, .15]});
host.handle({type: 'cable', target: 'grove/grove-1/cable',
  slack: 12, bend: [0, 0, -1]});
```

每个分支渲染4根线。`unitFrame`控制产品姿态，`cable`控制线姿态；拆一支保持兄弟分支。`host.dispose()`释放装配树。需要保留附件再装时，使用 `detach({dispose:false})` 并由调用者接管生命周期。

## TimerPWR

`button-a` / `button-b`沿原生侧弹舌变形，行程0.22mm为外观推导，固定铰接端保留。输入通过通用 `down` / `up` / `click` / `longpress` 事件发送；`cancel`发取消的`up`，不发`click`。外部按压示例：

```js
host.on('input', event => externalFramework.receive(event));
host.handle({type: 'button', target: 'grove/grove-1/button-a',
  action: 'press', source: 'external'});
host.update(1 / 60);
host.handle({type: 'button', target: 'grove/grove-1/button-a',
  action: 'release', source: 'external'});
// 丢失指针/取消输入时，用相同source与action:'cancel'。
host.handle({type: 'display', target: 'grove/grove-1/lcd', fill: '#dedede'});
host.handle({type: 'led', target: 'grove/grove-1/power-led', brightness: .37});
```

屏幕正面+Z，像素右向+X、上向+Y（USB端）。`lcd`接受外部RGBA framebuffer，保留调用者缓冲，渲染时映射白单色；不会自动画时钟、计时器、电池或INA3221读数。按键、灯和屏幕各自独立。调用者每帧执行`update(dt)`推进形状插值。

`usb`类型`usb-c-charge-only`，`battery`类型`mx1.25-2p`；均为机械视觉接口。官方明确USB仅充电，不能直接向Grove供电，这只记录为元数据，不生成充电或供电状态机。D4固定红色；产品引脚表称PB4为充电灯，原理图却把PB4标为BAT_CHRG输入，D4接在5V_OUT。来源记录保留这项差异及官方反馈回执，模型不自动把D4绑定到任何状态。

## ExtEncoder

本体是外接AB/ABZ编码器采集盒，没有转子。`encoder`为`vh2.54-5p`机械接口；真实5触点按本款印字G/5V/Z/B/A排列。`terminalPlug:true`安装随附绿色五螺钉插头。也可以从产品入口导入`TerminalPlug`，或总入口导入`ExtEncoderTerminalPlug`后手动装配。

```js
host.handle({type: 'joint', target: 'grove/grove-2/encoder/screw-1',
  angleDeg: 45, durationMs: 120});
const plug = encoder.port('encoder').detach({dispose: false});
encoder.port('encoder').attach(plug);
```

`screw-1`…`screw-5`只改变真实头部角度；不表示螺纹轴向运动、扭矩、压线或电气连续性，拒绝非零RPM。固定座、PCB和Grove线保持。插头尺寸、插入深度、弹片和配合间隙按照片推导，未做量产配合验收。被动`sensor`不计算ABZ、计数、角度、速度或电压。

## NFC 与印刷边界

NFC严格使用U216 ST25R3916自身原壳、PCB、线圈和匹配件；隐藏布线、天线圈数和安装Z属于明确标注的外观重建。`sensor`只作视觉锚点，不接受扫描、标签、读写、卡模拟或RF场命令。

本批8张最终PNG同时接入：TimerPWR4张和ExtEncoder2张标记`reference-redraw`；NFC正背2张标记`source-vector-raster`，恢复转换器复合字形轮廓方向，恢复范围见单品`artwork`记录。源恢复不宣称原稿未经修改直接导出。公开仅普通PNG、配准及来源说明，私表、下载链接、原文件名、矢量和中间材料留在仓库外。

每个模型/模块分别传`artwork:false`关闭印刷层，所有物理buffer、index和世界姿态保持。默认与可拆插头配置都在本批专项中检查。USB、电池、五芯接口拒绝Grove类型，类型限制只表示机械配对。

## 本批必要验证

运行`node scripts/check-timer-encoder-nfc-units.mjs`执行真实StickS3→HUB三分支夹具，覆盖四芯连接、两按键压放/取消、外部屏幕与独立红灯、五头角度/插拔、被动锚点、接口类型和贴图开关。单品smoke与来源冻结见各自研究目录；构建、在线资源字节和隐私检查结果见[本批进度](../artifacts/timer-encoder-nfc-expansion/progress.json)。

阶段保持`modeled`。本批不执行耗时逐面浏览器、全量历史或实物验收。此前85款已同步GitHub `main` 的`ad5d062`；本批和前批DAC2/DDS/KMeter是该提交之后的本地增量，未自动再次推送。

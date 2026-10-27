# Earth / Hall / QRCode

本批三款提供独立 `Model` 与包含两只插头、四根实体导线的 `GroveModule`。所有坐标单位为毫米，+X 右、+Y 上、+Z 正面。模型提供完整物件外观、真实控件形状与输入意图，外部框架负责模拟量、阈值、磁场、识别、音频和协议。

| 产品 | 外观实体与 API |
| --- | --- |
| `earth` / U019 | 原生外壳、双叉探针 PCB、电极、10K 可调电阻和 Grove；调节头为 `trim` 位置关节，`sensor` 只是视觉锚点 |
| `hall` / U084 | 完整原生外壳、PCB、三颗 A3144E、逻辑芯片、稳压器和 Grove；`sensor` 为视觉锚点，没有虚构按钮或转轴 |
| `qrcode` / U173 | 原壳、M14 采集组件、镜头/光窗、PCB、蜂鸣器和 Grove；`button` 为瞬时触发键，`mode` 为稳定通讯滑块；`illumination` 固定白光、`aiming` 固定红光，独立外驱 |

实际模型轴尺寸与厂商尺寸顺序分别记录在 `spec.nominalMm` / `vendorDimensionOrderMm`；原生 CAD 和附加贴层的可视包络另记，不缩放原壳强行符合另一口径。来源与内部安装推导见 [Earth](research/earth/modeling.md)、[Hall](research/hall/modeling.md)、[QRCode](research/qrcode/modeling.md)。

## 独立模型与真实机械控件

```js
import {loadModel, loadGroveModule} from 'm5stack-models.js/loaders';

const earth = await loadModel('earth');
earth.handle({type:'joint', target:'trim', angleDeg:30, durationMs:160});
earth.update(.16);
earth.handle({type:'joint', target:'trim', angleDeg:0});

const qr = await loadModel('qrcode');
qr.get('illumination').set({brightness:.5});
qr.get('aiming').set({brightness:.35});
qr.button('mode').setPosition(1); // 仅设置稳定滑块的视觉位置
qr.button('button').press('external-ui');
qr.update(.2);
qr.button('button').cancel('external-ui'); // 回位，不产生 click
qr.update(.2);
```

Earth 只有实际外露可调电阻的调节头转动。`trim` 接收 `angleDeg` / `durationMs`，拒绝非零 `rpm`；演示角度范围不是已测机械限位，也不代表电阻值、输出电压、比较器阈值或土壤湿度。探针、电极、PCB 和 Grove 保持固定；`sensor` 不接受数值或测量命令。

QRCode 的 `button` 发出按下/弹起/点击或取消输入意图，真实帽体随动；按键不会自动点灯、发声或执行扫码。`mode` 只保留其物理档位，不执行串口/I2C 切换。两个光输出保持各自实际颜色，亮度和开关独立，默认均关闭；不投射虚构扫描圈、读码结果或摄像画面。

Hall 原理图的 D1 是内部红色 LED，现有原壳与同型号照片未确认独立外露光路，因此保留隐藏封装，不虚构灯孔或可见 LED API。`sensor` 不执行磁场/磁极判断或输出电平，也不会因视觉附件接近自动点亮内部器件。

## QRCode 固定折射头配置

```js
const withRefractor = await loadModel('qrcode'); // 默认装固定折射头
const direct = await loadModel('qrcode', {refractor:false});
const wiredDirect = await loadGroveModule('qrcode', {
  refractor:false, cableLength:90,
});
```

两种配置均按官方原生零件装配。折射头为固定附件，改变观察光路和外形；取下后展示真实直视扫描头。它没有模型内旋转关节，也不执行光学追踪或识别。demo 中对应 `refractor` / `direct` 配置。附件的 CAD 包络与正文名义规格有差别，原尺寸分别保留，不能视为生产配合验收。

## Grove 三分支与输入寻址

```js
const host = await loadModel('sticks3');
const hub = await loadGroveModule('hub', {cableLength:60});
host.port('grove').attach(hub);
hub.port('grove-1').attach(await loadGroveModule('earth', {cableLength:65}));
hub.port('grove-2').attach(await loadGroveModule('hall', {cableLength:80}));
hub.port('grove-3').attach(await loadGroveModule('qrcode', {cableLength:95}));

host.handle({type:'joint', target:'grove/grove-1/trim', angleDeg:25});
host.handle({type:'led', target:'grove/grove-3/illumination', brightness:.45});
host.on('input', event => {
  // 例如 grove/grove-3/button；外部框架在这里决定设备行为。
  console.log(event.id, event.action);
});
host.handle({type:'pose', target:'grove/grove-3/unitFrame',
  position:[35,120,8], rotation:[.1,-.2,.15]});
host.handle({type:'cable', target:'grove/grove-3/cable', slack:12, bend:[0,0,-1]});

const saved = hub.port('grove-2').detach({dispose:false});
hub.port('grove-2').attach(saved);
host.dispose();
```

三分支示例证明机械挂接、四芯线姿态与组件寻址，不表示 HUB 可以执行对应模拟/数字/UART/I2C 协议。挂载时模型不进行电气兼容、供电或总线判断。真实端口引脚与坐标由单品记录提供，不从贴纸图案推导电气。

## 同批贴纸与边界

本批共7张PNG（含Earth可选中文教育版）。Earth保留原稿的字形和图案轮廓，依据用户预览/同型号标准官图恢复转换时丢失的填色与可见层，标`source-vector-raster`并记录恢复范围；默认英文EARTH，中文“土壤湿度”只在`stickerVariant:'education-cn'`时启用，共2张。QRCode使用3张精确机身原稿栅格，排除包装/不相关版本；Hall缺精确原稿，正背2张使用标明来源的`reference-redraw`。每款 `artwork.json` 记录实际面、分辨率、配准与 SHA256；不复制产品照片像素当贴纸。

```js
const bare = await loadModel('earth', {artwork:false});
const education = await loadModel('earth', {stickerVariant:'education-cn'});
const bareHost = await loadModel('sticks3', {artwork:false});
bareHost.port('grove').attach(await loadGroveModule('qrcode', {
  artwork:false, refractor:false,
}));
```

每个独立模型/模块分别传 `artwork:false`，主机选项不自动传播。关闭贴层保留所有原壳、安装孔、探针、可调头、镜头、按键、滑块和连接器。私有表、下载链接、原稿文件名、矢量、映射、生成器和中间素材全部保留仓库外；公开只最终普通 PNG、配准和来源说明，印刷设计/商标保留其权利。

必要局部/API 检查入口为 `node scripts/check-earth-hall-qrcode-units.mjs`，单品结构检查记录在 `docs/research/<id>/smoke.json`。范围包含实际三分支四芯线、真实调节头、按钮压放/取消、稳定滑块、独立固定色灯、贴纸开关与实体不变、独立拆离；Node 图形边界替身不提供浏览器像素证据。没有逐面浏览器、全量历史目录、实物、电气、磁场、声学或识别验收，阶段保持 `modeled`。

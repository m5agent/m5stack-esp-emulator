# Step16 / ASR / UHF-RFID

本批三款均提供独立 `Model` 和含两只插头、四根实体导线的 `GroveModule`。模型坐标为毫米，+X 向右、+Y 向上、+Z 朝产品正面；`vendorDimensionOrderMm` 单独保留厂商尺寸顺序。模型拥有外观和外部驱动的形状，固件、协议、数据、声音与电气行为由接入框架实现。

| ID / SKU | 模型轴尺寸 | 真实实体与可用 API |
| --- | --- | --- |
| `step16` / U198 | 24 × 32 × 16.9 mm；厂商顺序 32 × 24 × 16.9 | 原生旋钮/轴的 `rotation`；八个独立暖黄 `segment-a`…`segment-g`、`segment-dp`；独立 `rgb`；`grove` 与被动 `sensor` |
| `asr` / U194 | 24 × 48 × 16 mm；厂商顺序 48 × 24 × 16 | 完整原壳、CI-03T、固定内置喇叭、模拟麦克风声孔/保护网；仅 `grove` 与被动 `sensor`，没有虚构的按钮或外露灯 |
| `uhf-rfid` / U107 | 48 × 56 × 11.5 mm；`vendorDimensionOrderMm` 为 56 × 48 × 11.5 | 四孔/挂带槽原壳、JRD-4035板堆与实体陶瓷天线、真实Grove；仅 `grove` 与被动 `sensor` |

尺寸来自各款 `spec`。Step16 背贴增加约 0.008 mm，ASR 正面实物贴膜增加约 0.012 mm；UHF 原壳分面实测 Y 为约 55.989 mm，贴层增加约 0.008 mm。这些实际可视包络另记在 `visualEnvelopeMm`，不通过拉伸外壳消除来源差别。隐藏 PCB、封装、内部接线和安装深度的推导范围见各款 [Step16](research/step16/modeling.md)、[ASR](research/asr/modeling.md)、[UHF-RFID](research/uhf-rfid/modeling.md) 研究记录。

## Step16 旋钮与独立灯光

```js
import {loadModel, loadGroveModule} from 'm5stack-models.js/loaders';

const step = await loadModel('step16');
step.handle({type:'joint', target:'rotation', angleDeg:22.5});
step.handle({type:'joint', target:'rotation', angleDeg:11.25, durationMs:160});
step.handle({type:'led', target:'segment-a', brightness:.7});
step.handle({type:'led', target:'segment-dp', brightness:.35});
step.handle({type:'led', target:'rgb', color:'#22b477', brightness:.55});
step.update(.16); // DeviceViewer 已负责逐帧 update；自建渲染器自行调用
```

`rotation` 只带动真实原生旋钮和轴，固定开关座、前壳、数码段与 RGB 不跟转。元数据记录 16 定位和 22.5° 间隔；外部可给中间角度，模型不自动吸附、旋转、编码或点灯，不接受非零 rpm。原 CAD 静止位置只是视觉基准，不代表 BCD 零码、码序或固件方向。没有旋钮按压按钮，也不是步进电机。

八个显示段的外观固定为暖黄/琥珀色，各自只接受 `on` / `brightness`，任意颜色请求不改变实际颜色。`rgb` 独立接受 `color` / `on` / `brightness`。九灯默认熄灭，互不联动。原白色前膜保持，局部光外观把段光显示在真实膜上；亮色/光扩散是照片重建，不是光学仿真。数码段以 LED 寻址，没有 LCD framebuffer 或内置十六进制字码表；外部框架自行决定角度、BCD、字码和灯光之间的关系。外驱状态不回送输入意图。

## Grove 三分支装配与寻址

```js
const host = await loadModel('sticks3');
const hub = await loadGroveModule('hub', {cableLength:60});
host.port('grove').attach(hub);
hub.port('grove-1').attach(await loadGroveModule('step16', {cableLength:65}));
hub.port('grove-2').attach(await loadGroveModule('asr', {cableLength:80}));
hub.port('grove-3').attach(await loadGroveModule('uhf-rfid', {cableLength:95}));

host.handle({type:'joint', target:'grove/grove-1/rotation', angleDeg:45});
host.handle({type:'led', target:'grove/grove-1/segment-g', brightness:.6});
host.handle({type:'led', target:'grove/grove-1/rgb', color:'#37c98b', brightness:.4});
host.handle({type:'pose', target:'grove/grove-3/unitFrame',
  position:[45,120,8], rotation:[.1,-.2,.15]});
host.handle({type:'cable', target:'grove/grove-3/cable', slack:12, bend:[0,0,-1]});
host.update(1/60);

// 只拆掉 ASR 分支；其余 Unit 的姿态、灯光与四芯线继续保留。
const saved = hub.port('grove-2').detach({dispose:false});
hub.port('grove-2').attach(saved);
host.dispose(); // 最终释放整棵装配树
```

三分支示例只展示机械装配、线缆姿态和组件寻址。Step16 的 Grove 记录 GND / 5V / SDA / SCL，ASR 与 UHF-RFID 记录 GND / 5V / RXD / TXD。把它们画在同一 HUB 上不声明 HUB 可以路由相应 I2C/UART 协议，也不实现供电或总线通信。

ASR 的 `sensor` 只是 CI-03T 位置锚点，没有采音、识别、唤醒、声纹、播放或数据接口。固定喇叭的锥盆、悬边、篮架、磁体、内部插座与引线有实体深度，麦克风有真实声孔和保护网；没有模拟振膜动作。正文喇叭规格为 8Ω@0.8W，准确型号的官方背贴印 8Ω@1W；重绘保留实物印字并记录差别，模型不替两份来源选择电气额定值。原理图 D4 为红灯，但没有确证外露光路，因此不注册猜测的 Led；背贴蓝色灯泡是印刷图符。Unit U194 不套用 Module ASR M147 的 USB、按键或方壳。

UHF-RFID 的 `sensor` 是陶瓷天线/模组视觉锚点，`getState()` 为空对象，没有 scan/read/write/tag/RSSI/UART 命令。挂带槽和安装孔保持真实贯通，壳扣是固定壳体结构；没有虚构按键、外露灯、USB 或外置天线接口。PCB 堆、无字屏蔽罩、陶瓷天线电极与馈通的隐藏安装含推导，不声明 RF 电路、读距或生产配合。

## 本批五张贴纸

| 产品 | PNG 与来源 | 具体范围 |
| --- | --- | --- |
| Step16 | 1 张 `reference-redraw` | 同型号官方背照准确代码重绘完整背贴；前面和帽在实物中是白色，不增印刷 |
| ASR | 2 张 `reference-redraw` | 同型号官图重绘正面竖贴与背面电路图；正面实物贴膜跨过中央格栅，原孔及真实喇叭保留 |
| UHF-RFID | 背面 1 张 `official-vector-raster`，正面 1 张 `reference-redraw` | 背贴使用用户提供的准确型号原稿直接栅格化，保留当前 `UP TO 1M` 与黑色标题版本；正面按准确官图重绘天线/标签图形 |

UHF 背贴为 2400 × 2400 PNG / 30 × 30 mm，正面为 3300 × 2200 PNG / 33 × 22 mm；旧官图上的 2M/蓝色标题不覆盖用户提供的新原稿。Step16 与 ASR 的字号、颜色和配准仍为照片推导，高清不表示原厂矢量精度。来源、像素、定位和 SHA256 见各款 `artwork.json`。公开只最终普通 PNG 与配准代码，表格、私有下载链接、矢量原稿、生成器和中间件留仓库外，商标与印刷设计保留权利。

```js
const bare = await loadModel('asr', {artwork:false});
const bareHost = await loadModel('sticks3', {artwork:false});
// 每个独立加载的模块都应各自传入，主机选项不会自动传播。
bareHost.port('grove').attach(await loadGroveModule('uhf-rfid', {
  cableLength:70, artwork:false,
}));
const bareStep = await loadGroveModule('step16', {artwork:false});
```

关闭贴纸只移除印刷，保留完整原壳、孔、连接器、原旋钮与光导、背后 PCB、喇叭、麦克风和天线实体。活动物件上的印刷随所属物件，无需外部逐帧重新配准。

本批必要局部/API 检查入口为 `node scripts/check-step-asr-uhf-units.mjs`，检查三款四芯装配、Step16 旋钮/九灯独立状态、被动锚点、姿态与独立拆离、贴纸关闭的实体不变；单品 `docs/research/<id>/smoke.json` 记录结构细项。Node 图形边界替身不提供浏览器像素证据。未做逐面浏览器、全量历史目录、硬件、电气、声学或 RF 验收，三款保持 `modeled`。

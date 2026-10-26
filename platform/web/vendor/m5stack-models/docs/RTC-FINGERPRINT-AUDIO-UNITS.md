# RTC / Fingerprint2 / AudioPlayer

三款都使用独立 `Model` 与带四芯线的 `GroveModule`。毫米坐标为+X右、+Y上、+Z正面。接口和封装描述实际外观，下游负责时钟、识别、播放、串口和电气。

| ID | 型号 / 实体 | 可控外观 |
| --- | --- | --- |
| `rtc` | U126，HYM8563、PCB和内置纽扣电池，完整封闭双壳 | `sensor`视觉锚点；未虚构可拆电池接口 |
| `fingerprint2` | U203，A-K323CP电容采集面、环形导光件、PCB | `ring-led` RGB；`power-led`固定蓝色 |
| `audioplayer` | U197，N9301、microSD座、3.5mm立体声插座、PCB | `busy-led`固定蓝色；`sd` / `audio`为实际插座 |

Fingerprint2没有机械按键。采集面只提供外观与定位，不将触面伪装成可压帽，不读取指纹或保存用户数据。RGB只承接外部颜色/亮度，七色串口指令、呼吸灯和识别后红绿反馈由外部负责。两款的蓝色指示灯只接受独立on/brightness输出，不自动联动识别或播放。

```js
import {loadModel, loadGroveModule} from 'm5stack-models.js/loaders';

const host = await loadModel('sticks3');
const hub = await loadGroveModule('hub', {cableLength:60});
host.port('grove').attach(hub);
hub.port('grove-1').attach(await loadGroveModule('rtc', {cableLength:55}));
hub.port('grove-2').attach(await loadGroveModule('fingerprint2', {cableLength:65}));
hub.port('grove-3').attach(await loadGroveModule('audioplayer', {cableLength:75}));

host.get('grove/grove-2/ring-led').set({color:'#24c7a3', brightness:.65});
host.get('grove/grove-2/power-led').set({brightness:.3});
host.get('grove/grove-3/busy-led').set({on:true});
host.handle({type:'pose', target:'grove/grove-3/unitFrame',
  position:[20,90,6], rotation:[.1,-.2,.15]});
host.handle({type:'cable', target:'grove/grove-3/cable',
  slack:10, bend:[0,0,-1]});
hub.port('grove-1').detach(); // 保留指纹/音频分支及其外部灯光状态
host.dispose();
```

AudioPlayer 的 `audio` connector为 `audio-3.5mm-trs`，`sd` 为 `microsd`，均不接受Grove模块。本批补真实腔体、触点和卡座后板，不新增外卡或外接音频线，不虚构播放键、USB口或喇叭。模型不播放声音或访问文件系统。

RTC官方仅证实内置纽扣电池与封闭壳体。电池型号、座型和隐藏安装如无完整装配来源，按外观推导记录，不能据此判断可拆或制造配合。三款隐藏PCB布局、封装安装、光导/触点细节的依据与推导范围见各自research；新款印刷继续后置。

必要检查命令为 `node scripts/check-rtc-fingerprint-audio-units.mjs`，覆盖三分支实际产品、四芯线、独立灯光、插座类型、运行时边界、姿态与独立拆离。canvas和连接类型探针为Node替身，不代表浏览器像素、识别/播放或硬件验收。按用户要求不逐面浏览器复核，阶段保持 `modeled`。

# PoESP32 / CamS3-5MP / Synth

三款提供独立 `Model` 和含四芯线的 `GroveModule`，毫米坐标为+X右、+Y上、+Z正面。实体接口描述外观与配对坐标，网络、摄像、合成、音频、协议和电气均由外部框架负责。

| ID | 型号 / 实体 | 外部可控外观与接口 |
| --- | --- | --- |
| `poesp32` | U138；双板、ESP32/IP101G、PoE器件、HBJ-6308ANLF网口与八触点 | `link-led`固定黄、`activity-led`固定绿；`ethernet`类型`rj45-8p8c` |
| `cams3-5mp` | U174-B；固定焦距PY260 5MP、镜筒/玻璃/FPC、microSD与两组1×3母座 | `status-led`固定蓝；`sd`类型`microsd`，`download`/`expansion`类型`female-1x3-2.54mm` |
| `synth` | U178；SAM2695、NS4150B、PCB、内置8Ω1W喇叭与内部J2插座/引线 | `grove`为SYS_MIDI输入外观；`sensor`为纯视觉锚点 |

三款均无已证实的外露机械按键，不增加虚构button、调焦或运动关节。PoESP32无USB；CamS3-5MP不提供捕获/图像framebuffer；Synth无DIN、耳机或USB插座，内部喇叭接头不注册可挂接Port。灯只承接外部on/brightness，保持真实固定颜色，不自动联动网络、摄像或播放。

```js
import {loadModel, loadGroveModule} from 'm5stack-models.js/loaders';

const host = await loadModel('sticks3');
const hub = await loadGroveModule('hub', {cableLength:60});
host.port('grove').attach(hub);
hub.port('grove-1').attach(await loadGroveModule('poesp32', {cableLength:65}));
hub.port('grove-2').attach(await loadGroveModule('cams3-5mp', {cableLength:75}));
hub.port('grove-3').attach(await loadGroveModule('synth', {cableLength:85}));

host.get('grove/grove-1/link-led').set({brightness:.25});
host.get('grove/grove-1/activity-led').set({brightness:.6});
host.get('grove/grove-2/status-led').set({on:true});
host.handle({type:'pose', target:'grove/grove-3/unitFrame',
  position:[20,100,8], rotation:[.1,-.2,.15]});
host.handle({type:'cable', target:'grove/grove-3/cable',
  slack:12, bend:[0,0,-1]});
hub.port('grove-3').detach(); // 其他两分支与灯光状态保留
host.dispose();
```

Grove接线示例展示机械挂接和寻址，不证明HUB能转换UART/MIDI协议。RJ45、卡槽和下载插座拒绝Grove模块；本批不新增对应外线、卡片插拔、联网或发声行为。PCB、隐藏封装、安装深度和连接器内构仍含照片推导，见各产品research。

新增时同步贴纸：优先按用户表格里的精确同型号原稿或平面预览导出PNG；缺原稿处按已授权的同型号官方照片重绘并标来源。CSV、原稿、私有链接及转换材料只留仓库外，公开仅最终普通PNG与配准代码。`artwork:false`关闭贴纸；印刷依附真实壳体且不封堵接口或代替内部实体。

必要检查为 `node scripts/check-network-camera-synth-units.mjs`，覆盖真实三分支、四芯线、插座类型、独立固定色灯、运行时边界、姿态与拆离。只做新款局部smoke/API和构建，不逐面浏览器或全量复核，阶段保持 `modeled`。

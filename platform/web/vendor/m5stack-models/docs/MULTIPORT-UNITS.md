# PaHUB / PbHUB 多级接线

`pahub-v21` 对应 PaHUB v2.1 U040-B-V21，`pbhub-v11` 对应 PbHUB v1.1 U041-B。两者都可独立展示，也可作为 `GroveModule` 接到主机；各有上游输入 `grove` 和六个输出 `grove-0`…`grove-5`。输出编号按各自官方产品印字定位，具体实体坐标见产品目录。

```js
import {loadModel, loadGroveModule} from 'm5stack-models.js/loaders';

const host = await loadModel('sticks3');
const hub = await loadGroveModule('pahub-v21', {cableLength:80});
host.port('grove').attach(hub);

const key = await loadGroveModule('key', {cableLength:75});
const fan = await loadGroveModule('fan', {cableLength:110});
hub.port('grove-0').attach(key);
hub.port('grove-5').attach(fan);

// 线缆随Unit姿态更新；调用方按场景摆放各分支。
key.get('unitFrame').setPose({position:[-35,75,0]});
fan.get('unitFrame').setPose({position:[35,110,0]});
host.get('grove/grove-5/rotor').set({rpm:30});

// 只拆CH0；CH5的风扇和四芯线继续保留。
hub.port('grove-0').detach();
```

将ID换成 `pbhub-v11`，可视装配接口保持一致。PaHUB描述I2C分支，PbHUB描述其实际GPIO类扩展口；模型不实现通道选择、通信、电气兼容性、GPIO/ADC/PWM或供电。下游读取每个 `Port` 的元数据并实现对应功能。

PaHUB v2.1 另有 `dip-1`…`dip-3` 三枚稳定拨码。可用 `hub.button('dip-1').setPosition(1)` 同步某一档位，或用标准 `press()` / `release()` 产生切档意图；松开后保留档位。这里只移动真实拨码外形，不计算或设置I2C地址。

演示面板会自动列出六个输出口，排除已经被上游线占用的HUB输入口。继续挂接后的按键、关节、灯光及线缆控制沿完整路径出现，例如 `grove/grove-0/press`。本库不自动求解多线碰撞；调用方使用 `unitFrame` 和线缆姿态接口安排布线。

Gesture U127 使用ID `gesture`，有真实光学封装、窗口、PCB和Grove；`sensor`仅为视觉锚点，不接收或生成手势识别数据，也没有虚构机械按键。

来源、尺寸与推导项见各产品的 `docs/research/`。本批优先实体和连接接口，只执行有限结构/API检查，不作逐面浏览器或硬件验收。

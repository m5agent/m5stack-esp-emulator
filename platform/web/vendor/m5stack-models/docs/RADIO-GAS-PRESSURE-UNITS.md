# Tube Pressure / MQ / LoRaE220-920 接入

2026-10-26。本批新增U130、U199、U170。三款提供`Model`、`GroveModule`、`spec`、四芯`grove`及被动`sensor`；形状、可拆配件和输入意图属于模型，压力、气体、加热、无线、寄存器、固件和电气行为由外部框架实现。

| 型号 | 模型轴名义尺寸 mm | 真实机械接口与控件 |
| --- | --- | --- |
| `tube-pressure` U130 | 24×32×12.5 | 单一前向Ø3mm管嘴，`tube`类型`tube-3mm`；无灯/按钮/关节 |
| `mq` U199 | 24×64×25 | 圆脚MQ-5封装、实体金属网罩和固定六孔插座；`mq5`类型`mq5-six-pin`；无外露灯/按钮/关节 |
| `lora-e220-920` U170 | 24×71.4×8 | `sma`类型`sma-female`；`mode-0`/`mode-1`真实稳定DIP；随附胶棒天线有真实折叠铰链 |

尺寸采用+X右、+Y产品顶部、+Z正面；厂商顺序分别为32×24×12.5、64×24×25、71.4×24×8。U130原壳深8mm，气嘴伸出后12.5mm；LoRa原壳长64mm，71.4mm包含SMA，不包含110mm随附天线。MQ原壳、传感器安装及各配置的实际包络分别见本款`dimensions`、catalog和研究记录。保留完整原壳及真实开口，PCB、封装、管嘴内腔、插座与端口背衬都是独立物理几何。

## 三分支四芯连接

```js
import {loadModel, loadGroveModule} from '../src/loaders.js';

const host = await loadModel('sticks3');
const hub = await loadGroveModule('hub');
host.port('grove').attach(hub);
const pressure = await loadGroveModule('tube-pressure', {cableLength: 65});
const mq = await loadGroveModule('mq', {cableLength: 80});
const radio = await loadGroveModule('lora-e220-920', {
  cableLength: 95, antenna: true,
});
hub.port('grove-1').attach(pressure);
hub.port('grove-2').attach(mq);
hub.port('grove-3').attach(radio);

host.handle({type: 'pose', target: 'grove/grove-1/unitFrame',
  position: [0, 85, 8], rotation: [.1, -.2, .15]});
host.handle({type: 'cable', target: 'grove/grove-1/cable',
  slack: 12, bend: [0, 0, -1]});
```

每个分支渲染四芯线。`unitFrame`修改产品姿态，`cable`修改线缆形状；拆一支保持兄弟分支。`host.dispose()`释放装配树。`detach({dispose:false})`把保留的配件交还调用者，需重新装入或自行释放。

## Tube Pressure

前向`tube`只有机械管口和深腔，不接收Grove模块，也不实现导管、气体、压力、流速或传感器电压。MCP-H10-B200KPPN封装/感测背衬、PCB、HT7533、原生孔和黑色HY2.0-4P插座独立存在。只有背面1张有实物依据的印刷PNG；气嘴面没有额外贴纸，原壳背面的M5凹雕保留原CAD。

## MQ与可拆感测封装

MQ默认安装本款MQ-5，`mq5Cartridge:false`只拆下圆脚传感器；固定圆形六孔座、内部适配板和主板仍在。厂家图64mm端点不含外突圆罐；完整装配与拆去传感器的包络另按实际几何记录，不把名义壳尺寸写成装上圆罐后的总长。产品入口导出`MQ5Cartridge`，总入口别名为`Mq5Cartridge`。

```js
const cartridge = mq.port('mq5').detach({dispose: false});
mq.port('mq5').attach(cartridge);
```

`mq5`机械类型为`mq5-six-pin`，只约束附件配对；不生成加热、气敏电阻、ADC、报警或温度状态。网罩使用实际金属几何，内部感测封装和六针独立建模。D1虽在原理图中为绿色0603器件，但本款未确证外露光路，因此只保留隐藏封装，不注册可见LED能力。没有虚构可拆内部适配板或其他MQ型号。

## LoRa的DIP与折叠天线

严格使用U170的E220-900T22S/920版，不套433版或LoRaWAN。`mode-0`和`mode-1`是两枚真实稳定滑块：0/1为物理档位，`press`切换、`release`结束按压后保留档位；取消输入发送取消的`up`，不发送`click`。外部设置档位不回送输入：

```js
host.handle({type: 'button', target: 'grove/grove-3/mode-0',
  action: 'position', position: 1});
host.on('input', event => externalFramework.receive(event));
// 指针/键盘输入由Viewer转为事件；外部输入也可用press/release/cancel。
```

档位不改变串口、M0/M1网络或无线工作模式，模型不执行发射/接收、RF场、频段、功率或距离行为。每帧调用`host.update(dt)`推进形状插值。

默认`antenna:false`显示本体；`antenna:true`装入随附110mm天线，可用`antennaAngleDeg`指定初始折叠角。产品入口导出`Antenna`，总入口为`LoraE220920Antenna`。实际公针在元数据中标为`physicalConnector:'sma-male'`，`meta.connector:'sma-female'`表示它能接入的主端口类型，符合当前`Port.accepts`精确匹配约定，不需要修改共享核心。

```js
host.handle({type: 'joint', target: 'grove/grove-3/sma/tilt',
  angleDeg: 90, durationMs: 180});
const antenna = radio.port('sma').detach({dispose: false});
radio.port('sma').attach(antenna);
```

`tilt`以度为单位，0…90只表达官图中直线/折叠形状的外观范围，非零RPM和越界角度抛错；不自动扫动、不表示制造限位或铰链扭矩。SMA及Grove固定帧不随折叠改变。天线外形分段、铰链位置、隐藏同轴与安装间隙有照片推导，来源明确保留，未声称制造配合。配置菜单提供带天线/裸本体和MQ正常安装/拆去感测封装的查看入口。

## 贴纸、来源与必要验证

本批同步8张PNG：Tube Pressure背贴1张；MQ4张（精确背稿`source-vector-raster`1张，标题、空白识别贴、MQ-5银圈标记参考重绘3张）；LoRa正背与固定DIP ON/1/2标记共3张参考重绘。共7张`reference-redraw`均按各自同型号官图代码绘制。原稿恢复范围、可辨文字和配准见各款`docs/research/<id>/artwork`。不裁产品照片当贴纸，不用贴纸遮盖缺件，不把参考重绘称为原稿。

私表、私有下载链接、原稿名、矢量、原始官方图/CAD、生成器与中间材料留在仓库外。公开仅普通最终PNG、衍生几何和自写来源说明。每个模型/模块分别传`artwork:false`关闭印刷层，保留各配置的所有物理attributes/index及世界姿态，包含可拆传感器和天线。

运行`node scripts/check-radio-gas-pressure-units.mjs`执行真实StickS3→HUB三分支四芯、管嘴类型、MQ5插拔、两DIP输入/外驱档位、天线折叠/插拔、被动边界与配置贴图开关检查。单品smoke及冻结来源见各款研究目录；两构建、在线资源字节和隐私结果以[本批进度](../artifacts/radio-gas-pressure-expansion/progress.json)为准。

总入口新增`TubePressureUnit`/`TubePressureUnitModule`、`MqUnit`/`MqUnitModule`、`LoraE220920Unit`/`LoraE220920UnitModule`及上述两附件。保持`modeled`，未执行逐面浏览器、全量历史或实物验收。公开main的85款`ad5d062`仍为上次Git同步快照，后续本地增量未自动再次推送。

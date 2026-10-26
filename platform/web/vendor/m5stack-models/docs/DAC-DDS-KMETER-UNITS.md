# DAC2 / DDS / KMeter-ISO v1.1

本批提供独立 `Model` 和含两只插头、四根实体导线的 `GroveModule`。单位为毫米，+X 右、+Y 上、+Z 正面。完整原壳、PCB、接口内构和真实安装孔分别保留；电压、信号波形、采样、温度、协议与电气由外部框架实现。

| ID / SKU | 外观实体和组件 |
| --- | --- |
| `dac2` / U012-B | GP8413与实际PCB、固定4P输出座/触点、可选安装包装内HT3.96-4P螺钉插头；`grove`、`terminal`、被动 `sensor` |
| `dds` / U105 | AD9833、STM32F0、时钟器件与完整SMA外螺纹/绝缘芯/母触点/内部座；`grove`、`sma`、被动 `sensor` |
| `kmeter-iso-v11` / U133-V11 | 本款前后壳、STM32/MAX31855K/CA-IS3641HW、实际K型扁插座/内触点；`grove`、`thermocouple`、被动 `sensor` |

名义模型轴尺寸与厂商顺序分别记录在 `spec.nominalMm` / `vendorDimensionOrderMm`，原CAD和含贴层的可视包络另记；不缩放原壳强行匹配另一口径。DDS原壳本体与SMA外伸的产品总长分别保存。隐藏安装、封装、接触深度与外观推导见 [DAC2](research/dac2/modeling.md)、[DDS](research/dds/modeling.md)、[KMeter](research/kmeter-iso-v11/modeling.md)。

## DAC2 可拆端子与四个真实螺钉

```js
import {loadModel, loadGroveModule} from 'm5stack-models.js/loaders';

const dac = await loadModel('dac2', {terminalPlug:true});
const plug = dac.port('terminal').module;
plug.get('screw-1').set({angleDeg:45});
plug.get('screw-2').set({angleDeg:90, durationMs:160});
dac.update(.16);

const saved = dac.port('terminal').detach({dispose:false});
dac.port('terminal').attach(saved);
```

默认保留空固定座，`terminalPlug:true` 安装包装内的4P插头，demo提供空座/安装插头配置。产品入口导出 `TerminalPlug`，全局别名 `Dac2TerminalPlug`；手动新建该模块后可挂到 `terminal`。四个 `screw-1`…`screw-4` 只驱动真实螺钉头的视觉角度，固定座、PCB、Grove和其他螺钉保持。螺钉角度不模拟升降、夹紧力、接触或输出电压；拆掉插头保留整机和Grove四芯线。

原资料的A0/A1/A2地址配置不转成虚构的外露DIP开关。DAC2没有额外可见LED或按钮；`sensor` 不接受voltage/current/DAC值命令，也不做短路保护或电压转换。

## SMA 与 K型扁插座

| 端口 | 机械配对类型 | 范围 |
| --- | --- | --- |
| DDS `sma` | `sma-female` | 固定SMA母口，有螺纹外观、绝缘芯、空心中心触点及后部深度；不生成信号或波形 |
| KMeter `thermocouple` | `thermocouple-k-mini-flat` | 本款实际K型扁插槽与金属触点；没有自动接收温度/热电偶状态 |

以上两个接口都拒绝Grove模块，类型仅约束几何配对，不证明实物电平、接线或电气兼容。接口槽是实际开口，后方保留插座深度与触点，不使用贴图覆盖空洞。

DDS没有虚构的旋钮、LED或屏幕，顶部金色露窗属于SMA金属件。模型不实现AD9833的频率、相位、波形、时钟、休眠或寄存器。

KMeter严格使用U133-V11原壳和对应印刷，不套旧版。原理图LED1保留隐藏红色封装；没有确证外露光路，因此不注册猜测灯控。包装的1m热电偶探头未建成猜测尺寸的模块，当前默认插座空置，外部框架可按真实配对类型接入自有几何；没有温度、补偿、开短路或隔离电气模型。

## Grove 多分支与外驱寻址

```js
const host = await loadModel('sticks3');
const hub = await loadGroveModule('hub', {cableLength:60});
host.port('grove').attach(hub);
hub.port('grove-1').attach(await loadGroveModule('dac2', {
  cableLength:65, terminalPlug:true,
}));
hub.port('grove-2').attach(await loadGroveModule('dds', {cableLength:80}));
hub.port('grove-3').attach(await loadGroveModule('kmeter-iso-v11', {cableLength:95}));

host.get('grove/grove-1/terminal/screw-1').set({angleDeg:35});
host.handle({type:'pose', target:'grove/grove-3/unitFrame',
  position:[35,120,8], rotation:[.1,-.2,.15]});
host.handle({type:'cable', target:'grove/grove-3/cable', slack:12, bend:[0,0,-1]});
host.update(.2);

const saved = hub.port('grove-2').detach({dispose:false});
hub.port('grove-2').attach(saved);
host.dispose();
```

示例只证明机械挂接、四芯线姿态和层级地址，不执行HUB路由、供电、I2C或器件协议。外驱螺钉和姿态不回送用户输入意图；真实插拔会发出相应端口输入事件。

## 同批印刷与检查范围

DAC2优先使用精确机身原稿；源复合轮廓填充规则恢复按实际处理记录为 `source-vector-raster`，字形和图案来自原稿，不宣称字节不变的直接导出。DDS缺原稿，按同型号官方照片代码重绘高清PNG并标 `reference-redraw`。KMeter使用对应v1.1的两面原稿；正面导出时透明度为0的异常按对应预览恢复半透明圆环，并明确标为原稿恢复，插座的可辨标记另按本款官图重绘。本批共7张PNG（DAC2两张、DDS两张、KMeter三张）。实际像素、来源、配准和恢复边界见各款 `artwork.json`，不裁产品照片、不补造不可辨字。

```js
const bare = await loadModel('dac2', {terminalPlug:true, artwork:false});
const wiredBare = await loadGroveModule('kmeter-iso-v11', {artwork:false});
```

每个模型/模块分别传 `artwork:false`，主机选项不自动传播。关闭印刷保留原壳、孔、PCB、SMA、K插座和端子/螺钉实体。私有CSV、下载URL、原稿名、矢量、映射、生成器和中间素材始终留在仓库外；公开只普通PNG、配准与来源说明，印刷/商标保留权利。

必要专项为 `node scripts/check-dac-dds-kmeter-units.mjs`，单品结构/API记录在 `docs/research/<id>/smoke.json`。范围包含实际三分支四芯线、可拆端子/四螺钉、SMA/K口类型、被动锚点、贴纸关闭的实体不变和独立拆离。Node图形边界替身不提供浏览器像素证据；没有逐面浏览器、全量历史、实物、电气、信号或温度验收，阶段保持 `modeled`。

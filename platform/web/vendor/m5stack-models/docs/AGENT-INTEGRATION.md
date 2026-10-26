# 动态外壳接入：给下游 Agent

2026-10-26端子修订：AC Measure/AIN4-20mA/BLDC Driver只补齐插舌四孔下壁，`terminal/screw-1…4`、装拆和所有端口/输入接口保持。当前SHA及局部验证见[闭合修复](TERMINAL-TONGUE-CLOSURE.md)；旧freeze/smoke是历史快照，不能代替当前修订来源。

本地最新新增 `unit-id`（U124）、`rf433r`（U113）、`rf433t`（U114），同步6张本款官图代码重绘 `reference-redraw` PNG，每款正背各1张；没有照片裁切、借用相近型号或不可辨小字编造。当前本地127款（14主机、113Unit），全部 `modeled`、`verified` 为0。本次127款源码同步包含112款基线 `32c95e0` 后新增的15款Unit/28张对应PNG及三旧端子闭合修复，范围见[127款同步记录](GIT-SYNC-127-2026-10-26.md)。历史progress中的未提交/未推送字样仅描述其保存时点，远端状态以GitHub main及实际推送回执为准。完整API、来源和三分支四芯例见[ID/RF433R/RF433T](ID-RF433-UNITS.md)，30批记录见[本地增量索引](LOCAL-EXPANSION.md)。

三款分别保留本款原壳、真实芯片封装/引脚、PCB、Grove深腔/四触点和独立胶贴基底。ID为本款ATECC608B-TNGTLSU-G器件外观；RF433R与RF433T分别采用真实接收/发射器及晶体/外围，内置PCB天线固定、不发光，没有外接SMA、胶棒或弹簧天线，不挖假观察窗或造关节。共用壳只在本款自有CAD来源核对后保留，不套用另一型号的芯片或印刷。隐藏板位/铜天线布局/安装、字体颜色与印刷配准仍标明推导，不宣称生产配合。

三款本体组件均只有 `grove`，没有 `sensor` / `button` / `joint` / `led` / display；均导出 `Model` / `GroveModule` / `spec`。总入口六个别名为 `IdUnit` / `IdUnitModule`、`Rf433rUnit` / `Rf433rUnitModule`、`Rf433tUnit` / `Rf433tUnitModule`；loader ID为三款slug。`unitFrame` / `cable`沿现有Grove接口外驱姿态和四芯线形，嵌套路径以前级实际Port ID作前缀，外驱不回送输入意图。外形只呈现真实连接和固定器件；没有身份值、数据帧、RF动画、读写/识别或收发功能。

`artwork:false`保留两入口全部物理attributes/index与最顶层更新后的 `matrixWorld`，含独立胶贴基底；印刷不代替PCB、器件、原壳或插座。身份/密钥/证书/加密/I2C、RF/ASK/数据/强度/距离/通信、GPIO、供电/电气、物理和固件由外部框架实现。必要专项 `node scripts/check-id-rf433-units.mjs`，综合范围以[本批进度](../artifacts/id-rf433-expansion/progress.json)为准；没有新增逐面浏览器、全量历史或实物验收。私表、私有链接/原稿名、矢量、官图CAD原件、生成器和中间件留仓库外，仅公开最终普通PNG及安全配准/来源。

## 此前：Accel / OP90 / OP180

前批新增 `accel`（U056）、`op90`（U057）、`op180`（U058），同步4张本款官图代码重绘 `reference-redraw` PNG：Accel正背2张，OP90/OP180各背贴1张；没有照片裁切、借用相近型号或不可辨小字编造。该批完成时本地124款（14主机、110Unit），全部 `modeled`、`verified` 为0。公开仓库112款提交基线为 `32c95e0`，该批保存时其后共12款及三旧端子局部修复为本地增量；当前未推送范围以本文最新批次记录为准；Git同步范围见[112款同步记录](GIT-SYNC-112-2026-10-26.md)。完整API、来源和三分支四芯例见[Accel/OP90/OP180](ACCEL-OP90-OP180-UNITS.md)，29批记录见[本地增量索引](LOCAL-EXPANSION.md)。

三款分别保留本款原壳、真实传感封装、PCB与器件、Grove插座和独立胶贴基底。OP90/OP180保留实际固定安装方向、槽型遮光壳、收发窗口、引脚与有意开放的检测空气隙；`90` / `180`是产品结构方向，不是可动角，不能为闭合填平真槽或造铰链。IR发射器不画可见灯、光束或检测锥。Accel没有真实可动机构，不以倾斜动画模拟内部加速度或数据；隐藏安装、内腔、图形字体/颜色和配准推导见单品研究。

三款本体组件均只有 `grove`和被动 `sensor`，没有 `button` / `joint` / `led` / display；均导出 `Model` / `GroveModule` / `spec`。总入口六个别名为 `AccelUnit` / `AccelUnitModule`、`Op90Unit` / `Op90UnitModule`、`Op180Unit` / `Op180UnitModule`；loader ID为三款slug。`unitFrame` / `cable`沿现有Grove接口外驱姿态和四芯线形，嵌套路径以前级实际Port ID作前缀，外驱不回送输入意图。`sensor`只定位真实器件外观，不能写入数值、检测、计数或内部状态。

`artwork:false`保留两入口全部物理attributes/index与最顶层更新后的 `matrixWorld`，含独立胶贴基底；印刷不代替PCB、光电封装、空气槽或插座。加速度/姿态数据、遮挡/检测/计数/电平、IR光学、I2C/GPIO、供电/电气、物理和固件由外部框架实现。必要专项 `node scripts/check-accel-opto-units.mjs`，综合范围以[本批进度](../artifacts/accel-op90-op180-expansion/progress.json)为准；没有新增逐面浏览器、全量历史或实物验收。私表、私有链接/原稿名、矢量、官图CAD原件、生成器和中间件留仓库外，仅公开最终普通PNG及安全配准/来源。

## 此前：Mini PDM / Mini BPS v1.1 / MIC

前批新增 `mini-pdm`（U089）、`mini-bps-v11`（U090-B）、`mic`（U096），同步5张本款官图代码重绘 `reference-redraw` PNG：前两款各正背2张，MIC背贴1张；没有照片裁切或不可辨小字编造。三款均导出 `Model` / `GroveModule` / `spec`，保留真实四芯 `grove` 和被动 `sensor`；MIC另有实际调节头的有限角关节。该批完成时本地121款（14主机、107Unit），全部 `modeled`、`verified` 为0。公开仓库112款提交基线为 `32c95e0`，该批保存时其后共9款为本地增量；当前未推送范围以本文最新批次记录为准；Git同步范围见[112款同步记录](GIT-SYNC-112-2026-10-26.md)。完整API、来源和三分支四芯例见[Mini PDM/Mini BPS v1.1/MIC](AUDIO-PRESSURE-UNITS.md)，28批记录见[本地增量索引](LOCAL-EXPANSION.md)。

Mini PDM保留本款SPM1423HM4H-B金属MEMS封装、真实声孔/深腔、PCB、HT7333及Grove。官方表为24×24×13mm，自身尺寸图与完整4162三角原壳为24×24×8mm，两者分别记录，不缩放原壳；反馈 `dcd6f74080ea478f8745ce19d5542ab8` 已保存。Mini BPS严格U090-B QMP6988 v1.1，保留4162三角原壳24×24×8mm、LGA9金属封装、Ø0.20mm真气孔/深腔、PCB、HT7533及BSS138；不混EOL U090 BMP280或其13mm几何/贴纸。两款前部双槽都有真实封装或PCB背衬，胶贴基底独立；安装/内腔、隐藏器件与印刷配准仍标明推导。

MIC保留本款电容麦克风金属筒、真实穿孔网/内凹振膜、蓝色10K阈值电位器、MAX4466/LM393/HT7533与Grove。`threshold`仅外驱可见调节头的 `angleDeg` / `durationMs`，非零RPM被拒绝；当前−135～135°是保守外观范围，机械止点和电气零点未确认。蓝色固定座、刻线、PCB与麦克风不随头旋转，不产生电阻、增益、ADC、Din/阈值或声音事件。三款均没有灯、按钮或显示屏；被动 `sensor`没有内部数值命令。

总入口六个别名为 `MiniPdmUnit` / `MiniPdmUnitModule`、`MiniBpsV11Unit` / `MiniBpsV11UnitModule`、`MicUnit` / `MicUnitModule`；loader ID为三款slug。`unitFrame` / `cable`沿现有Grove接口外驱姿态和四芯线形，嵌套路径以前级实际Port ID作前缀，外驱不回送输入意图。三款的麦克风声学/音频/录音、PDM时钟/数据、气压/温度/海拔、I2C/ADC/GPIO、电气和固件由其他框架实现。

`artwork:false`保留两入口全部物理attributes/index与最顶层更新后的 `matrixWorld`，含独立胶贴基底；印刷不代替真实PCB、器件、孔网或插座。必要专项 `node scripts/check-audio-pressure-units.mjs`，综合范围以[本批进度](../artifacts/audio-pressure-expansion/progress.json)为准；没有新增逐面浏览器、全量历史或实物验收。私表、私有链接/原稿名、矢量、官图CAD原件、生成器和中间件留仓库外，仅公开最终普通PNG及安全配准/来源。

## 此前：Roller485 Lite / Mini CAN / INA226-10A

前批新增 `roller485-lite`（U182-Lite）、`mini-can`（U179）、`ina226-10a`（U200），同步7张PNG：Roller485 Lite三张、Mini CAN正背两张为同款官图代码重绘 `reference-redraw`，INA226-10A精确10A机身正背两张为原稿恢复栅格 `source-vector-raster`。三款均导出 `Model` / `GroveModule` / `TerminalPlug` / `spec`，保留真实四芯 `grove`。该批完成时本地118款（14主机、104Unit），全部 `modeled`、`verified` 为0。公开仓库112款提交基线为 `32c95e0`，该批保存时其后共6款为本地增量；当前未推送范围以本文最新批次记录为准；Git同步范围见[112款同步记录](GIT-SYNC-112-2026-10-26.md)。完整API、来源和三分支四芯例见[Roller485 Lite/Mini CAN/INA226-10A](ROLLER-MINI-CAN-INA226-UNITS.md)，27批记录见[本地增量索引](LOCAL-EXPANSION.md)。

Roller485 Lite保留本款3504电机/转子、固定壳体、PCB、白色单色64×48 OLED、两颗独立RGB、Grove、PWR485与debug实体。`rotor`接受外驱角度/时长或连续视觉RPM，`press`压放实际壳舌并回弹，`lcd`仅接外部framebuffer，`rgb-1` / `rgb-2`默认off独立外驱。它只有单PWR485端子，不套其他Roller型号的顶部扩展口或滑环输出；没有 `sensor` 或 `grove-top`，不生成FOC、编码器数值、扭矩、负载、电流/速度环或电机物理。

Mini CAN为本款非隔离TJA1051T/3 SO8、ME3116/MST5333与3012电感实体，完整3286三角原壳8mm保留，含固定端子的裸机为24×32×10.2mm。不套Unit CAN U085隔离模块或MCU。INA226为U20010A/5mΩ版本，保留MSOP10、隔离SOIC8封装、16脚B0505ST16-W5、保险丝/分流器；不是1A版本。其官方58mm名义与56mm原壳分别记录，固定座安装外伸为已标明推导，官方尺寸图适用范围反馈见单品来源。两款本体只有 `grove` / `terminal`，隐藏LED无确认外露光路，不造灯窗、数值锚点或按钮。

三款均有可拆四螺钉 `TerminalPlug`，可用 `terminalPlug:true`安装或通过真实固定Port单独装拆。Roller使用 `pwr485/screw-1`…`screw-4`，Mini CAN/INA使用 `terminal/screw-1`…`screw-4`；四头仅接受 `angleDeg` / `durationMs`并可精确回位，拒非零RPM，不模拟螺纹轴向、夹紧或电气连接。总入口九个别名为 `Roller485LiteUnit` / `Roller485LiteUnitModule` / `Roller485LiteTerminalPlug`、`MiniCanUnit` / `MiniCanUnitModule` / `MiniCanTerminalPlug`、`Ina22610aUnit` / `Ina22610aUnitModule` / `Ina22610aTerminalPlug`；loader ID为三款slug。

`unitFrame` / `cable`沿现有Grove接口外驱姿态和四芯线形，嵌套路径以前级实际Port ID作前缀，外驱不回送输入意图。`artwork:false`保留各配置全部物理attributes/index与最顶层更新后的 `matrixWorld`，印刷不替代PCB、端子、触点或胶贴基底。电机控制/反馈、串口/CAN/I2C、电流电压功率、电气保护、供电与固件由其他框架实现。必要专项 `node scripts/check-roller-mini-can-ina226-units.mjs`，综合范围以[本批进度](../artifacts/roller-mini-can-ina226-expansion/progress.json)为准；没有新增逐面浏览器、全量历史或实物验收。私表、私有链接/原稿名、矢量、官图CAD原件、生成器和中间件留仓库外，仅公开最终普通PNG及安全配准/来源。

## 此前：UWB / TMOS PIR / Mini ToF-90

前批新增 `uwb`（U100）、`tmos-pir`（U185）、`mini-tof-90`（U196），同步6张PNG：UWB标准机身正背2张 `source-vector-raster`，另两款各2张本款官图代码重绘 `reference-redraw`。三款均导出 `Model` / `GroveModule` / `spec`，保留真实四芯 `grove`。该批完成时本地115款（14主机、101Unit），全部 `modeled`、`verified` 为0。公开仓库112款提交基线为 `32c95e0`，该批保存时新增三款为本地增量；当前未推送范围以本文顶部记录为准；Git同步范围见[112款同步记录](GIT-SYNC-112-2026-10-26.md)。完整API、来源与三分支四芯例见[UWB/TMOS PIR/Mini ToF-90](RANGING-PRESENCE-UNITS.md)，26批记录见[本地增量索引](LOCAL-EXPANSION.md)。

UWB为本款Ai-Thinker BU01/DW1000及STM32F103C8T6实体，完整3796三角原壳、黑色PCB、内置固定平面铜天线、晶振/稳压器和蓝色Grove均保留。只有 `grove`，无sensor/button/LED/joint，不套外置SMA或胶棒天线。标准机身原稿恢复保留原色与轮廓，仅修正转换的 `evenodd`→`nonzero`复合字腔；包装、照片及跨SKU同名候选排除，原稿/映射仅留仓库外。

TMOS PIR为本款STHS34PF80金属封装与凹入硅滤光窗、PCB背衬，只有被动 `sensor` 外观锚点及 `grove`。不套旧PIR半球菲涅耳，不画可见红外/检测锥，不提供人体存在、温度、运动或数值状态。官方规格表5.2mm与本款尺寸图/完整STL的8mm厚度冲突，保留24×32×8原始实体并已反馈，见单品来源。

Mini ToF-90保留固定90°两块PCB、板间四针、VL53L0X分离收发窗和深腔实体，光学方向固定+Y，不造铰链或外驱转动。`sensor`仅被动外观锚点；`power-led`为独立固定红色D1外驱明暗，默认off，无光晕。原生Grove侧嵌件的导光材料与耦合属于已标明的外观推导，灯不随连接/供电/距离自动联动，IR窗保持不发可见光。

总入口别名 `UwbUnit` / `UwbUnitModule`、`TmosPirUnit` / `TmosPirUnitModule`、`MiniTof90Unit` / `MiniTof90UnitModule`，loader ID为三款slug。`unitFrame` / `cable`沿现有Grove接口接受外驱姿态/线形；嵌套时以前级实际port ID作路径前缀，外驱不回送输入。`artwork:false`保留本款全部物理attributes/index及最顶层更新后的世界矩阵；印刷不代替PCB、光窗、胶贴基底或插口背衬。RF/AT/定位/测距、人体存在/温度、I2C、电气与固件由其他框架实现。必要专项 `node scripts/check-ranging-presence-units.mjs`，综合范围以[本批进度](../artifacts/ranging-presence-expansion/progress.json)为准，没有新增逐面浏览器、全量历史或实物验收。私表、私有链接/原稿名、矢量、官图CAD原件、生成器和中间件留仓库外，仅公开最终普通PNG及安全配准/来源。

## 此前：RS485-ISO / AIN4-20mA / AC Measure

前批新增 `rs485-iso`（U094）、`ain4-20ma`（U162）、`ac-measure`（U164），同步6张PNG：前两款各2张 `reference-redraw`，AC Measure正背2张 `source-vector-raster`。三款均导出 `Model` / `GroveModule` / `TerminalPlug` / `spec`，提供真实四芯 `grove` 与本款固定端子。该批完成时本地112款（14主机、98Unit），全部 `modeled`、`verified` 为0；该批保存时公开Git为85款 `ad5d062`，当时随后二十七款尚未推送；当前同步以本文顶部记录为准。完整API、配置、来源和三分支四芯例见[RS485-ISO/AIN4-20mA/AC Measure](ISOLATED-INTERFACE-UNITS.md)。

RS485-ISO严格本款U094隔离本体，`terminal` 为 `vh3.96-4p`；`terminalPlug:true`装随附四螺钉插头。`terminator:true`须同时装插头，120Ω电阻及引线位于同一插头B/A入口并随其拆装，不增加假插口。`power-led`默认off，只接受独立外驱开关/亮度；固定白色是预览估计，`meta.colorConfirmed:false`，不是官方确认灯色或RGB规格，不随UART/端子/电源联动。

AIN4-20mA是单通道U162，保留STM32G030/HCNR200/SGM321、真实六针P2/P3及五个可拆帽位；`terminal` 为 `ht3.96-4p`。`jumpers`接受默认 `'three-horizontal'`、`'two-vertical'` 或 `false`；每个 `Shunt`独立装拆，五口为 `pin-header-2.54-2p`，`port.meta.physicalPins` / `port.physicalPins`记录占针，冲突在修改附件前拒绝。只防止两帽占同一实体针，不执行供电选择。帽位经真实开口外露，`covers:false`只作开盖检查；无sensor/LED/button/本体joint。

AC Measure U164保留本款STM32G030/HLW8032/B0505ST16-W5/EL357、PCB与 `ht3.96-4p`固定座，前视L2/N2/L1/N1只记录实体标记，不是接线建议。无sensor/LED/button/本体joint。AC正背原稿恢复保留原色，仅修正转换造成的 `evenodd`→`nonzero`字腔填充，标 `source-vector-raster`，包装贴纸排除；另两款按自身官图代码重绘，不裁照片、不编不可辨字、不借贴纸遮缺件。

三款插头均有 `terminal/screw-1`…`screw-4`，只外驱可见头角 `angleDeg` / `durationMs`、拒非零RPM，不代表轴向压线/扭矩/电气。总入口别名 `Rs485IsoUnit` / `Rs485IsoUnitModule` / `Rs485IsoTerminalPlug`、`Ain420maUnit` / `Ain420maUnitModule` / `Ain420maTerminalPlug` / `Ain420maShunt`、`AcMeasureUnit` / `AcMeasureUnitModule` / `AcMeasureTerminalPlug`；loader ID为三款slug。实例 `artwork:false`保留对应盖/插头/电阻/跳帽配置的全部物理attributes/index和世界矩阵。内部UART/RS485、供电、ADC、数值、隔离、协议及电气由外部框架实现。必要专项 `node scripts/check-isolated-interface-units.mjs`；综合范围以[本批进度](../artifacts/isolated-interface-expansion/progress.json)为准，不新增逐面浏览器、全量历史或实物验收结论。私表、私有链接/原稿名、矢量、官图CAD原件、生成器与中间件只留仓库外，公开最终普通PNG及安全来源说明。

## 此前：BLDC Driver / RCA / Puzzle

前批新增 `bldc-driver`（U181）、`rca`（U155）、`puzzle`（U193），同步6张本款官图代码重绘 `reference-redraw` PNG。三款均导出 `Model` / `GroveModule` / `spec`，提供实际四芯 `grove`；均为输出/连接装配，没有虚构的 `sensor`。该批完成时本地109款（14主机、95Unit），全部 `modeled`、`verified` 为0；公开Git仍85款 `ad5d062`，随后二十四款本地增量未自动再次推送。完整API、配置、来源与三分支/级联例见[BLDC Driver/RCA/Puzzle](BLDC-RCA-PUZZLE-UNITS.md)。

BLDC Driver严格本款STM32G030/DRV11873与U/V/W/COM固定4P座；`terminal` 为 `ht3.96-4p`，默认裸座，`terminalPlug:true` 装随附 `TerminalPlug`。附件有四个 `screw-1`…`screw-4`，仅外驱头角/时长、拒非零RPM。无随附电机/转子/按钮/旋钮，隐藏SYS_LED无确证光路则不注册穿壳灯。固定座、PCB/封装、Grove和真实背衬齐备，不执行PWM、转速、方向、保护或电气。

RCA保留真实单母插孔的金属筒/绝缘环/中心触点/开放腔，`rca` Port拒Grove；没有随附RCA插头/线。`channel` 是壳内单枚SW-SPDT双通道稳定滑钮，默认闭壳禁pointer，`covers:false`开盖才可看/操作，贴层随真实盖隐藏，固定I1/I2不随滑块移动。0/1只表示外观档位，外驱不回声，取消不click，不切换音视频或模拟电路。壳24×32×8与含座24×36.4×14.7分记，官网表8mm不能替代总厚尺寸图；无LED/joint/sensor。

Puzzle为24×24×15的真实64颗WS2812E-1313和原生8×8隔光栅格。`pixel-0`…`pixel-63` 是正视行优先外观布局索引，不宣称厂家串行线序；默认全off，可逐灯外驱。`matrix` 接 `{type:'matrix',colors:[64色],brightness:0…1}` 或 `{type:'matrix',rgba:[256字节],brightness:0…1}`，alpha仅乘外观亮度，整帧先验证后更新。主输入 `grove` 对应J2，输出 `out` 对应J1，可接第二真实GroveModule，继续渲染四芯线与下级形状；上游帧不自动转发下游像素/电源/协议。不造MCU、按键、显示屏、自动动画或电气行为。随附桥接件独立导出 `Bridge` / 总入口 `PuzzleBridge`，仅外形/实体PCB插座/背标，无装配Port或命令，刚性成品配合缺基准，不能视为已核准装配。

总入口模型别名 `BldcDriverUnit` / `BldcDriverUnitModule` / `BldcDriverTerminalPlug`、`RcaUnit` / `RcaUnitModule`、`PuzzleUnit` / `PuzzleUnitModule` / `PuzzleBridge`；按需loader ID为三款slug。各实例 `artwork:false` 保持当前插头/闭壳/开盖配置的全部物理attributes/index和世界矩阵。三款私表无精确原稿，重绘不裁照片/不编不可读小字/不遮缺件；私表、私有链接/原稿名、矢量、官图CAD原件、生成器和中间件只在仓库外。必要专项 `node scripts/check-bldc-rca-puzzle-units.mjs`，综合范围见[本批进度](../artifacts/bldc-rca-puzzle-expansion/progress.json)，不增加逐面浏览器、全量历史或实物验收结论。

## 此前：Thermal2 / FlashLight / GPS SMA

前批新增 `thermal2`（U149）、`flashlight`（U152）、`gps-sma`（U190），同步7张本款官图代码重绘 `reference-redraw` PNG。三款均导出 `Model` / `GroveModule` / `spec`，提供真实四芯 `grove`；Thermal2/GPS SMA另有被动 `sensor`，FlashLight仅实际 `mode` / `light` 输出组件，没有传感器锚点。该批完成时本地106款（14主机、92Unit），全部 `modeled`、`verified` 为0；公开Git仍85款 `ad5d062`，后续二十一款本地增量未自动再次推送。完整API、配置、来源和三分支四芯例见[Thermal2/FlashLight/GPS SMA](THERMAL2-FLASHLIGHT-GPS-UNITS.md)。

Thermal2严格使用本款黑色下凹MLX90640采集头、ESP32-PICO-D4、实际PCB/蜂鸣器和两原壳舌，`button` / `reset` 压放/取消后原顶点精确回位；`rgb` 只独立外驱。没有显示、内生热成像、测温、报警、声音或MCU复位逻辑。相同外壳来源不表示可套NCIR2器件/贴纸。

FlashLight的 `light` 是固定白光外驱灯，接受 `on` / `brightness`，拒绝重设RGB颜色；内部 `mode` 是两档稳定Button，默认闭壳不接pointer，`covers:false`开盖配置才可看/操作，仍保留真实壳数据与固定PCB丝印。`setPosition(0|1)` 或 `type:'button',action:'position'`只改变实体档位且不回送输入，不生成Flash/Torch脉冲、功率、电气或热行为。正文/原理图/背贴5000…5700K与规格表6000…6500K存在冲突，固定预览色不是校准色温，详见单品来源/反馈。

GPS SMA的 `sma` 接真实可拆 `Antenna`，默认 `antenna:false`，`antenna:true`装入完整有源带线puck；不是LoRa胶棒，不造铰链。`sma/shape` 接毫米局部中心线points，更新同轴与末端puck，保持固定SMA/Grove和本体；点集限制/名义1m与当前曲线长见专门指南和组件状态。壳24×64×8与含SMA24×71.4×8分别记录。蓝1PPS未证实外露光路，不注册外露LED，不生成GNSS/RF/定位/NMEA或线缆物理行为。

总入口别名 `Thermal2Unit` / `Thermal2UnitModule`、`FlashlightUnit` / `FlashlightUnitModule`、`GpsSmaUnit` / `GpsSmaUnitModule` / `GpsSmaAntenna`；按需loader ID为三款slug。各模型/模块分别传 `artwork:false`，保留对应闭壳/开盖/天线配置的全部物理attributes/index和世界矩阵。本批私表无精确原稿，重绘不是照片裁片，字体/颜色/注册与不可辨小字限制按单品来源保留。私表、私有链接/原稿名、矢量、官图/CAD原件、生成器和中间件仅留仓库外。必要专项 `node scripts/check-thermal2-flashlight-gps-units.mjs`，综合结果见[本批进度](../artifacts/thermal2-flashlight-gps-expansion/progress.json)，不增加逐面浏览器、全量历史或实物验收结论。

## 此前：DCSSR / NCIR2 / Reflective IR

前批新增 `dcssr`（U140）、`ncir2`（U150）、`reflective-ir`（U175），同步6张 `reference-redraw` PNG。三款均提供 `Model` / `GroveModule` / `spec`、四芯 `grove` 和被动 `sensor`。该批完成时本地103款（14主机、89Unit），全部保持 `modeled`、`verified` 为0；公开Git基线仍为85款 `ad5d062`，随后十八款本地增量尚未再次推送。完整接口、配置和三分支四芯示例见[DCSSR/NCIR2/Reflective IR](DCSSR-NCIR2-REFLECTIVE-IR-UNITS.md)。

DCSSR为完整直流SSR套件，控制板和整机包络分别记录；中央 `button`、`rgb`、`power-led`、`ssr-led` 独立，四个 `ssr-screw-1`…`ssr-screw-4` 只改变螺钉头角度。`terminal-1` / `terminal-2` 各为 `ht3.96-4p`，`terminalPlug:true` 安装两只独立 `TerminalPlug`，各含四枚 `screw-1`…`screw-4`。按钮只发输入意图，灯和头角必须由调用方驱动，不实现继电/模式/Modbus或电气。

NCIR2保留真实TO39测温头、正面原壳舌 `button`、侧面原生一体壳舌 `reset`、`rgb` 和蜂鸣器实体；复位按键只发输入意图，不执行MCU复位，不虚构显示屏或声音输出。Reflective IR保留两颗真实IR收发封装、背面 `threshold` 电位器和固定红 `status-led`（实际壳内PCB灯，无新增外窗或穿壳halo）；电位器只外驱有限角/时长并拒非零RPM，不驱动检测距离、比较器或可见IR光束。总入口别名为 `DcssrUnit` / `DcssrUnitModule` / `DcssrTerminalPlug`、`Ncir2Unit` / `Ncir2UnitModule`、`ReflectiveIrUnit` / `ReflectiveIrUnitModule`。

三款原稿在私表中均无精确匹配，按已授权本款官图代码重绘，标 `reference-redraw`，不是照片裁片；字体/颜色、不可辨小字及贴图注册限制见单品研究。每个独立模型/模块传 `artwork:false` 关闭印刷，保留对应配置的全部物理attributes/index与世界矩阵。私表、私有链接、原稿名、矢量、官图/CAD原件、生成器和中间件仅留本地。必要专项为 `node scripts/check-dcssr-ncir2-reflective-ir-units.mjs`，综合检查范围以[本批进度](../artifacts/dcssr-ncir2-reflective-ir-expansion/progress.json)为准，没有逐面浏览器、全量历史或实物验收结论。

## 此前：Watering / HBridge v1.1 / DLight

前批新增 `watering`（U101）、`dlight`（U136）、`hbridge-v11`（U160-V11），均导出 `Model` / `GroveModule` / `spec`，提供四芯 `grove` 与被动 `sensor`。该批完成时本地100款（14款主机、86款Unit），全部保持 `modeled`、`verified` 为0；GitHub `main` 仍为85款 `ad5d062`，随后十五款本地增量未自动再次推送。完整调用、配置和三分支四芯线见[Watering/DLight/HBridge](WATERING-LIGHT-HBRIDGE-UNITS.md)。

Watering的 `inlet` / `outlet` 是两只真实 `silicone-tube-4mm` 机械口，拒绝Grove。产品 `Hose` 的总入口别名为 `WateringHose`；默认构造不装管，`hoses:true` 装入双管，配置菜单先列 `supplied-hoses` 再列裸本体。嵌套 `inlet/shape` / `outlet/shape` 接受 `{type:'shape',points:[[0,0,0],…]}`，点的单位为mm，管口局部首段沿+Y且至少6mm，起点必须 `[0,0,0]`；总计3…16个有限点，每轴范围±500mm，相邻点至少相距1mm。管道仅改变外观形状，没有水流、压力、泵驱动、液位或土壤数值。整机没有确证外露LED、按钮或可见转子，内部电机不注册虚构旋转关节。

DLight严格对应U136 BH1750FVI-TR，原壳24×32×8 mm，真实2.9×5.7 mm光学开窗后方有独立透明封装、被动暗色感测die和白PCB背衬。只有 `grove` 和被动 `sensor`，没有灯、按钮、关节、光束、lux/ADC/光学或I2C行为；P1/P2仅为隐藏未装配制造焊盘，不造用户插口。

HBridge的 `source`、`address-1`…`address-4` 是PCB上的五枚稳定 `Button`，实际位于壳内；默认闭壳，控件不接受画布pointer。`covers:false` 是开盖检查配置，可看/操作这些真实滑块；不是在闭壳表面新增开关。外驱 `position` 只移动实体，不执行电源选择、电压或地址运算。`terminal` 类型为 `ht3.96-4p`；产品入口另导出 `TerminalPlug`，模型以 `terminalPlug:true` 安装，并提供四个独立 `screw-1`…`screw-4` 外驱螺钉。`capacitor:true` 必须同时 `terminalPlug:true`，电容跨同一插头的前两槽，不新增插口，也不执行电机/供电行为。配置菜单保留闭壳三种附件组合和开盖检查配置，无LED API。

总入口模型别名为 `WateringUnit` / `WateringUnitModule`、`DlightUnit` / `DlightUnitModule`、`HbridgeV11Unit` / `HbridgeV11UnitModule`；附件别名为 `WateringHose` / `HbridgeV11TerminalPlug`。按需加载ID为 `watering`、`dlight`、`hbridge-v11`。

本批同步5张PNG：Watering机背1张 `source-vector-raster` 为精确原稿轮廓恢复，电机铭牌1张 `reference-redraw`；DLight背贴1张、HBridge正背2张同为 `reference-redraw`。源恢复不宣称未经修改的原稿直接导出。每个模型/模块分别传 `artwork:false`，在对应软管、端子、电容和盖配置下保留完整物理attributes/index与 `matrixWorld`。私表、私有链接、原稿名、矢量、原始官图/CAD、生成器与中间件不分发。必要专项入口为 `node scripts/check-watering-light-hbridge-units.mjs`；这里只登记入口，构建、接线、在线资源与隐私结果以本批进度报告为准，不预先声称综合通过，不新增逐面浏览器、全量历史或实物验收结论。

## 此前：Tube Pressure / MQ / LoRaE220-920

前批新增 `tube-pressure`（U130）、`mq`（U199）、`lora-e220-920`（U170），均导出 `Model` / `GroveModule` / `spec`，提供四芯 `grove` 和被动 `sensor`。该批完成时本地97款（14款主机、83款Unit），全部保持 `modeled`、`verified` 为0；GitHub `main` 仍是 `ad5d062` 的85款快照，随后十二款本地增量未自动再次推送。完整调用、配置菜单与三分支四芯线见[Tube Pressure/MQ/LoRa](RADIO-GAS-PRESSURE-UNITS.md)。

Tube Pressure的 `tube` 是前向单气嘴机械口 `tube-3mm`，无电气pin，拒绝Grove。真实Ø3mm气嘴、贯通管腔与独立感测背衬保留；原壳24×32×8 mm与含气嘴24×32×12.5 mm分别记录，没有第二气嘴、灯、按钮或旋转关节，不运行压力、气流、导管网络或电压逻辑。

MQ默认装入真实圆脚MQ-5感测封装，`mq5Cartridge:false`仅拆下圆罐，固定六孔座和内部适配板保留。`mq5`类型为 `mq5-six-pin`，产品入口导出 `MQ5Cartridge`，总入口别名 `Mq5Cartridge`；可经 `port('mq5').detach({dispose:false})` 和 `.attach(cartridge)`独立拆装。名义/原CAD24×64×25 mm保留厂家壳体口径；默认含圆罐实际包络约24×80.31×25 mm，拆罐后约24×64.4×25 mm，属于安装/照片推导，不能把厂家64mm标注套到含罐整机或缩壳凑数。无确证外露LED；隐藏D1封装不提供灯API，不执行加热、气敏电阻、ADC、报警或电气逻辑。

LoRa严格对应U170 E220-900T22S/920版。`mode-0` / `mode-1`为两枚稳定DIP：`press`切换、`release`保留档位，`cancel`结束本来源输入而不发送click；外部 `{type:'button', target:'mode-0', action:'position', position:1}`设置档位不回送输入。档位不改变串口、M0/M1电气网络或RF状态。`sma`是 `sma-female`；产品 `Antenna` 的总入口别名为 `LoraE220920Antenna`，`Antenna.meta.physicalConnector === 'sma-male'`记录真实公针，`meta.connector === 'sma-female'`表示可接入的主端口类型。默认 `antenna:false`显示本体，`antenna:true`装入随附110mm天线，`antennaAngleDeg`指定初始角。嵌套 `sma/tilt`接受 `angleDeg` / `durationMs`，范围0…90°，拒绝越界角和非零RPM；形状插值不产生RF、扫描或制造限位保证。本体名义24×71.4×8 mm包含SMA，不包含天线。配置菜单的首项为带天线、次项裸本体；MQ另列正常安装/拆罐配置，菜单默认展示与构造器默认选项分别记录。

本批同步8张PNG：Tube背贴1张 `reference-redraw`；MQ精确背标1张 `source-vector-raster`，标题、空白识别贴与MQ-5银圈印字3张 `reference-redraw`；LoRa正背与固定DIP的ON/1/2字样3张 `reference-redraw`。固定DIP字样不随滑块移动，MQ银圈字样属于可拆圆罐。各模型/模块分别传 `artwork:false`，关闭印刷保留各配置的完整实体attributes/index及物理世界姿态。私表、私有链接、原稿名、矢量、原始官图/CAD、生成器与中间件不分发。必要专项入口为 `node scripts/check-radio-gas-pressure-units.mjs`；这里只登记入口，两构建、接线、在线资源与隐私结果以本批进度报告为准，不预先声称综合通过，不新增逐面浏览器、全量历史或实物验收结论。

## 此前：ADC v1.1 / AMeter / VMeter

前批新增 `adc-v11`（U013-V11）、`ameter`（U086）、`vmeter`（U087），均导出 `Model` / `GroveModule` / `TerminalPlug` / `spec`，提供 `grove`、`terminal` 和被动 `sensor`。该批完成时本地94款（14款主机、80款Unit），全部保持 `modeled`、`verified` 为0；GitHub `main` 仍是 `ad5d062` 的85款快照，随后九款本地增量未自动再次推送。完整调用、三分支四芯线与附件边界见[ADC/AMeter/VMeter](ADC-METER-UNITS.md)。

ADC v1.1 的 `terminal` 是 `ht3.96-2p`，随附插头提供 `screw-1`…`screw-2`；AMeter与VMeter的 `terminal` 是 `ht3.96-4p`，随附插头各提供 `screw-1`…`screw-4`。三款均以 `terminalPlug:true` 安装，或通过 `port('terminal').attach(new TerminalPlug())` 独立装入/拆下。总入口别名分别为 `AdcV11TerminalPlug`、`AmeterTerminalPlug`、`VmeterTerminalPlug`。`terminal/screw-N` 接受 `angleDeg` / `durationMs`，只转对应螺钉头，非零RPM被拒绝；无轴向紧固、压线、扭矩或电气连接行为。端子机械类型拒绝Grove。

AMeter的 `power` 与VMeter的 `power-led` 各自默认关闭、接受外部亮度，不与Grove、螺钉或测量值自动联动。当前官方资料未确认发光色，固定预览色仅是外观估计；元数据保留 `colorConfirmed:false`，不能当成官方白灯规格或RGB能力。ADC v1.1没有灯、按钮或旋钮。三款 `sensor` 都是被动视觉锚点，不运行ADC采样、电流/电压、寄存器、校准、隔离、熔断、保护或固件逻辑。两款电表的名义壳体24×56×8 mm与含固定端子的24×56×10.2 mm视觉包络分别记录；ADC v1.1为24×32×10.2 mm，不缩掉真实端子来凑壳厚。

本批三款各2张PNG，共6张，全部按自身型号官图代码重绘并标记 `reference-redraw`，不裁产品照片。每个独立模型或Grove模块分别传 `artwork:false`；原壳、孔、PCB、触点、插头、螺钉及物理世界姿态保持。私表、私有下载链接、原稿名、矢量、原始官图、生成器与中间件不分发。必要专项入口为 `node scripts/check-adc-meter-units.mjs`；这里只登记入口，构建、接线与在线资源结果以本批进度报告为准，不预先声称综合验证通过，也不新增逐面浏览器、全量历史或实物验收结论。

前批 `timerpwr`（U189）、`extencoder`（U161）、`nfc`（U216）均提供 `Model` / `GroveModule`、`grove` 及被动 `sensor`。该批完成时为本地91款（14款主机、77款Unit），对应当时的六款Git同步后增量；调用、四芯线、附件和来源边界见[TimerPWR/ExtEncoder/NFC](TIMER-ENCODER-NFC-UNITS.md)。

TimerPWR的 `lcd` 是64×48白单色OLED，接受外部RGBA framebuffer后按亮度显示，不自动画计时器或电池状态。`button-a` / `button-b`沿真实原生侧弹舌压下/弹起，`press` / `release` / `cancel` 按各自来源处理；`power-led`为独立固定红灯，屏幕、按键与灯不自动联动。`usb`是 `usb-c-charge-only`，`battery`是 `mx1.25-2p`，仅提供机械配对与视觉元数据，不运行充电/供电状态机。

ExtEncoder的 `encoder` 为 `vh2.54-5p` 五芯机械接口；本体没有旋钮、按钮、LED或转子。`terminalPlug:true`安装随附插头；产品入口导出 `TerminalPlug`，总入口别名为 `ExtEncoderTerminalPlug`。`encoder/screw-1`…`screw-5`分别接受 `angleDeg` / `durationMs`，只转真实螺钉头、拒绝非零RPM；不产生ABZ、计数、压线、电压或轴向紧固。NFC严格对应U216 ST25R3916，只有 `grove` 与被动 `sensor`，没有扫描、标签、读写、卡模拟、RF场或灯/按钮命令；隐藏天线布线与安装为已标明的外观推导。

本批同步8张PNG：TimerPWR4张、ExtEncoder2张标记 `reference-redraw`；NFC正背2张标记 `source-vector-raster`，恢复转换器复合字形填充规则后保留原轮廓与填色，不宣称原稿未经修改直接导出。各模型/模块分别传 `artwork:false`；私表、下载链接、原稿名、矢量、生成器和中间件不分发。必要专项入口为 `node scripts/check-timer-encoder-nfc-units.mjs`；这里只登记入口，构建、接线与在线资源结果以本批进度报告为准，不新增逐面浏览器、全量历史或实物验收结论。

本地后续新增 `dac2`（U012-B）、`dds`（U105）、`kmeter-iso-v11`（U133-V11），均提供 `Model` / `GroveModule`、`grove` 及被动 `sensor`，没有新增可见LED或按钮。三款接口、可拆附件、四芯线和外部职责见[DAC2/DDS/KMeter](DAC-DDS-KMETER-UNITS.md)；这批属于 `ad5d062` 的85款Git同步之后的本地增量。

DAC2的 `terminal` 为 `ht3.96-4p`，`terminalPlug:true` 安装随附插头；产品入口的 `TerminalPlug` 全局别名为 `Dac2TerminalPlug`。`terminal/screw-1`…`screw-4` 独立接受 `angleDeg` / `durationMs`，只转螺钉头，拒绝非零RPM；固定座、PCB、其他螺钉和Grove线保持。A0/A1/A2保留真实固定焊盘/跳线，不生成外露DIP开关。模型不处理DAC值、电压、电流或短路保护。

DDS的 `sma` 机械类型为 `sma-female`；模型轴总包络24×71.4×8 mm包含SMA，原壳24×64×8 mm单独保留。壳上波形曲线属于固定印刷，不是外驱信号波形。KMeter的 `thermocouple` 机械类型为 `thermocouple-k-mini-flat`，保留真实K型扁槽与触点；没有猜测尺寸的热电偶 `Probe` 模块或温度/冷端补偿命令。两口都拒绝Grove，接口类型只约束机械配对。

本批同步7张PNG：DAC2正背2张为 `source-vector-raster`，原稿复合字形的填充规则从 `evenodd` 恢复为 `nonzero`；DDS正背2张为同型号官图 `reference-redraw`；KMeter正背2张为对应v1.1原稿栅格，前图导出透明度为0的圆环依对应预览恢复为半透明，K座印字另有1张 `reference-redraw`。这些恢复不宣称未经修改的原稿导出。每个模型/模块单独传 `artwork:false`，固定物理实体保持；私有表、源链接、矢量及生成中间件不分发。专项入口为 `node scripts/check-dac-dds-kmeter-units.mjs`，运行结果以对应报告为准，不新增逐面浏览器或实物验收结论。


`laser-tx`（U066）提供独立固定红色 `emitter`，默认关闭，只表现自身650nm印字对应的发射孔/透镜外观；`laser-rx`（U065）仅有 `grove` 和被动 `sensor`，深色接收头不注册为灯。两款没有按钮、关节、光束、光斑、通信或TX/RX状态联动。`midi`（U187）提供稳定 `mode`（0=左Bypass，1=右Separate）、独立固定绿 `power-led`（默认关闭）、`grove` 与被动 `sensor`。型号、命令、三分支四芯线和边界见[Laser/MIDI](LASER-MIDI-UNITS.md)。

MIDI 的 `midi-in-din` / `midi-out-din` 使用 `din-5pin-female`；`midi-in-trs` / `midi-out-trs` / `audio` 共享 `audio-3.5mm-trs` 机械配对类型，各自 `meta` 保留输入、输出和音频用途。机械配对不证明引脚、电平、光学或MIDI/音频电气兼容，改档不路由信号或产生声音。模型轴40×48×25 mm，厂商尺寸顺序48×40×25 mm。

三款同步6张正背 `reference-redraw` PNG，按同型号官方图代码重绘，未裁产品照片。原稿来源缺口和不可辨细字保留在单品记录中；原表、私有链接、矢量、生成器及中间件不分发。每个独立模型或模块分别传 `artwork:false`；接线仅表示机械装配/层级寻址，不建立TX/RX光学链路或HUB协议转换。

`earth`（U019）的 `trim` 是仅定位的真实调节头关节，无灯或按钮；`hall`（U084）只有 `grove` 和被动 `sensor`，D1 保留隐藏红色封装，没有无依据的可见 LED API。`qrcode`（U173）提供瞬时 `button`、稳定 `mode`、独立固定白光 `illumination` 与红光 `aiming`；默认 `{refractor:true}` 装固定折射头，`{refractor:false}` 显示直视扫描头，独立和 Grove 模块均可选择。具体命令、四芯线层级寻址及职责见[Earth/Hall/QRCode](EARTH-HALL-QRCODE-UNITS.md)。

三款同步7张PNG：Earth默认英文与显式 `stickerVariant:'education-cn'` 中文版共2张，均为 `source-vector-raster`（原稿轮廓/填色及可见层依对应预览和标准官图恢复，并非未修改原稿）；Hall两面为 `reference-redraw`；QRCode三个机身面为精确原稿 `official-raster`，不使用包装图。模型不实现湿度、阈值、磁场、扫码、电气或固件行为；各实例分别传 `artwork:false` 可关闭本批贴层。

`step16`（U198）提供真实16定位旋钮、八个独立暖黄显示段与独立RGB；`asr`（U194）提供固定喇叭/模拟麦克风，`uhf-rfid`（U107）提供实体陶瓷天线/板堆。三款同时带五张贴纸，UHF背贴使用所提供准确原稿栅格，其他面按官图重绘；API、机械分支示例、来源类型和各模块分别传 `artwork:false` 的方式见[Step16/ASR/UHF](STEP-ASR-UHF-UNITS.md)。

`mini-imu`（U095）提供完整MPU6886实体与纯视觉锚点，`extio2`（U011-B）提供真实10针弯针接口，`acssr`（U139）提供SSR/控制板套件、原生按键、三路独立外驱灯及两只可拆4P端子。三款同时带对应贴纸，姿态、输入/外驱状态和接线例子见[IMU/扩展IO/ACSSR](IMU-EXTIO-ACSSR-UNITS.md)。

此前补贴纸批的30款Unit已同步补对应印刷，精确原稿优先，缺源才按官方照片重绘；统一开关、Grove配置和来源/局部检查范围见[新增Unit贴纸](UNIT-STICKER-ADDITIONS.md)。

`poesp32`（U138）补双板/PoE/RJ45八触点，`cams3-5mp`（U174-B）补PY260固定镜头/卡槽/两组1×3母座，`synth`（U178）补内置喇叭与格栅后实体。真实插座类型、三枚独立固定色灯及三分支接线见[网络/摄像/合成Unit](NETWORK-CAMERA-SYNTH-UNITS.md)。新增同时补对应贴纸，源表与矢量仅本地保留。

`rtc`（U126）保留封闭电池/时钟器件外观，`fingerprint2`（U203）有真实电容采集面和独立灯环，`audioplayer`（U197）有真实卡槽/音频座和独立BUSY灯。三款只提供外观/锚点，接线与灯光寻址见[RTC/指纹/音频Unit](RTC-FINGERPRINT-AUDIO-UNITS.md)。

`rollercan` / `rollercan-lite` 和 `vibrator` 均通过 `rotor` 外驱真实旋转件。标准版的 `grove-top` 带动下级Unit与四芯线，Lite无顶部Grove；两款底部OLED和真实弹舌保持固定。组件路径、外部画面与转速示例见[旋转Unit](ROTATING-UNITS.md)。

`can`（U085）支持可拆4P端子、四个螺钉头和固定白色指示灯；`env-pro`（U169/BME688）与 `tof4m`（U172/VL53L1X）提供完整通风/光学实体与纯视觉锚点。独立模型、三分支Grove接线和职责见[CAN与环境/测距Unit](CAN-ENV-TOF-UNITS.md)。

`2relay` / `4relay` 支持随附4P端子独立装卸，插头内各有四个外驱螺钉；`dmx` 有稳定终端滑块、XLR释放片与固定红灯。Relay指示灯保持实际蓝/绿色，均不自动联动电气。配置、组件地址和职责见[Relay与DMX](RELAY-DMX-UNITS.md)。

`joystick2` 有 `tilt-x` / `tilt-y`、瞬时 `press` 和 `rgb`；`byteswitch` 有八枚保持档位的钮子杆，`bytebutton` 有八枚压放按钮，两款各九RGB及可继续级联的 `grove-out`。独立/多级接线、组件地址和输入边界见[可动输入Unit](INTERACTIVE-INPUT-UNITS.md)。

本库负责毫米尺度的外观、键帽行程、视觉关节、线缆和输入意图。下游负责固件、电气、总线、传感器值、设备状态及舵机/电机物理模型。默认模型静止；设置 `rpm` 只要求渲染器旋转，不表示给硬件通电。

`oled`（U119）与 `lcd`（U120）支持独立和 Grove 模块中的 `lcd` framebuffer，多屏可经 HUB 分别寻址。立式分辨率为 64×128 / 135×240，屏幕选择与 Unit 姿态不覆盖其他画面。`co2`（U103）提供完整实体与传感器视觉锚点；接入示例和职责见[显示 Unit](DISPLAY-UNITS.md)。

`pahub-v21`、`pbhub-v11` 各有输入 `grove` 和输出 `grove-0`…`grove-5`，六个输出均可挂接下级Unit及四芯线；层级路径和独立分支装卸见[多接口接线](MULTIPORT-UNITS.md)。`gesture`提供真实光学实体和Grove接口，不在模型内识别手势。

Weight-I2C 与8Servos可通过 `{terminalPlug:true}` 安装各自随附的四芯螺钉端子，也可对 `terminal` 手动装卸。`terminal/screw-1`…`screw-4` 是外驱头部角度，卸下插头不影响Unit或Grove线。示例、层级地址和职责见[可拆端子接入](UNIT-TERMINALS.md)。

新增 Unit 可用 `loadModel('gps-v11' | 'weight-i2c' | '8servos')` 独立展示，也可用相同ID的 `loadGroveModule()` 挂接主机。GPS定位、称重值、HX711采样、I2C通信和舵机PWM均由外部实现；模型内的接口和封装只描述可见实体。三款当前仅做必要结构/API检查与构建，未做逐面浏览器验收。

`fader` 的 `slider` 是独立的毫米位置控件（`kind: 'slider'`）：中位0、范围−17.5～17.5 mm，向+Y为正。使用 `model.get('slider').set({positionMm: 12, durationMs: 200})`，或 `model.handle({type:'slider', target:'slider', positionMm:12})`；挂接后路径为 `grove/slider`。读取 `getState()` 的 `positionMm`、`targetPositionMm`、`rangeMm`、`transitioning`、`dragging`。外驱设置越界会抛错；直接鼠标拖动限制在实体止点，松手保持位置，取消拖动也不弹回。`start`、`position`、`end` 输入仅表示用户拖动意图，`end.cancelled` 标记失焦/卸载取消；外驱 `set()` 不回送输入。导出的 `VisualSlide` 可供其他直线控件复用，`mesh` 应按零位在组件本地坐标建模；固定轨道不放入移动 `cap`。

`8angle` 提供 `rotation-1`…`rotation-8`，每个只接受−140～140°的绝对 `angleDeg`，不接受非零rpm；这对应官方280°总转角，中位为视觉基准，不代表ADC零点。`switch` 是保持档位的滑动开关，`rgb-1`…`rgb-9` 分别设置灯光。Fader的灯为 `rgb-1`…`rgb-14`。`mini-scales` 的实体功能键为 `button`，RGB为 `rgb`；秤台保持固定，不将重量、校准或传力形变作为可视状态。这三款同样支持 `loadGroveModule()`，所有组件路径随挂接层级前缀变化。

## 先使用公开 API

```js
import {DeviceViewer} from 'm5stack-models.js/core';
import {loadModel, loadGroveModule} from 'm5stack-models.js/loaders';

const viewer = new DeviceViewer(container, {keyboard: 'focused'});
const host = await loadModel('sticks3');
viewer.mount(host);

// 按需加载，挂接后原有组件路径继续成立。
const fan = await loadGroveModule('fan', {
  propeller: true, cableLength: 85,
  cable: {slack: 16, bend: [0, 0, -1]},
});
host.port('grove').attach(fan);
host.get('grove/rotor').set({rpm: 120});
host.get('grove/unitFrame').setDistance(100);
host.get('grove/cable').setOptions({slack: 24});
viewer.fit();

// 输入事件交给下游。不要把外部视觉状态命令回送为输入。
const off = host.on('input', event => runtime.sendInput(event));
```

`runtime` 是下游提供的对象。示例没有实现它，也没有向真实设备发送命令。Three.js 应由下游 bundler 去重，避免模型与 Viewer 各用一个 Three.js 实例。仓库导出源码，使用 ESM bundler 接入；不要把所有模型一次打进首屏。

`loadModel()` 返回的模型按需构建。首次直接调用 `getState()` 也会建立真实组件并返回当前快照，不需要先访问 `root`、`get()` 或 `list()`。挂接模块仍在对应端口的 `module.state` 下递归返回；它不读取硬件或执行固件。

## 输入、按压与稳定开关

```js
host.button('btnA').press('external-preview');
host.button('btnA').release('external-preview');
// 失焦、捕获丢失、组件卸载时取消；不产生 click。
host.button('btnA').cancel('external-preview');

host.handle({type: 'press', target: 'btnA'});
host.handle({type: 'release', target: 'btnA'});
```

同一个来源必须成对释放。多来源同时按住时，最后一个来源释放才回弹。`press` / `release` 会产生输入意图，适合交互注入；不要用它们反馈固件自己的键状态，避免回声循环。电容区 `travel=0`，有输入意图但不伪造机械位移。

`button.getActuationState()` 返回只读的 `{depthMm, targetDepthMm, settled}`，用于观察视觉插值是否到达终点；`getState()` 保持原输入状态结构。不要通过 `cap.position` 判断所有按键的行程：Button U027 的原壳片绕固定根部弯曲，Limit U145 的金属柄绕固定铰链转动。二者继续使用相同的 `press/release/cancel` 和输入路径，`meta.visualMotion` 分别为 `flex-pad` / `lever`。行程和角度中未获机械图确认的值均为外观估计。

CardKB v1.1（U035-B）有50个独立实体按钮，例如 `key-q`、`key-1`、`key-esc`、`key-up`；挂载后使用 `grove/key-q`。本层只发送各键按压意图，下游负责矩阵扫描、字符、组合键及I2C字节。它不是CardKB2。Cardputer-ADV新增 `grove-power` 两档滑块，只同步Grove供电方向选择器的外观，不切换任何电气状态。

CardKB 的 `AltLeft` 显式映射到 Sym 实体键，仅在模型画布聚焦时处理该 Alt 键自身。Alt 与其他键的组合、未映射的修饰键和表单输入继续留给浏览器；失焦或键释放会清除已有的模型按压来源。

Unit Key U144 使用 `press` 和独立的 `rgb`。红色空心键帽与轴芯一起压放，1.6 mm 行程是外观估计。官方规格表总高22.6 mm与机械图24.3 mm冲突，两者均保留，当前可见外形依据机械图。

Unit 8Encoder U153 使用 `rotation-1`…`rotation-8`、`press-1`…`press-8`、稳定档位 `switch` 及 `rgb-1`…`rgb-9`。CH1靠Grove端，CH8靠开关端。0.35 mm按压与2.2 mm开关档距为外观估计；灯位编号只对应几何位置，不能据此推定电气串链编号。

`Button.latching=true` 的滑动开关在首次按下时切换稳定档位，松手不会回位。外部状态同步可用 `setPosition(0|1)` 或 `handle({action:'position', target, position:1})`，不会模拟电源逻辑。读取 `getState().position`。不要把所有带 `power` 的旧 ID 当成电源：Tab5 的 legacy `power` 指向电池卡扣，Nesso 的 legacy ID 也要结合 label/meta 确认含义。

demo 的“定格检查”列出所有 Button，包括稳定滑块与零行程电容区，均可选择后近看。瞬时键与电容区支持保持／弹起；滑块通过上方独立开关切档，保持／弹起按钮禁用。悬停只提供外观高亮，按下／释放不自动点灯；验证压程时应比较同一悬停状态，并以真实帽体运动为准。电容区只改变输入状态，机械行程保持0。

“近看”只缩放和平移，保留当前模型旋转。检查侧面或背面的按钮时先选择对应视角，再选择按钮并近看，避免被壳体遮住的帽体造成压程不可见。

使用 `DeviceViewer({keyboard:'focused'})` 后仅聚焦 canvas 时处理设备快捷键。失焦、标签隐藏、卸载和 pointer capture 丢失会取消按住的输入；默认 `keyboard:true` 保留上游全局快捷键习惯。表单输入不会触发设备键。

## 关节命令与寻址

```js
const robot = await loadModel('stackchan');
robot.handle({type: 'joint', target: 'yaw', angleDeg: 30, durationMs: 400});
robot.handle({type: 'joint', target: 'pitch', angleDeg: 35, durationMs: 400});
// 有连续轴的组件才接受非零 rpm。
robot.get('yaw').set({rpm: 5});
robot.get('yaw').set({rpm: 0});

const encoder = await loadModel('encoder');
encoder.get('rotation').set({angleDeg: 90});
const joystick = await loadModel('joystick-v11');
joystick.get('tilt-x').set({angleDeg: 12});
joystick.get('tilt-y').set({angleDeg: -8});
joystick.button('press').click();
```

| 产品 | 组件路径 | 用法 |
| --- | --- | --- |
| StackChan | `yaw` / `pitch` | 底座不动；颈部水平旋转；头部俯仰 |
| Fan | `rotor` | 裸轴或可选风叶一起旋转 |
| Roller485 U182 | `rotor` / `press` | 标准滑环版转盘与顶端 Grove 随转，底部实体弹舌压放 |
| Encoder | `rotation` / `press` | 连续旋转及实体旋钮按压 |
| Angle | `rotation` | 外部绝对角度定位 |
| Light U021 | `trim` | 金属微调头绕局部+Z定位，蓝色座固定 |
| Joystick v1.1 | `tilt-x` / `tilt-y` / `press` | 两轴倾斜与倾斜后的局部按压 |
| Key | `press` / `rgb` | 实体键帽压放，灯光独立外驱 |
| 8Encoder | `rotation-1`…`rotation-8` / `press-1`…`press-8` / `switch` | 八路独立旋转/按压，开关保持档位 |

挂到 `grove` 后上述 Unit 路径都加 `grove/` 前缀。进一步嵌套的 HUB 同样按 Port 递归，不硬编码场景树 child 索引。可通过 `host.list('joint')`、`host.list('button')` 与组件 `.path` 枚举。

Roller485 为 U182 标准滑环版，`rotor` 绕模型 `+Y`，接受外部角度或连续视觉转速。转盘、外转子、顶端 `grove-top` 和 `top-led` 一起转；基座的 `lcd`、`press`、双 RGB、`grove`、`pwr485` 和 `debug` 固定。`lcd` 在底面 `-Y`，为 64×48 白色单色 OLED，外部 RGB 帧仅在产品局部着色器中按亮度显示为白光。`press` 的 0.25 mm 自由端压程与隐藏支撑为外观推导。

```js
const roller = await loadGroveModule('roller485', {cableLength:85});
host.port('grove').attach(roller);
host.get('grove/rotor').set({angleDeg:90});
host.get('grove/rotor').set({rpm:20});
host.get('grove/rotor').set({rpm:0});
host.display('grove/lcd').fill('#ffffff');
roller.port('grove-top').attach(await loadGroveModule('env-iii'));
```

顶端挂接后的组件路径为 `grove/grove-top/…`，装配姿态相对该转动端口；线缆/子组件随接口坐标变换，调用方可另设 `unitFrame` 姿态。接口显示不传播供电或 I2C/RS485 信号。`rgb-1/rgb-2` 是空间位置编号，不推定电气链序；`top-led` 是固定红色，只接受亮度/开关的外观效果，不因挂接或电机状态自动点亮。`pwr485/debug` 保留真实连接器外形与元数据，不属于 Grove 连接菜单。

角度为度、`durationMs` 为毫秒、`rpm` 为视觉转速；传给关节的是它自身局部轴上的角度。StackChan 的 pitch 使用当前正视装配为 0，正角抬头，接受 `[0,90]`；这不是硬件舵机的校准零位。Angle/Joystick 的 demo 滑条范围只用于观察姿态，不能作为机械限位或传感器换算关系。轴线与范围依据见 [VISUAL-MOTION.md](VISUAL-MOTION.md)。

Light U021 的 `trim` 只旋转有厚度、带真实工具槽的金属头，位置为`[0,2.5,3.72]` mm，局部轴为`+Z`。它是位置式关节，拒绝非零rpm；`visualRangeDeg=[-135,135]`仅供demo观察，`rangeDeg=null`，额定机械限位、旋向和电气零位未确认。头半径1.5 mm、槽深0.32 mm及蓝色座尺寸均为照片估计。调用方直接指定外观角度，不在本层换算电阻、光强阈值、比较器结果或ADC值。

```js
const light = await loadModel('light');
light.get('trim').set({angleDeg:45});

const lightHost = await loadModel('sticks3');
lightHost.port('grove').attach(await loadGroveModule('light', {cableLength:70}));
lightHost.handle({type:'joint',target:'grove/trim',angleDeg:-45});
```

StackChan 的前侧 Power 板跟随 pitch，下端 Adapter 跟随 yaw，七根可见线束跨两组端点更新；底座 USB 固定。官方后部为开放机构，不能用虚构后盖封住。线束路线及隐藏舵机包装为视觉近似，不模拟材料、电气或碰撞求解。

`getState()` 提供 `angleDeg`、`targetAngleDeg`、`rpm`、`transitioning`、`continuous`、`rangeDeg`、`visualRangeDeg`、`demoRpmMax`。绝对角度命令停止原有 rpm；新的 rpm 命令取消原有角度插值。模型不自动运行点头、摆头、测量或固件逻辑。

## Encoder U135

`rotation`、`press` 与独立的 `led0/led1` 保留原寻址，挂到主机后使用 `grove/rotation`、`grove/press`、`grove/led0` 等递归路径。实际Ø10黑帽和轴绕原CAD collar拟合轴 `[-0.0130000268,7.9499998353,6]` mm旋转；0.35 mm按压仅为外观行程估计。固定支撑、PCB和Grove座保持静止，不生成编码计数、脉冲、I2C或固件行为。

两RGB位于Grove两侧下端，`led0/led1`分别表示正视左/右，尚未确认对应原理图LED1/LED2的电气顺序。官方视频显示白壳下端漫透；外部颜色/亮度驱动原前壳自身的局部emissive外观，默认熄灭，按压/转动不自动改变灯色。这不声明光学材料或光线输运模拟。

```js
const encoder = await loadGroveModule('encoder', {cableLength:70});
host.port('grove').attach(encoder);
host.get('grove/rotation').set({angleDeg:90});
host.button('grove/press').press('preview');
host.button('grove/press').release('preview');
host.handle({type:'led',target:'grove/led0',color:'#22b477',brightness:.4});
host.handle({type:'led',target:'grove/led1',on:false});
```

Thermal U016只保留`sensor`视觉anchor，不提供温度、热图、IR可见光或运动命令。其`grove`口面由旧`[0,-15.65,0]`改为`[0,-15.65,1.4]` mm；10×5.2 mm座体来自自身机械图，Z1.4由原CAD入口对齐推导。默认`loadGroveModule('thermal')`与`unitFrame.setDistance`按当前真实口对齐；显式`unitPose.position`仍是装配原点。依赖旧工程坐标的调用者读取当前Port变换，递归路径（如`grove/grove-1/sensor`）、插头与四芯线API保持。完整110°黑包体与小窗为外观实体，凹面深度、板形/高度和裁短脚含推导，见[Thermal建模记录](THERMAL-MODEL-NOTES.md)。

Angle U005保持`rotation`绝对角度接口和递归路径，例如`host.handle({type:'joint',target:'grove/rotation',angleDeg:37})`。本批将旧轴心Y7校正为自身图纸Y8，含齿帽直径遵循Ø9.5；固定包体/板/金属框不随动。实际Grove工程原点从`[0,-15.65,0]`改为`[0,-15.65,1.4]` mm，5.2 mm高度来自自身CAD槽底−1.2到前面+4的包络推导，非官方标注口高。默认模块自动对齐，显式unitPose仍是装配原点；依赖旧坐标的布局读取当前Port变换。网页名义厚度22与机械图总高22.3分开记录。`rpm`仍拒绝，viewer范围不等于机械限位或传感器换算。见[Angle建模记录](ANGLE-MODEL-NOTES.md)。

U135实际 `grove` 口面原点由旧 `[0,-15.65,0]` 更正为 `[0,-15.65,-0.6]` mm，Z取自该产品原壳 `-3.2…2` mm开口中点。`loadGroveModule`和`unitFrame.setDistance`按真实口面重新对齐；直接使用旧Port工程坐标的布局应读取当前Port变换，显式`unitPose.position`仍为装配原点。隐藏PCB/包体/焊腿、帽轴深度、口内尺寸和漫透亮斑范围仍为推导。公开来源与推导见[Encoder来源记录](../source-manifest.json)，专项审查见[Encoder审查记录](../artifacts/encoder-detail/public/review.json)，当前stage保持`modeled`。

NCIR U028保留`sensor`视觉anchor，不提供温度、热图、IR可见光或运动命令。真实`grove`口面由旧`[0,-15.65,0]`改为`[0,-15.65,1.4]` mm，座体10×5.2 mm和入口上下界有本款机械图／CAD依据。默认`loadGroveModule('ncir')`与`unitFrame.setDistance`按当前真实口对齐；显式`unitPose.position`仍是装配原点。依赖旧工程坐标的调用者读取当前Port变换，递归路径（如`grove/grove-1/sensor`）、插头与四芯线API保持。完整TO39的金属筒、凸冠、Ø3.5凹窗和真实环隙分开建模；PCB、安装yaw、脚裁长及局部台阶含推导，见[NCIR建模记录](NCIR-MODEL-NOTES.md)。

PCB孔内壁现按实际FrontSide几何检查，Thermal／Angle／Encoder修复不改变公开组件、Port坐标或外驱状态；下游接法保持。相关拓扑回归与历史证据边界见[PCB孔内壁说明](PCB-HOLE-WINDING.md)。

## Grove 装配坐标

`Port` 原点在口面，局部 +Y 向外、+Z 朝宿主正面，1 单位 = 1 mm。`cableLength` 兼容旧入口，表示初始口面间距，曲线实际长度请读 `cable.getState().curveLengthMm`。

```js
const frame = host.get('grove/unitFrame');
// position 是 Unit 装配原点在宿主 Port 局部坐标的位置；rotation 为弧度。
frame.setPose({rotation: [0, 0, Math.PI / 6]});
// 保留当前旋转，把 Unit 的真实输入口对准 [0,90,0]。
frame.setDistance(90);
const geometry = host.get('grove/cable').getState();
// geometry.source / target 是两端真实口面的相对位置与朝向。
```

线缆跟随端点和方向，不做碰撞求解。调用方要避免任意摆放引起模型互穿或线缆穿过其他物体。详见 [GROVE-CABLE.md](GROVE-CABLE.md)。

CardputerZero C154 的外围坐标在 2026-10-26 按官方正面及斜视照片校正。以正视屏幕时 +X 向右为基准，HDMI/音频/Grove 组移到右侧，USB-A/RJ45/Boot 组移到左侧；microSD 和顶部红外件同步修正。组件 ID、连接器类型、按键输入和帧缓冲 API 保留，依赖旧硬编码左右坐标的调用方需要迁移：

| 组件 ID | 当前口面位置 mm | 当前外法向 |
| --- | --- | --- |
| `grove` | `[42.04,13.1,0.85]` | `+X` |
| `hdmi` | `[42.04,-13.6,0.5]` | `+X` |
| `headset` | `[42.04,0.1,1.1]` | `+X` |
| `usb-c2` | `[42.04,13.1,6.65]` | `+X` |
| `usb-c` | `[-42.04,13.1,6.65]` | `-X` |
| `usb-a` | `[-42.04,13.1,-0.7]` | `-X` |
| `ethernet` | `[-42.04,-13.8,-3.1]` | `-X` |
| `micro-sd` | `[-18.1,27.03,6.0]` | `+Y` |
| `ext` | `[0,27.03,1.2]` | `+Y`，保持原位 |

默认 Grove 连接会跟随更正后的右侧真实口面，继续使用 `host.port('grove').attach(...)`。直接布局先调用 `host.root.updateMatrixWorld(true)`，再读取 Port 的 `object3d.matrixWorld` 或 `getWorldPosition/getWorldQuaternion`，不要复用旧 `[-42.04,13.1,0.85]`。Boot 固定原点变为 `[-41.85,0.4,5.6]`，按下沿世界 `+X` 向壳内移动，`boot` 的 press/release/cancel 用法保持。官方图稿存在不同 C1/C2 标号修订，模型不据印刷图案推断 USB 协商、供电或电气角色。

Heart U029 的工程坐标修正：依据其自身官方10×5.2 mm口图和原壳Z=−1.2…4的开口，`grove`口面中心由历史`[0,-15.65,0]`更正为`[0,-15.65,1.4]` mm。RS485 U034的中心仍是`[0,-15.65,1.4]`。两款现为真实开放顶槽、短锁定舌、四触点及5.2 mm外部座高；下部8.6 mm通道、6.8 mm上槽、短针及凹入内底、深度／壁厚和Heart PCB切口仍为外观推导，不声明实物公差。

`loadGroveModule('heart',{cableLength:70})`会从实际输入口重新对齐，默认目标口仍为宿主Port局部`[0,70,0]`，调用方法和递归路径保持。直接使用旧Heart Port工程坐标的布局应重新读取`heart.port('grove').object3d.position`；显式`unitPose.position`仍表示装配原点，不会静默加减1.4 mm。要按输入口定位，应在设旋转后调用`unitFrame.setDistance(...)`或读取真实Port世界变换。

HUB 可继续接 Unit，demo 的 Grove 接口菜单使用完整路径，例如 `grove/grove-1`，并排除已被上游线占用的 Module 输入口。连接/断开后保留有效选口；祖先模块拆卸后回到仍存在的祖先接口。

```js
const hub = await loadGroveModule('hub', {cableLength:70});
host.port('grove').attach(hub);
hub.port('grove-1').attach(await loadGroveModule('scroll', {cableLength:60}));
host.get('grove/grove-1/rotation').set({rpm:30});
host.button('grove/grove-1/press').press('external');
host.button('grove/grove-1/press').cancel('external');
host.get('grove/grove-1/rgb').set({color:'#22b477',brightness:.4});
```

Unit Scroll U186 的 `rotation` 沿自身 +X 转轴，`press` 使用独立输入来源，`rgb` 由外部控制。轮组、源 CAD 与隐藏支撑的视觉映射及按压估计见 [VISUAL-MOTION.md](VISUAL-MOTION.md)；不生成编码计数或 I2C 数据。

## 屏幕帧缓冲与目标选择

`host.list('display')` 返回包括挂接模块的屏幕，使用各组件的完整 `.path` 定位，例如 `lcd`、`grove/lcd` 或 `grove/grove-1/lcd`。通过 `host.display(targetPath).writeRGBA(rgba)`、`writeRGB565()` 或 `fill()` 写入外部像素；目标路径、像素内容和驱动协议由调用者提供。

demo 的“屏幕校准图”仅写当前所选屏幕。多屏时显示目标选择框；没有主机屏幕但接入带屏 Unit 时同样可用。选择、连接或拆卸只刷新目标，不清除其他屏已有的帧；同名路径替换后使用新的组件身份与校准状态。单色标记的 OLED 使用灰阶校准图，电子纸关闭校准时恢复纸色底。校准不是固件页面，也不模拟显示器驱动或刷新过程。

## 屏幕触点

```js
host.on('input', event => {
  if (event.kind === 'display' && event.id === 'lcd') {
    // action: start / move / end；x/y: 左上原点的整数像素。
    // pointerId 区分触点，points 为当前仍活动的点。
    externalRuntime.sendInput(event);
  }
});
const lcd = host.display('lcd');
lcd.touch('start',10,20,1);
lcd.touch('move',14,22,1);
lcd.touch('end',14,22,1);
lcd.setTouchEnabled(false);
```

指针取消和移出屏幕沿用 `end`，不增加新的输入 action。禁用会逐点结束活动触点；最终销毁静默清空并释放标记。`touch()` 是外部直接注入入口，仍可在指针触控禁用时使用；清理和销毁过程中不会重新创建触点。屏幕帧缓冲与触点输入相互独立，不自动执行设备页面或固件行为。

## 外部灯光状态

```js
const keys = await loadGroveModule('8encoder');
host.port('grove').attach(keys);
host.get('grove/rotation-1').set({angleDeg: 135});
host.button('grove/press-1').press('preview');
host.button('grove/press-1').release('preview');
host.get('grove/rgb-1').set({color: '#22b477', brightness: 0.4});
host.get('grove/rgb-1').set({on: false});
```

灯光的 kind 为 `led`，用 `host.list('led')` 枚举。`Led.set({color,brightness})` 或 `handle({type:'led',target,…})` 更新外观，亮度范围0…1；`getState()` 返回颜色和亮度。它不会产生输入事件或与按键自动联动。demo的“灯光外观”面板使用相同公开API。

`invisible:true` 保留器件透镜及外部状态接口，但不产生人眼可见的 emissive 或 glow；demo 灯位菜单只列可见光器件。StickS3 的 `irTx` 继续接受原路径命令和状态查询，标记为不可见红外，不再渲染成红色指示灯。本库不模拟红外传输、波束或手机相机效果。

Heart U029 的 `red-led` 表示 MAX30100 靠 Grove 一端的可见红光孔，默认熄灭、颜色固定为`#ff2820`；任意`color`请求都保留红色，只接受外部开关／亮度。远 Grove 的圆窗是被动 SENSOR，不会跟着亮；IR 不绘为可见光。包体和两光心来自原厂p27，安装朝向由官方照片的非对称外形对应推导；绝对座深、透镜剖面、材质和视觉亮度仍为推导，不声明光学仿真。

```js
const heart = await loadModel('heart');
heart.handle({type:'led', target:'red-led', brightness:.6});
heart.handle({type:'led', target:'red-led', on:false});
host.port('grove').attach(await loadGroveModule('heart', {cableLength:70}));
host.handle({type:'led', target:'grove/red-led', brightness:.4});
```

demo会发现该灯位并禁用任意选色。调用方应明确给定亮度；本库不根据产品名、心率、测量模式、上电或挂接自动闪烁。原厂资料明确区分RED 660 nm与IR 880 nm，并说明纯心率模式的红灯关闭；不得从模型可见红光推断传感数据。

Color U009 的两颗白色补光使用`fill-left`、`fill-right`，默认颜色`#ffffff`、亮度0。两个路径标识左右可见封装，D1/D2与左右的对应尚未确认。官方原理图中两灯各经1K电阻接同一VCC，没有独立GPIO控制；按实际供电状态展示时，由调用方给两灯相同亮度。统一`Led`接口的`color`只是绘图参数，硬件仍为白灯，不据此声明RGB能力。本库不随挂接、上电或测量自动点灯；封装深度和光扩散为外观估计。

```js
const color = await loadModel('color');
for (const id of ['fill-left','fill-right']) color.led(id).set({brightness:.4});

const colorHost = await loadModel('sticks3');
colorHost.port('grove').attach(await loadGroveModule('color', {cableLength:70}));
colorHost.handle([
  {type:'led',target:'grove/fill-left',brightness:.4},
  {type:'led',target:'grove/fill-right',brightness:.4},
]);
```

所选旧版Relay U023保持无外驱灯组件。其[官方原理图](https://m5stack-doc.oss-cn-shenzhen.aliyuncs.com/577/UNIT-RELAY.pdf)中的D1为1N4148WS续流二极管，图中未含状态LED，对应正面照片也未定位可见灯。产品概述的“状态指示灯”表述与该来源冲突，反馈回执为`a3df6baaef22420dac639e23af0b302a`，仅代表接收待评估；在版本、物料位号和实际灯位得到确认前，不添加猜测灯或电气联动。

Cardputer-ADV 与 StamPLC 各有一颗 Stamp-S3A RGB，统一 ID 为 `stamp-rgb`，默认熄灭，例如 `host.handle({type:'led',target:'stamp-rgb',color:'#22b477',brightness:.65})`。StamPLC 文档中的红色下载指示是同一颗 RGB 的一种状态，模型不额外添加第二颗红灯；颜色／亮度由调用方给定，不实现下载启动顺序、GPIO38 供电门控或按键自动点灯。封装深度与光扩散仍是外观估计，原盖板的遮挡边缘保留。

StackChan 顶部 `touch-1`、`touch-2`、`touch-3` 为前／中／后三个零行程电容输入区，仍用 Button 的 `press/release/cancel`；左右各有 `rgb-left-1`…`rgb-left-6` 与 `rgb-right-1`…`rgb-right-6`。灯号表示从前向后的外观分段，不声明电气链顺序；边界、分段间距和光扩散为推导。全部随头部 pitch/yaw，触摸不会自动点灯。原来 pitch90° 中区被盖板挡住的问题已按源螺孔轴配准盖座修正，默认检查要求30姿态／90条整机顶面法向接近全部命中触区。该有限方向采样不保证任意相机角度可达，也不证明全局头颈datum、隐藏舵机或制造配合。

## Relay U023 的负载端子附件

默认 Relay 带开放的固定 3P 座。`terminal` 是独立的 `ht3.96-3p` 外观接口，三列从左到右为 COM、NO、NC，节距3.96 mm；它不会出现在 Grove 挂接目标中。`TerminalPlug` 是可拆附件，随附件出现的三颗工具槽螺钉可分别接收位置式转角：

```js
import {TerminalPlug} from 'm5stack-models.js/units/relay';

const relay = await loadModel('relay');
relay.port('terminal').attach(new TerminalPlug());
relay.handle({type:'joint', target:'terminal/screw-2', angleDeg:45});
relay.handle({type:'detach', target:'terminal'});

// 与真实 Grove 外观装配组合，路径按层级寻址。
host.port('grove').attach(await loadGroveModule('relay', {terminalPlug:true}));
host.handle({type:'joint', target:'grove/terminal/screw-1', angleDeg:-60});
host.handle({type:'detach', target:'grove/terminal'}); // 保留 Relay 与 Grove 线缆
```

`loadModel('relay', {terminalPlug:true})` 也可直接显示已插状态。demo 的“固定3P座／安装螺钉插头”配置可切换两种装配；已插状态显示三个螺钉角度控件。`screw-1`…`screw-3` 对应 COM／NO／NC，只转螺钉头，不接受非零 rpm，不实现螺纹升降、夹紧力、负载线路或触点通断。±180° 是查看范围，额定机械范围未确认。

`nominalMm` 保留官方规格表的24×48×8 mm基壳口径；`visualEnvelopeMm` 为官方机械图的24×48×14.6 mm外露装配，后螺钉另突出约0.055 mm。PCB、端子壁厚、内部接触深度和插头夹线结构为照片推导，接口类型名只用于本库几何配对，不证明不同厂家的实物通配。

## RS485 U034 的4P端子附件

U034 默认仍为空固定座。官方包装中随附的可拆4P端子由该产品入口导出的`TerminalPlug`提供，类型为`ht3.96-4p`；从左到右物理标签是B、A、12V+、12V-。可用`terminalPlug:true`直接装上，或单独挂接。它与Relay的3P附件分别导入，按各自连接器类型匹配。

```js
import {TerminalPlug as Rs485TerminalPlug} from 'm5stack-models.js/units/rs485';
const rs485 = await loadModel('rs485');
rs485.port('terminal').attach(new Rs485TerminalPlug());
rs485.handle({type:'joint',target:'terminal/screw-4',angleDeg:45});
rs485.handle({type:'detach',target:'terminal'});

host.port('grove').attach(await loadGroveModule('rs485', {terminalPlug:true}));
host.handle({type:'joint',target:'grove/terminal/screw-2',angleDeg:-60});
host.handle({type:'detach',target:'grove/terminal'}); // 保留Unit与Grove线缆
```

`screw-1`…`screw-4`随附件挂接出现，分别对应四个标签，只旋转真实工具槽螺钉头。固定座、接触孔、线入口和夹笼保持实体深度；不执行螺纹升降、夹线、RS485/UART、供电或电气连接。demo的固定4P座／安装4P螺钉插头配置可切换装配；±180°为查看范围，不是额定机械限位。官方未提供该附件工程图，局部尺寸与插入深度为照片推导，HT3.96-4P名称不证明厂牌通配。

## 渲染与生命周期

`DeviceViewer` 自动调用 `host.update(dt, time)` 并在姿态变化时渲染。自建渲染器必须调用它，`dt` 和 `time` 单位均为秒；持续 rpm、插值与键帽动画会返回动画标志。外部的直接变换需要请求渲染；关节和线缆 setter 已请求。

```js
// 自建渲染循环：
host.update(deltaSeconds, elapsedSeconds);
renderer.render(scene, camera);

// 断开默认 dispose；复用时显式保留。
const saved = host.port('grove').detach({dispose: false});
host.port('grove').attach(saved);
host.port('grove').detach();
off();
viewer.unmount(host); // 卸载不销毁，允许缓存复用。
host.dispose();      // 最终清理 geometry/material/timer。
viewer.dispose();
```

同一 Module 实例再次 `attach` 到原接口是幂等操作；挂到另一兼容接口时会从旧口安全转移，保留实例状态和资源。兼容性与循环挂载检查发生在装配变更前。同步生命周期回调不能重挂正在装卸的同一实例或正在挂载的目标口，也不能拆卸正在挂接的新实例；这些操作会抛错，应等当前调用结束后再发起下一次装配（例如使用 `queueMicrotask`）。替换目标口旧实例时的正常拆卸不受影响。默认 `detach()` 销毁实例；需要缓存时使用 `detach({dispose:false})`，最终由调用方销毁。

拆卸前会沿原宿主链同步发出 `module:will-detach`，事件载荷为 `{port,module}`。此时旧路径和父子关系仍有效，适合取消将被移除子树中的外部输入；它是生命周期事件，不是新的 `input` action。查看器与 demo 只取消各自持有的输入，无关按钮继续保持。外部框架创建的 hold 应由该框架取消，并在更改父链前完成配对；取消使用 `button.cancel(source)`，不会产生 click。

同一 Viewer 重复 `mount(host)` 不重复订阅或更新；跨 Viewer 挂载会先解除旧 Viewer 的归属。`unmount` 取消旧 Viewer 持有的键盘/指针输入，但不销毁模型。若下游缓存带有持续运动的模型，需自行决定卸载时是否 `set({rpm:0})`；demo 切换模型时会停止连续轴，返回缓存时保持停止。

demo 的异步 Unit 加载在切换模型、接口或 Unit 后会作废旧请求，未挂载的过期实例会释放。连接刷新保留仍有效的按键检查位置和 LED 选位；DOM 控件被替换时取消其输入，明确的“保持按下”只在目标仍存在且仍被选中时保留。

## 修改后验证

从仓库根目录运行 `npm run check`、`npm run build`、`./manage.sh status`。专项测试覆盖真实帽位移/方向/回位、固定根部弯曲、刚性杠杆、多键与多旋钮、稳定档位、多来源取消、关节父子装配、静止与终帧、目录内Unit线缆端点与默认姿态穿壳。另检查所有真实主机Grove口、CoreS3 DinBase及StackChan组合姿态中的插头坐标与渲染线管表面轨迹；覆盖数以当前生成报告为准。

生命周期专项为 `scripts/check-port-lifecycle.mjs`、`scripts/check-viewer-lifecycle.mjs`、`scripts/check-demo-lifecycle.mjs`，已接入正常检查。Viewer 专项运行真实查看器与输入路由，以无 GPU renderer 和 DOM 边界替身检查所有权和取消顺序；这些替身不提供浏览器视觉证据。

还需打开 demo，实际操作按键按住/回弹、模型快捷键与表单焦点、连接/断开、端点旋转、风叶转动、摇杆倾斜与按压、StackChan 组合姿态。Node 几何测试不能替代浏览器画面，也不能证明下游模拟器、真实硬件、机械配合或硬件限位正确。

## 正式栅格贴纸

2026-10-26 起，缺原稿的可读印刷面按用户授权加入官方照片参考重绘。运行时 `userData.artworkKind === 'reference-redraw'`，与原稿栅格的 `official-raster` / `official-raster-film` 分开标记；各产品的 `artwork-redraw.md` 记录精确参考和未还原项。重绘的高像素不代表厂商矢量或电气引脚证据。既有原稿层和显式教育版保留，`artwork:false` 同样关闭参考重绘层。

正式贴纸默认启用，`artwork: false`关闭本批栅格层。历史七款Unit与新增Earth另提供显式`stickerVariant: 'education-cn'`，Earth的两版原稿恢复边界见[本批指南](EARTH-HALL-QRCODE-UNITS.md)；独立模型与Grove模块分别传选项，父主机选项不自动传播。贴图固定于真实壳体、盖、帽或关节，外部框架无需逐帧重设贴纸坐标。覆盖、缺面、位图精度和许可边界见[贴纸记录](STICKER-COVERAGE.md)。旧照片裁切保持关闭。

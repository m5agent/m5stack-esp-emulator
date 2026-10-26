# 新增 Unit 贴纸接入

2026-10-26。下表保留此前81款新增Unit的印刷记录，本批新增ID、RF433R、RF433T三款及6张PNG，现列84款。三款正背各1张，均按本款官图代码重绘 `reference-redraw`，不裁照片、不借其他型号或编造不可辨文字。此前30款回补及各批来源/验收快照分别保留，原先43款范围见[覆盖记录](STICKER-COVERAGE.md)。当前本地127款（14主机、113Unit），全部 `modeled`、`verified` 为0。本次127款源码同步包含112款基线 `32c95e0` 后新增的15款Unit/28张对应PNG及三旧端子闭合修复，范围见[127款同步记录](GIT-SYNC-127-2026-10-26.md)。历史progress中的未提交/未推送字样仅描述其保存时点，远端状态以GitHub main及实际推送回执为准。30批记录见[本地增量索引](LOCAL-EXPANSION.md)。

| 产品ID | SKU | 当前来源类型 | PNG数 | 具体面与限制 |
| --- | --- | --- | --- | --- |
| `poesp32` | U138 | 原稿膜 / 原稿栅格 | 3 | [来源与配准](research/poesp32/README.md) |
| `cams3-5mp` | U174-B | 原稿栅格 / 原稿膜 | 4 | [来源与配准](research/cams3-5mp/modeling.md) |
| `synth` | U178 | 参考重绘 | 2 | [来源与配准](research/synth/artwork.md) |
| `8angle` | U154 | 原稿膜 / 参考重绘 | 2 | [来源与配准](research/8angle/artwork.md) |
| `pahub-v21` | U040-B-V21 | 原稿栅格 | 2 | [来源与配准](research/pahub-v21/stickers.md) |
| `pbhub-v11` | U041-B | 原稿栅格 | 1 | [来源与配准](research/pbhub-v11/stickers.md) |
| `2relay` | U131 | 原稿栅格 | 3 | [来源与配准](research/2relay/STICKERS.md) |
| `env-pro` | U169 | 原稿栅格 | 1 | [来源与配准](research/env-pro/STICKERS.md) |
| `fingerprint2` | U203 | 原稿栅格 | 2 | [来源与配准](research/fingerprint2/STICKERS.md) |
| `byteswitch` | U191 | 参考重绘 | 2 | [来源与配准](research/byteswitch/artwork.md) |
| `bytebutton` | U192 | 参考重绘 | 2 | [来源与配准](research/bytebutton/artwork.md) |
| `gps-v11` | U032-V11 | 参考重绘 | 2 | [来源与配准](research/gps-v11/artwork.md) |
| `weight-i2c` | U180 | 参考重绘 | 2 | [来源与配准](research/weight-i2c/artwork.md) |
| `8servos` | U165 | 参考重绘 | 3 | [来源与配准](research/8servos/artwork.md) |
| `fader` | U123 | 参考重绘 | 1 | [来源与配准](research/fader/artwork.md) |
| `mini-scales` | U177 | 参考重绘 | 3 | [来源与配准](research/mini-scales/artwork.md) |
| `joystick2` | U024-V2 | 参考重绘 | 1 | [来源与配准](research/joystick2/artwork.md) |
| `gesture` | U127 | 参考重绘 | 1 | [来源与配准](research/gesture/stickers.md) |
| `oled` | U119 | 参考重绘 | 1 | [来源与配准](research/oled/stickers.md) |
| `lcd` | U120 | 参考重绘 | 1 | [来源与配准](research/lcd/stickers.md) |
| `co2` | U103 | 参考重绘 | 1 | [来源与配准](research/co2/stickers.md) |
| `tof4m` | U172 | 参考重绘 | 1 | [来源与配准](research/tof4m/stickers.md) |
| `rtc` | U126 | 参考重绘 | 2 | [来源与配准](research/rtc/stickers.md) |
| `4relay` | U097 | 参考重绘 | 5 | [来源与配准](research/4relay/STICKERS.md) |
| `dmx` | U183 | 参考重绘 | 2 | [来源与配准](research/dmx/STICKERS.md) |
| `can` | U085 | 参考重绘 | 2 | [来源与配准](research/can/STICKERS.md) |
| `rollercan` | U188 | 参考重绘 | 3 | [来源与配准](research/rollercan/STICKERS.md) |
| `rollercan-lite` | U188-Lite | 参考重绘 | 3 | [来源与配准](research/rollercan-lite/STICKERS.md) |
| `vibrator` | U059 | 参考重绘 | 1 | [来源与配准](research/vibrator/stickers.md) |
| `audioplayer` | U197 | 参考重绘 | 2 | [来源与配准](research/audioplayer/stickers.md) |
| `mini-imu` | U095 | 参考重绘 | 3 | [来源与配准](research/mini-imu/artwork.md) |
| `extio2` | U011-B | 参考重绘 | 1 | [来源与配准](research/extio2/artwork.md) |
| `acssr` | U139 | 参考重绘 | 2 | [来源与配准](research/acssr/README.md) |
| `step16` | U198 | 参考重绘 | 1 | [来源与配准](research/step16/artwork.json) |
| `asr` | U194 | 参考重绘 | 2 | [来源与配准](research/asr/artwork.md) |
| `uhf-rfid` | U107 | 原稿栅格 / 参考重绘 | 2 | [来源与配准](research/uhf-rfid/artwork.md) |
| `earth` | U019 | 原稿轮廓/填色及可见层恢复栅格 `source-vector-raster` | 2 | 默认英文；显式 `education-cn` 中文教育版；[接入与边界](EARTH-HALL-QRCODE-UNITS.md) |
| `hall` | U084 | 参考重绘 `reference-redraw` | 2 | 正面方向图、背面型号/信号及引脚色块；[来源与配准](research/hall/artwork.md) |
| `qrcode` | U173 | 精确原稿栅格 `official-raster` | 3 | 正面、背面、侧面 UART/I2C 标；包装不接入；[接入与边界](EARTH-HALL-QRCODE-UNITS.md) |
| `laser-tx` | U066 | 参考重绘 `reference-redraw` | 2 | 正背标；保留自身650nm及OUT印字，不作为接口电气依据；[接入与边界](LASER-MIDI-UNITS.md) |
| `laser-rx` | U065 | 参考重绘 `reference-redraw` | 2 | 正面接收示意/机名，背面频率/PORT.B/引脚块；[来源与配准](research/laser-rx/artwork.md) |
| `midi` | U187 | 参考重绘 `reference-redraw` | 2 | 正背对应机身印刷；固定承载面与稳定滑块分离；[接入与边界](LASER-MIDI-UNITS.md) |
| `dac2` | U012-B | 原稿轮廓栅格 `source-vector-raster` | 2 | 正面T形端子/机名/Grove标、背面GP8413/I2C标；复合字形填充由 `evenodd` 恢复 `nonzero`；[来源与配准](research/dac2/artwork.md) |
| `dds` | U105 | 参考重绘 `reference-redraw` | 2 | 正面机名/波形曲线，背面器件框图/接口标；固定印刷不模拟波形；[来源与配准](research/dds/artwork.md) |
| `kmeter-iso-v11` | U133-V11 | v1.1原稿恢复栅格 / 参考重绘 | 3 | 正背原稿2张，前图alpha为0的圆环按对应预览恢复半透明；K型插座印字另重绘1张；[接入与边界](DAC-DDS-KMETER-UNITS.md) |
| `timerpwr` | U189 | 参考重绘 `reference-redraw` | 4 | 正面机名、按键提示、顶侧充电/电池接口标、背面覆膜；不复制屏幕内容；[接入与边界](TIMER-ENCODER-NFC-UNITS.md) |
| `extencoder` | U161 | 参考重绘 `reference-redraw` | 2 | 五芯座上方固定接口标与背贴；本体没有旋钮或转子；[接入与边界](TIMER-ENCODER-NFC-UNITS.md) |
| `nfc` | U216 | 原稿轮廓恢复栅格 `source-vector-raster` | 2 | 蓝色NFC正标、ST25R3916/I2C背标；复合字形填充由 `evenodd` 恢复 `nonzero`，包装不接入；[来源与配准](research/nfc/artwork.md) |
| `adc-v11` | U013-V11 | 参考重绘 `reference-redraw` | 2 | 固定2P座正负标与背面ADC V1.1/ADS1110/I2C标；不套旧ADS1100型号；[来源与配准](research/adc-v11/artwork.md) |
| `ameter` | U086 | 参考重绘 `reference-redraw` | 2 | 正背对应机身印刷；固定4P端子与可拆插头保持真实实体；[接入与边界](ADC-METER-UNITS.md) |
| `vmeter` | U087 | 参考重绘 `reference-redraw` | 2 | 正背对应机身印刷；不套用AMeter或隐藏原孔；[接入与边界](ADC-METER-UNITS.md) |
| `tube-pressure` | U130 | 参考重绘 `reference-redraw` | 1 | 背面型号/PORT.B/引脚块；前面无贴纸；背面贴纸下方M5浮雕保留原CAD；[来源与配准](research/tube-pressure/artwork.md) |
| `mq` | U199 | 精确背标原稿栅格 `source-vector-raster` / 参考重绘 `reference-redraw` | 4 | 原稿背标1张；机名、空白识别贴、可拆MQ-5银圈字样重绘3张；[接入与边界](RADIO-GAS-PRESSURE-UNITS.md) |
| `lora-e220-920` | U170 | 参考重绘 `reference-redraw` | 3 | 正背本款920标、固定DIP上的ON/1/2；不随两滑块移动，不套433版或LoRaWAN；[接入与边界](RADIO-GAS-PRESSURE-UNITS.md) |
| `watering` | U101 | 原稿轮廓恢复栅格 `source-vector-raster` / 参考重绘 `reference-redraw` | 2 | 精确机身背标1张、电机铭牌1张参考重绘；双管不靠贴纸封口；[接入与边界](WATERING-LIGHT-HBRIDGE-UNITS.md) |
| `dlight` | U136 | 参考重绘 `reference-redraw` | 1 | 背面DLIGHT/BH1750FVI-TR/PORT.A/引脚条；前面无贴纸，光学窗保留真实封装与背衬；[来源与配准](research/dlight/artwork.json) |
| `hbridge-v11` | U160-V11 | 参考重绘 `reference-redraw` | 2 | 正背对应机身印刷；真实壳内DIP与外壳贴纸分离，开盖/附件配置按指南保留；[接入与边界](WATERING-LIGHT-HBRIDGE-UNITS.md) |
| `dcssr` | U140 | 参考重绘 `reference-redraw` | 2 | 本款DCSSR机身与直流SSR标签，不混用交流SSR；[接入与来源](DCSSR-NCIR2-REFLECTIVE-IR-UNITS.md) |
| `ncir2` | U150 | 参考重绘 `reference-redraw` | 2 | 本款壳面印刷，金属感测头/真实孔口保留；[接入与来源](DCSSR-NCIR2-REFLECTIVE-IR-UNITS.md) |
| `reflective-ir` | U175 | 参考重绘 `reference-redraw` | 2 | 正面收发符号与背面型号/阈值方向/接口条，真实电位器孔不以贴纸替代；[接入与来源](DCSSR-NCIR2-REFLECTIVE-IR-UNITS.md) |
| `thermal2` | U149 | 参考重绘 `reference-redraw` | 2 | 本款正背标；原壳舌和黑色MLX90640开口保留，不套NCIR2；[接入与来源](THERMAL2-FLASHLIGHT-GPS-UNITS.md) |
| `flashlight` | U152 | 参考重绘 `reference-redraw` | 2 | 背贴与开盖PCB固定模式标；印刷随真实承载件可见性；[接入与来源](THERMAL2-FLASHLIGHT-GPS-UNITS.md) |
| `gps-sma` | U190 | 参考重绘 `reference-redraw` | 3 | 本体正背及随附有源天线puck正标，不贴到RF/Grove孔口；[接入与来源](THERMAL2-FLASHLIGHT-GPS-UNITS.md) |
| `bldc-driver` | U181 | 参考重绘 `reference-redraw` | 2 | 本款正背标，固定相线座/可拆插头保留实体；[接入与来源](BLDC-RCA-PUZZLE-UNITS.md) |
| `rca` | U155 | 参考重绘 `reference-redraw` | 2 | 背贴与固定PCB I1/I2标，不随壳内滑钮移动；[接入与来源](BLDC-RCA-PUZZLE-UNITS.md) |
| `puzzle` | U193 | 参考重绘 `reference-redraw` | 2 | 本体背部双Grove/方向标和独立桥件背标，正面64灯及栅格是实体；[接入与来源](BLDC-RCA-PUZZLE-UNITS.md) |
| `rs485-iso` | U094 | 参考重绘 `reference-redraw` | 2 | 本款正背标；固定VH3.96座、随插头拆装的电阻及独立指示灯均保留实体；[接入与来源](ISOLATED-INTERFACE-UNITS.md) |
| `ain4-20ma` | U162 | 参考重绘 `reference-redraw` | 2 | 本款正背标；真实六针和独立跳帽不靠印刷替代，无数值sensor/LED/button；[接入与来源](ISOLATED-INTERFACE-UNITS.md) |
| `ac-measure` | U164 | 原稿恢复栅格 `source-vector-raster` | 2 | 精确机身正背标，保留原色，复合字腔 `evenodd`→`nonzero`恢复；包装排除；[接入与来源](ISOLATED-INTERFACE-UNITS.md) |
| `uwb` | U100 | 原稿恢复栅格 `source-vector-raster` | 2 | 标准机身正背标，保留原色与轮廓，恢复复合字腔；包装/照片排除；内置天线与PCB实体独立；[接入与来源](RANGING-PRESENCE-UNITS.md) |
| `tmos-pir` | U185 | 参考重绘 `reference-redraw` | 2 | 本款正背标保留光学开口；真实金属封装/硅滤光窗和PCB背衬，不套旧PIR半球；[接入与来源](RANGING-PRESENCE-UNITS.md) |
| `mini-tof-90` | U196 | 参考重绘 `reference-redraw` | 2 | 本款正背标；固定直角双板/光窗/Grove侧实体嵌件独立，不以贴图替代；[接入与来源](RANGING-PRESENCE-UNITS.md) |
| `roller485-lite` | U182-Lite | 参考重绘 `reference-redraw` | 3 | 本款PORT.A/PWR485/debug可读印字；OLED、柔性壳舌和电机转子独立实体；[接入与来源](ROLLER-MINI-CAN-INA226-UNITS.md) |
| `mini-can` | U179 | 参考重绘 `reference-redraw` | 2 | 本款MINI CAN机身正背标；非隔离SO8/PCB、真实插座及胶贴基底独立；[接入与来源](ROLLER-MINI-CAN-INA226-UNITS.md) |
| `ina226-10a` | U200 | 原稿恢复栅格 `source-vector-raster` | 2 | 精确10A/5mΩ正背机身原稿，恢复复合字腔；不混1A/包装；PCB/隔离封装/分流实体独立；[接入与来源](ROLLER-MINI-CAN-INA226-UNITS.md) |
| `mini-pdm` | U089 | 参考重绘 `reference-redraw` | 2 | 本款前麦克风符号及背面CLK/DAT针序；MEMS声孔/PCB与胶片独立；表13mm/原图原壳8mm分别保留；[接入与来源](AUDIO-PRESSURE-UNITS.md) |
| `mini-bps-v11` | U090-B | 参考重绘 `reference-redraw` | 2 | 精确QMP6988 v1.1前BPS与背PORT.A/I2C针序；不混U090 BMP280；金属气孔/PCB及胶片独立；[接入与来源](AUDIO-PRESSURE-UNITS.md) |
| `mic` | U096 | 参考重绘 `reference-redraw` | 1 | 本款背面型号/接线标签；真实麦克风孔网/阈值头/PCB和胶片独立；[接入与来源](AUDIO-PRESSURE-UNITS.md) |
| `accel` | U056 | 参考重绘 `reference-redraw` | 2 | 本款正背印刷；传感封装/PCB与胶贴基底独立，锚点不含加速度数值；[接入与来源](ACCEL-OP90-OP180-UNITS.md) |
| `op90` | U057 | 参考重绘 `reference-redraw` | 1 | 本款背面型号/针序；固定光电封装、收发窗口及真空气槽独立，不混OP180；[接入与来源](ACCEL-OP90-OP180-UNITS.md) |
| `op180` | U058 | 参考重绘 `reference-redraw` | 1 | 本款背面型号/针序；5mm真槽、相对光窗和固定顶部封装，胶贴基底独立，不混OP90；[接入与来源](ACCEL-OP90-OP180-UNITS.md) |
| `unit-id` | U124 | 参考重绘 `reference-redraw` | 2 | 本款正背印刷；ATECC608B-TNGTLSU-G/PCB与胶贴基底独立，无身份值或加密/I2C模拟；[接入与来源](ID-RF433-UNITS.md) |
| `rf433r` | U113 | 参考重绘 `reference-redraw` | 2 | 本款接收器正背印刷；固定内置PCB天线，不混发射版，不造外接天线或RF动效；[接入与来源](ID-RF433-UNITS.md) |
| `rf433t` | U114 | 参考重绘 `reference-redraw` | 2 | 本款SYN115与OUT正背印刷；固定内置PCB天线、真实六脚封装，不混接收版；[接入与来源](ID-RF433-UNITS.md) |

每款已接入的面和仍缺的小字以单品记录为准，不表示所有印刷面都已完整还原。2Relay部分正面小字缺原稿支持；Fingerprint2原稿中的指纹图形只有200×200像素，保持原生位图并与高清矢量文字分层，未放大冒充更高精度。营销图上的尺寸箭头、屏幕保护膜和外部注释不会作为永久印刷贴到屏幕或活动帽。相似Module/HAT、新旧Unit的贴纸不混用。

原稿栅格标记`official-raster`/`official-raster-film`；UHF准确原稿直接栅格的运行时标记为`official-vector-raster`。Earth依据对应预览和标准官图恢复原稿轮廓/填色及可见层，标记`source-vector-raster`；DAC2与NFC同样标记`source-vector-raster`，恢复范围为原稿复合字形的填充规则`evenodd`→`nonzero`，原有填色和可见面保留。KMeter两面原稿的运行时类型为`official-vector-raster`，前面透明度为0的圆环按对应预览恢复半透明；以上恢复均不宣称未经修改的原稿导出。Watering机背精确原稿的轮廓恢复同样标记`source-vector-raster`，具体恢复范围见单品记录。重新绘制的文字/图形标记`reference-redraw`。字体、颜色、安装尺寸/位置的推导在单品文档说明；这些标签仅为外观，不提供电气引脚或协议行为。新代码MIT；印刷和商标保留权利。表格、私有下载链接、矢量原稿、生成器及转换中间只留仓库外，公开仅最终普通PNG与配准代码。

```js
const model = await loadModel('byteswitch');         // 默认带对应印刷
const bare = await loadModel('byteswitch', {artwork:false});
const wired = await loadGroveModule('byteswitch', {artwork:false});
```

选项应传给每个独立模型或模块，父主机选项不自动传播。印刷随真实壳、平台或所属物件；只有实物连续贴膜桥过原生服务孔时使用`printedFilm`，`artwork:false`下原孔及后方组件全部保留。ByteSwitch/ByteButton前面印字0在底部CH0，对应API控件1；印字7在顶部CH7，对应控件8。

必要检查为`node scripts/check-unit-sticker-additions.mjs`，可在命令后传产品ID缩小范围；覆盖新增印刷非空、来源标记、开关、非印刷实体缓冲/姿态不变和Grove四芯装配。各作者另将新贴层和修改前物理基线比较，保留原按钮/开关/旋钮/附件和线缆API。两个工作副本构建与在线资源字节检查另记在[本批记录](../artifacts/unit-sticker-additions/progress.json)。未逐面浏览器、全量73款或实物验收，阶段保持`modeled`。


Step16 / ASR / UHF-RFID 本批与模型同时接入五张PNG。Step16仅背贴，正面和原旋钮保持实物白色；ASR两面按精确Unit U194官图重绘，未套用Module M147。UHF背贴使用当前原稿的 `UP TO 1M` 与黑标题版本，2400×2400 PNG／30×30 mm；正面天线图为官图参考重绘，3300×2200 PNG／33×22 mm。ASR背贴忠实保留印字8Ω@1W，同时记录正文0.8W差异，不作为额定电气数据。必要装配/开关检查及调用方式见[本批接入](STEP-ASR-UHF-UNITS.md)，对应专项为 `node scripts/check-step-asr-uhf-units.mjs`。本批未作逐面浏览器或全目录验收；旧贴纸报告仍只对应其原始快照。

## Earth / Hall / QRCode 同批印刷

本批单独记录7张PNG：Earth默认英文背标和显式 `stickerVariant:'education-cn'` 中文教育版共2张，Hall正背参考重绘2张，QRCode三个机身原稿面3张。Earth两版均标记 `source-vector-raster`，原稿轮廓/填色及可见层按用户所给预览和对应标准官图恢复；不宣称未经修改的原稿导出。QRCode排除包装素材，正背与侧面 UART/I2C 标保留其真实承载壳体关系。

Earth默认不切换为中文教育版；可用 `loadModel('earth', {stickerVariant:'education-cn'})` 或对 Grove 模块传相同选项。`artwork:false` 的优先级高于变体。三款真实控件、Grove接线与外部框架边界见[本批接入](EARTH-HALL-QRCODE-UNITS.md)；局部检查入口为 `node scripts/check-earth-hall-qrcode-units.mjs`，检查结果以对应记录为准。当前不新增逐面浏览器或全目录验收结论，旧报告仍只对应原始快照。


## Laser TX / Laser RX / MIDI 同批印刷

本批独立记录6张 `reference-redraw` PNG，三款各正背2张。已检索所提供表格的精确型号来源，暂无对应原稿；按同型号官方图中可辨文字和图形代码重绘，不裁产品照片，不套用相似型号。TX保留自身650nm与OUT印字，RX背贴保留IN，Grove元数据分别按官方接口表保留DIN与DOUT；贴纸文字不充当电气行为。不可辨细字、字体/颜色/尺寸及配准推导按单品记录保留。

TX/RX各印刷投影到自身原壳，MIDI印刷留在真实固定承载面，均随对应物件姿态保持配准。`artwork:false` 分别传给模型/模块；关闭贴层不删除原孔、接收/发射实体、插座、光导或滑块。调用和必要专项入口 `node scripts/check-laser-midi-units.mjs` 见[本批接入](LASER-MIDI-UNITS.md)，结果以对应记录为准。本段不宣称本批构建、在线资源或浏览器验收通过，也不将此前43款、30款回补、36款或39款快照合并成全量验收。私有表、下载链接、矢量原稿、生成器和中间件继续留在仓库外；公开仅最终PNG、配准及来源说明。


## DAC2 / DDS / KMeter-ISO v1.1 同批印刷

本批单独记录7张PNG，不并入历史43款、此前30款回补及36/39/42款新增快照。DAC2优先使用精确机身原稿，正面T形标和背面GP8413/I2C标共2张；复合字形填充规则由 `evenodd` 恢复 `nonzero` 后保留原稿轮廓和填色，标记 `source-vector-raster`。DDS缺对应原稿，按本款官方照片代码重绘正背2张，标记 `reference-redraw`，波形曲线和器件框图只作为固定印刷。

KMeter使用U133-V11对应正背原稿2张，不套旧版。前面原稿转换后圆环透明度为0，按对应预览恢复半透明并明确记录源恢复；K型插座上可辨标记另按同型号官图重绘1张。原稿栅格与参考重绘分别标记，包装图和不可辨字不补造。三款共7张图片的像素、来源与配准按各款 `artwork.json` 记录；源矢量、私表、下载链接和生成中间件不进入公开目录。

`artwork:false` 分别传给每个模型或Grove模块，关闭贴层保留完整原壳、孔、PCB、SMA/K插座与DAC2端子/螺钉。调用、三分支四芯线和必要专项 `node scripts/check-dac-dds-kmeter-units.mjs` 见[本批指南](DAC-DDS-KMETER-UNITS.md)。本段只登记同批印刷与检查入口，构建和在线资源以相应进度报告为准，不宣称逐面浏览器、全量历史或实物验收通过。


## TimerPWR / ExtEncoder / NFC 同批印刷

本批独立记录8张PNG，不并入历史43款、此前30款回补或36/39/42/45款新增快照。TimerPWR按自身U189官方照片代码重绘4张：正面机名、按键提示、顶侧充电/电池接口与背贴；屏幕仍由外部framebuffer负责，不裁取计时界面当永久贴纸。ExtEncoder按自身U161官方照片重绘固定五芯座接口标和背贴2张；两款共6张均标记 `reference-redraw`，不可辨小字及配准推导以单品记录为准。

NFC采用U216自身正背精确原稿，不套用旧PN532 NFC或RFID2。复合字形填充由 `evenodd` 恢复 `nonzero` 后保留原轮廓与填色，直接高清栅格成2张PNG，标记 `source-vector-raster`；不宣称未经修改的转换器导出。独立包装贴、预览图、原稿、原文件名、私表、下载URL、矢量和生成中间件均不分发，公开仅最终普通PNG、配准代码和安全来源说明。

每个模型/模块分别传 `artwork:false`，关闭印刷不删除原壳、孔、OLED/按键、五芯座/插头/螺钉、Grove触点或NFC实体天线。调用与三分支四芯线见[本批指南](TIMER-ENCODER-NFC-UNITS.md)，必要专项入口为 `node scripts/check-timer-encoder-nfc-units.mjs`。这里只登记接入和检查入口，构建、在线资源与专项结果以本批进度报告为准，不新增逐面浏览器、全量历史或实物验收结论。


## ADC v1.1 / AMeter / VMeter 同批印刷

本批单独记录6张PNG，三款各2张，全部标记 `reference-redraw`。所提供表格无这三款精确原稿，按自身型号官方照片中可辨文字、色块和图形代码重绘；不裁产品照片、不使用相似型号。ADC v1.1固定2P座的正负标与背面ADS1110/接口标按U013-V11保留，不把旧ADS1100正文差异转成模型行为；AMeter与VMeter各自保留自身正背印刷。可辨范围、字体/颜色和配准推导按各款研究记录说明。

每个模型/模块分别传 `artwork:false`，关闭印刷保留真实原壳、孔、PCB、固定座、可拆插头与螺钉。两款电表的指示灯是独立物理光路，固定预览色仅为发光色未确认时的外观估计，`colorConfirmed:false`；PNG与灯都不执行测量或电气逻辑。API、三分支四芯线、两/四/四个螺钉头和检查入口见[本批指南](ADC-METER-UNITS.md)，必要专项为 `node scripts/check-adc-meter-units.mjs`。这里只记录来源与入口，构建、接线和在线资源结果以本批进度报告为准，不预先宣称综合验证、逐面浏览器、全量历史或实物验收通过。私表、私有下载链接、原稿名、矢量、原始官图、生成器与中间素材均留仓库外，公开仅最终普通PNG、配准和安全来源说明。


## Tube Pressure / MQ / LoRaE220-920 同批印刷

本批单独记录8张PNG，新增Unit表由51款增至54款；不回写历史43款、30款回补或此前各批快照。Tube Pressure只有官图确证的背贴1张，按同型号照片代码重绘为 `reference-redraw`；正面保留真实单气嘴，不添加虚构贴纸；背面贴纸下方的M5浮雕保留原CAD。

MQ背面精确机身原稿栅格1张标记 `source-vector-raster`，原稿转换/恢复范围以单品来源记录为准，不称未经修改的原稿导出；机名标题、空白识别贴、MQ-5银圈字样3张为 `reference-redraw`。空白识别贴保持原样，不补造气体名称或工作状态；银圈字样随可拆MQ-5圆罐，拆罐保留固定座与适配板。LoRa按U170/920自身官图重绘正背与固定DIP的ON/1/2共3张，标记 `reference-redraw`；固定字样不随两枚稳定滑块移动，天线折叠不改变固定机身印刷。

每个模型/模块分别传 `artwork:false`，保留完整原壳、开孔、PCB、感测封装、管嘴深腔、固定座、DIP与可拆圆罐/天线的物理attributes/index和世界姿态。MQ名义/CAD24×64×25 mm与默认含罐约24×80.31×25 mm、拆罐约24×64.4×25 mm分别记录；LoRa的两DIP与0…90°天线关节仅表达形状和输入意图，不实现气体/加热/压力/RF或电气逻辑。配置菜单、四芯线和必要专项入口 `node scripts/check-radio-gas-pressure-units.mjs` 见[本批指南](RADIO-GAS-PRESSURE-UNITS.md)。构建、接线、在线资源和隐私结果以对应进度报告为准，不预先声称综合验证通过，也不新增逐面浏览器、全量历史或实物验收。私表、私有下载链接、原稿名、矢量、原始官图/CAD、生成器和中间材料均不分发，公开仅最终普通PNG、配准及安全来源说明。


## Watering / DLight / HBridge 同批印刷

本批独立记录5张PNG，不并入历史43款、此前30款回补或36/39/42/45/48/51/54款新增快照。Watering机背按精确原稿轮廓恢复并栅格化，标记 `source-vector-raster`；电机铭牌可辨部分另按同型号官图代码重绘1张。DLight背贴1张及HBridge正背2张均为 `reference-redraw`，不可辨小字不补造，不裁产品照片。原稿恢复范围、字体/颜色、安装尺寸及配准推导按单品记录保留，不宣称厂商原稿未经修改直接导出。

`artwork:false` 分别传给各独立模型/Grove模块；完整原壳、真孔、DLight感测封装/背衬、Watering双软管与机械口、HBridge开盖/闭壳/端子/电容配置的物理attributes/index和世界姿态保持。调用与必要专项 `node scripts/check-watering-light-hbridge-units.mjs` 见[本批指南](WATERING-LIGHT-HBRIDGE-UNITS.md)，综合结果以对应进度报告为准；不预先声称两构建、在线资源、逐面浏览器、全量历史或实物验收通过。原表、私有URL/原稿名、矢量、官图/CAD原文件、生成器与中间件仅在仓库外保留，公开仅最终普通PNG、配准代码及安全来源说明。


## DCSSR / NCIR2 / Reflective IR 同批印刷

本批6张PNG按各自官方照片代码重绘，不复制产品照片像素，不套相近型号，不编造不可辨小字，不用印刷掩盖缺件。仅公开最终普通PNG、配准和安全来源说明，原表、私有链接/原稿名、矢量、官图/CAD原文件、生成器和中间件留仓库外。各配置 `artwork:false` 关闭印刷保留完整实体、真实孔口和装配世界矩阵。用法和专项 `node scripts/check-dcssr-ncir2-reflective-ir-units.mjs` 见[本批指南](DCSSR-NCIR2-REFLECTIVE-IR-UNITS.md)，检查范围以本批进度记录为准；不增加逐面浏览器或实物验收结论。


## Thermal2 / FlashLight / GPS SMA 同批印刷

本批7张PNG（Thermal2 2、FlashLight 2、GPS SMA 3）均为同型号官图代码重绘，不复制照片像素、不编造不可辨小字、不套相近型号、不用贴纸遮缺件。各配置 `artwork:false` 保留完整原壳、真实光学封装/孔、PCB、双原壳舌、壳内模式开关及可拆带线天线的物理attributes/index和世界矩阵。具体来源/注册限制与必要专项 `node scripts/check-thermal2-flashlight-gps-units.mjs` 见[本批指南](THERMAL2-FLASHLIGHT-GPS-UNITS.md)，综合结果以本批进度为准；没有新增逐面浏览器或实物验收。原表/私有链接/原稿名/矢量/官图CAD原文件/生成器/中间件仅留仓库外，公开最终普通PNG、配准与安全说明。


## BLDC Driver / RCA / Puzzle 同批印刷

本批6张PNG（BLDC Driver 2、RCA 2、Puzzle 2）均为本款官图代码重绘。正面灯阵、插孔、真实端子和开关由物理几何表现，不裁照片/编字/贴纸遮缺件。`artwork:false` 关闭印刷并保留对应插头/闭壳/开盖配置的所有物理attributes/index/世界矩阵；固定PCB丝印随真实PCB保留，不随活动件移动。来源/字体颜色/注册限制与专项 `node scripts/check-bldc-rca-puzzle-units.mjs` 见[本批指南](BLDC-RCA-PUZZLE-UNITS.md)，检查范围以本批进度为准；没有新增逐面浏览器或实物验收。原表/私有链接/原稿名/矢量/官图CAD原件/生成器/中间件只留仓库外，公开最终普通PNG及安全配准/来源。


## RS485-ISO / AIN4-20mA / AC Measure 同批印刷

本批6张PNG（每款2张）：RS485-ISO、AIN4-20mA均按自身官图代码重绘，标 `reference-redraw`；AC Measure精确机身原稿恢复为 `source-vector-raster`，原色和轮廓保留，只修正转换中的 `evenodd`→`nonzero`字腔填充，包装排除。重绘不裁照片、不编造不可辨文字。实际端子/电阻/六针/跳帽/PCB/封装均为物理几何，贴纸不补缺件。

`artwork:false`保留对应盖/插头/电阻/跳帽配置全部物理attributes/index与世界矩阵。必要专项 `node scripts/check-isolated-interface-units.mjs`和[本批指南](ISOLATED-INTERFACE-UNITS.md)登记接线、配件、外驱动作及印刷开关范围；综合结果以[本批进度](../artifacts/isolated-interface-expansion/progress.json)为准，没有新增逐面浏览器、全量历史或实物验收。私表、私有链接/原稿名、矢量、官图CAD原件、生成器与中间件仅留仓库外，公开最终普通PNG及安全配准/来源。


## UWB / TMOS PIR / Mini ToF-90 同批印刷

本批6张PNG（每款2张）：UWB标准机身正背原稿恢复为 `source-vector-raster`，保留原色、轮廓，仅恢复转换中的 `evenodd`→`nonzero`复合字腔；包装/照片排除。TMOS PIR与Mini ToF-90按各自官图代码重绘，标 `reference-redraw`，不裁产品照片、不编造不可辨文字。完整原壳、真实PCB/内置天线、金属/光学封装与胶贴基底均独立建模，贴纸不掩盖缺件。

`artwork:false`保持两入口全部物理attributes/index及最顶层更新后的世界矩阵。必要专项 `node scripts/check-ranging-presence-units.mjs` 和[本批指南](RANGING-PRESENCE-UNITS.md)登记四芯Grove、被动锚点与Mini ToF红灯独立外驱范围；综合结果以[本批进度](../artifacts/ranging-presence-expansion/progress.json)为准，没有新增逐面浏览器、全量历史或实物验收。私表、私有链接/原稿名、矢量、官图CAD原件、生成器与中间件仅留仓库外，公开最终普通PNG及安全配准/来源。


## Roller485 Lite / Mini CAN / INA226-10A 同批印刷

本批7张PNG：Roller485 Lite的PORT.A/PWR485/debug三张及Mini CAN正背两张为同型号官图代码重绘 `reference-redraw`；INA226-10A两张为精确U20010A/5mΩ机身原稿恢复栅格 `source-vector-raster`，保留颜色/轮廓并恢复复合字腔，排除1A版本与包装。没有产品照片裁切、预览放大或不可辨文字编造。完整原壳、真实PCB/封装、端子接触件和胶贴基底均独立建模，印刷不遮缺件。

`artwork:false`保持两入口及裸座/带插头配置的全部物理attributes/index与世界矩阵。必要专项 `node scripts/check-roller-mini-can-ina226-units.mjs`、[本批指南](ROLLER-MINI-CAN-INA226-UNITS.md)登记真实Grove线、Roller转子/壳舌/OLED/RGB及三款四螺钉附件的外驱范围；综合结果以[本批进度](../artifacts/roller-mini-can-ina226-expansion/progress.json)为准，没有新增逐面浏览器、全量历史或实物验收。私表、私有链接/原稿名、矢量、官图CAD原件、生成器与中间件仅留仓库外，公开最终普通PNG及安全配准/来源。


## Mini PDM / Mini BPS v1.1 / MIC 同批印刷

本批5张 `reference-redraw` PNG：Mini PDM前符号/背针序、Mini BPS v1.1前BPS/背PORT.A针序各两张，MIC背面一张。每张依据本款官图可辨文字和图形代码重绘，没有照片裁片、预览放大或不可辨小字编造。BPS严格U090-B QMP6988，不混旧U090 BMP280；PDM官方13mm表与8mm尺寸图/原壳冲突继续记录，原壳不缩放并有真实反馈。各款PCB、金属封装、通气/声学孔网、Grove、独立胶贴基底和MIC调节头均为实体，贴纸不遮缺件。

`artwork:false`保持两入口全部物理attributes/index与世界矩阵。必要专项 `node scripts/check-audio-pressure-units.mjs`、[本批指南](AUDIO-PRESSURE-UNITS.md)登记三款四芯线、被动锚点及MIC有限角 `threshold` 外驱范围；综合结果以[本批进度](../artifacts/audio-pressure-expansion/progress.json)为准，没有新增逐面浏览器、全量历史或实物验收。字体/颜色、隐藏安装和配准限制见各单品研究。私表、私有链接/原稿名、矢量、官图CAD原件、生成器和中间件只留仓库外，公开最终普通PNG及安全配准/来源。


## Accel / OP90 / OP180 同批印刷

本批4张 `reference-redraw` PNG：Accel正背2张，OP90和OP180各背面1张。每张依据精确本款官图可辨文字和图形代码重绘，没有照片裁片、预览放大、相近型号套用或不可辨小字编造。真实传感封装、固定光电遮光壳/收发窗/引脚、PCB、Grove和独立胶贴基底保留，检测真空气槽不填平，印刷不遮缺件。90/180不代表可动角，不造铰链、可见IR或虚拟检测锥。

`artwork:false`保持两入口全部物理attributes/index与世界矩阵。必要专项 `node scripts/check-accel-opto-units.mjs`、[本批指南](ACCEL-OP90-OP180-UNITS.md)登记三款四芯线和被动锚点；综合结果以[本批进度](../artifacts/accel-op90-op180-expansion/progress.json)为准，没有新增逐面浏览器、全量历史或实物验收。三款均无按钮、关节、灯或显示；加速度、检测/遮挡/计数/电平、协议、电气和固件由外部实现。字体/颜色、隐藏安装和配准限制见单品研究。私表、私有链接/原稿名、矢量、官图CAD原件、生成器和中间件只留仓库外，公开最终普通PNG及安全配准/来源。


## ID / RF433R / RF433T 同批印刷

本批6张 `reference-redraw` PNG：ID、RF433R、RF433T每款正背各1张。每张依据精确本款官图可辨文字和图形代码重绘，没有照片裁片、预览放大、收发型号互借或不可辨小字编造。真实芯片封装/引脚、PCB、固定内置铜天线、Grove深腔/四触点和独立胶贴基底均有实体，不用印刷遮缺件。R/T共用外壳依各自CAD核源，不代表共用电子封装或印刷；天线不发光、不动，不造外接天线或观察窗。

`artwork:false`保持两入口全部物理attributes/index与世界矩阵。必要专项 `node scripts/check-id-rf433-units.mjs`、[本批指南](ID-RF433-UNITS.md)登记三款四芯线和grove-only实际API；综合结果以[本批进度](../artifacts/id-rf433-expansion/progress.json)为准，没有新增逐面浏览器、全量历史或实物验收。三款均无sensor、按钮、关节、灯或显示；身份/密钥/证书/加密/I2C与RF/ASK/数据/强度/距离/通信、协议、电气和固件由外部实现。字体/颜色、隐藏安装和配准限制见单品研究。私表、私有链接/原稿名、矢量、官图CAD原件、生成器和中间件只留仓库外，公开最终普通PNG及安全配准/来源。

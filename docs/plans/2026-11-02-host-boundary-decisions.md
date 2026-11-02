# 2026-11-02 剩余主机边界决策（AtomS3R-Ext / 3 个组合件 / StickV）

状态：**最终边界决策**（`implemented` / `composition-only` / `boundary-only`）。
范围：`atoms3r-ext`、`atoms3r-ai-chatbot`、`atoms3r-cam-ai-chatbot`、
`atoms3r-m12-volcengine-kit`、`stickv` 五款当前“仅视觉、无运行登记”的主机。
本决策只登记边界，不改设备目录、QEMU 机器、profile、matrix 或测试；结论以
当前 main（`3030576e`，32 台已登记设备）与 2026-11-02 实际检索到的官方清单为准。

## 决策总表

| 对象 | SKU | 硬件构成 | 是否有“准确该板”固件 | 决策 |
| --- | --- | --- | --- | --- |
| AtomS3R-Ext | C126-Ext | 单 SKU 控制器：ESP32-S3-PICO-1-N8R8 + 8MB Flash/PSRAM + 9 轴 + IR + 顶部 Proto 扩展板；**无屏** | 否 | **boundary-only** |
| AtomS3R-AI Chatbot | K147 | 组合件：1 × AtomS3R（C126）+ 1 × Atomic Voice Base（A149） | 否（只有控制器+底座的官方应用固件，无套件 host 构建） | **composition-only** |
| AtomS3R-CAM AI Chatbot | K147-CAM | 组合件：1 × AtomS3R-CAM（C126-CAM）+ 1 × Atomic Voice Base（A149） | 否（同上） | **composition-only** |
| AtomS3R-M12 Volcengine Kit | D062-M12 | 组合件：1 × AtomS3R-M12（C126-M12）+ 1 × Atomic Voice Base（A149） | 否（只有 M12+底座的应用/测试固件；M12 控制器本体已用共享官方镜像接入） | **composition-only** |
| StickV | K027 | K210（RV64GC + KPU + OV7740）；非 ESP32 | 否（K210/MaixPy 生态，M5Burner/UIFlow2 无任何条目） | **boundary-only** |

五款**全部保持 visual-only**；本决策不产生新的 host 设备、machine 或 alias。

## 判定口径

- **准确该板固件**：官方构建或官方固件条目明确以该 SKU/硬件组合为目标，
  例如 M5Burner「UIFlow2.0 AtomS3R-CAM」条目描述明确写
  `UIFlow2 for AtomS3R-CAM and AtomS3R-M12`，因此 M12 控制器本体可按该共享
  官方镜像接入（main 已有 `atoms3r-m12` + `m5atoms3rm12`）。仅有“同 SoC/同名
  系列”或“社区固件”不算准确该板固件。
- **implemented**：找到被忽略的准确该板固件，可登记为独立 host 并走同 guest
  参考固件路径。本轮五款均未发现。
- **composition-only**：套件 = 已接入控制器 host + 已建模/可建模底座（A149）；
  不登记独立 host alias，按组合件复用既有 host + base 数据面验证；套件级
  AI/云应用固件只是运行在控制器上的应用，不构成新 host 身份。
- **boundary-only**：无准确该板固件，且不是“已接入 host + 已建模底座”的组合；
  保持 visual-only，不做 ESP32 alias；后续仅在出现官方板级构建/固件时重开。

检索渠道（均于 `2026-11-02` 实际请求）：

1. M5Burner API：`GET https://burner.m5stack.com/api/v1/devices`；
   `GET /api/v1/firmwares?keyword=…`；`GET /api/v1/firmwares?deviceId=…`；
   `GET /api/v1/firmwares/{id}`、`/versions`。
2. 官方 GitHub：`m5stack/uiflow-micropython` 的 Releases API（`2.5.4`、`2.5.3`）
   与 `m5stack/boards` 目录、`m5stack/cmodules/m5unified/m5unified.c` 板级映射。
3. M5Unified 板级枚举（Ext/Voice 等检测能力，仅辅助判断是否存在板级 profile）。
4. 官方产品文档、套件教程与底座文档（`docs.m5stack.com`）。
5. 本仓库已实现机器/补丁/证据（`patches/`、`devices/`、`docs/evidence/`）与
   main 上的 `m5atoms3r`、`m5atoms3rcam`、`m5atoms3rm12`、`m5atomvoices3r`。

## 通用检索结果

### M5Burner（54 个 device，`2026-11-02`）

- 设备清单中**没有** `STICKV`、`STICKV_*`、`EXT`、`M12`、`ATOMS3R_EXT`、
  Chatbot/Volcengine Kit、Voice Base 相关 device code；与 AtomS3R 相关的设备只有
  `ATOMS3R`（deviceId `2093000000000000011`，15 条固件）与 `ATOM_S3`
  （`1985000000000000204`，58 条固件）。
- 关键词检索结果（`/api/v1/firmwares?keyword=…`，`pageSize=30`）：

  | 关键词 | total | 命中与五款相关？ |
  | --- | --- | --- |
  | `AtomS3R-Ext` | 0 | 否 |
  | `Ext Board` | 0 | 否 |
  | `K147` / `K147-CAM` / `D062` | 0 / 0 / 0 | 否 |
  | `Voice Base` / `A149` | 0 / 0 | 否 |
  | `StickV` / `K210` / `Maix` | 0 / 0 / 0 | 否 |
  | `Chatbot` | 7 | 否（Cardputer/Core2/Tab5 等无关应用） |
  | `M12` | 4 | 都是控制器应用/共享镜像，见下 |
  | `AtomS3R` | 29 | 控制器固件，无 Ext/套件条目 |

- `ATOMS3R` 的 15 条固件中官方条目为：`UIFlow2.0 AtomS3R`（`1897200000000001772`，
  v2.5.4）、`XiaoZhi Voice Assistant For AtomS3R`（`1897200000000002559`，
  v2.2.6-AtomS3）、`OpenAI Voice Assistant For AtomS3R`（`1897200000000000358`，
  v1.0）、`AtomS3R小聆语音助手`（`1897200000000000486`，v1.8.4）、
  `Echo Pyramid 小智语音助手`（`1897200000000002892`）、`AtomS3R User Demo`
  （`1897200000000001680`）；**没有 Ext 专属条目**。
- `ATOM_S3` 的 58 条中与本决策相关：`UIFlow2.0 AtomS3R-CAM`
  （`1897200000000003117`，v2.5.4，描述明确覆盖 CAM 与 M12）、
  `XiaoZhi Voice Assistant For AtomS3R-CAM/M12`（`1897200000000002138`，
  v2.2.2）、`AtomS3R-M12火山引擎语音助手`（`1897200000000002766`，v1.0-beta）、
  `AtomS3R-CAM M12 User Demo`（`1897200000000000208`，v0.1）。
  这些条目全部以 `ATOM_S3` 控制器族标记，没有 K147/K147-CAM/D062 kit 设备码。
- M5Burner 版本接口不公开文件哈希（只有 `binFileName`/版本号），本决策未下载
  应用固件，因此不声明其二进制 SHA；需要 SHA 时必须在未来集成任务中单独下载
  并记录。

### 官方 GitHub release（`m5stack/uiflow-micropython`）

- `2.5.4`（`https://github.com/m5stack/uiflow-micropython/releases/tag/2.5.4`）
  共 **57** 个 asset；其中 `esp32s3-spiram-8mb` 只有 9 个：
  `atoms3r`、`atoms3r_cam`、`atom_echos3r`、`papers3`、`powerhub`、
  `stamps3bat`、`stamps3mini`、`sticks3`、`xiao-s3`。
  **没有** ext / m12 / chatbot / voice-base / kit 命名的 asset；`2.5.3`（49 个
  asset）同样没有。AtomS3R-M12 只通过 `atoms3r_cam` 共享镜像 + M5Burner 条目
  描述覆盖（该共享镜像 SHA-256 `1b29cc3d…`，见证据附录）。
- 上游 `m5stack/boards` 共 **56** 个 board 目录，Atom 系列只有
  `M5STACK_AtomS3`、`AtomS3R`、`AtomS3R_CAM`、`AtomS3U`、`AtomS3_Lite`、
  `AtomU`、`Atom_Echo`、`Atom_EchoS3R`、`Atom_Lite`、`Atom_Matrix`；
  **没有** `M5STACK_AtomS3R_Ext`、`M5STACK_AtomS3R_M12` 或任何 K147/D062 kit
  board 目录。
- 上游 `m5stack/cmodules/m5unified/m5unified.c` 的 board 映射只暴露实际有
  UIFlow2 构建的板：`M5AtomS3`=11、`M5AtomS3R`=18、`M5AtomS3R_CAM`=144、
  `M5AtomEchoS3R`=145、`M5AtomU`=130 等；其中**没有** Ext/M12/chatbot/kit
  身份（M12 通过 CAM 构建返回 144 族身份；Ext 无任何构建）。
- `M5Unified.hpp` 有 `board_M5AtomS3RExt`、`board_M5AtomVoiceS3R` 的运行时
  **检测/配置**分支，但那只是库对硬件的识别能力，不等于存在 Ext/kit 的官方
  固件构建；不能据此把 Ext 当成已接入 host。

## 逐款决策

### 1) AtomS3R-Ext（C126-Ext，`atoms3r-ext`）— boundary-only

**硬件构成与差异**：官方文档（`https://docs.m5stack.com/en/core/AtomS3R-Ext`）
描述为基于 ESP32-S3-PICO-1-N8R8 的可编程控制器，8MB Flash + 8MB PSRAM、
BMI270+BMM150 九轴、IR 发射、顶部通用扩展板（FPC 连接，5×6@2.54mm 用户焊接区，
Proto 保留 G3/G4/G9/G10/G11/G12/G13/G14/G17/G21/G40/G42/G46/G48）、
HY2.0-4P、24.0×24.0×12.0mm、7.0g；**规格、Features、PinMap 均无 TFT/显示项**
（对照 AtomS3R 明确写 `0.85-inch LCD`、GC9107 128×128）；开发平台只列
Arduino IDE / ESP-IDF / PlatformIO，页面 Tutorial 与 Development Platform
**未列 UiFlow2**（UiFlow2 只出现在全站导航）。Includes 只有 `1 x AtomS3R-Ext`，
不是“AtomS3R + 扩展板”两个独立 SKU 的组合件。

**固件检索结果**：M5Burner 无 Ext device、`ATOMS3R` 15 条固件无 Ext 条目、
`AtomS3R-Ext`/`Ext Board` 关键词 0；GitHub `2.5.4`/`2.5.3` release 无 ext asset；
上游 boards 无 Ext board 目录、`m5unified.c` board 映射无 Ext；UIFlow2 只有
AtomS3R 构建（该构建的板级 identity 为 18，且 QEMU `m5atoms3r` 机器包含
Ext 上不存在的 GC9107 面板）。因此**不存在准确该板固件**。

**可复用机器**：`m5atoms3r`（已实现，reference-ready）可用于同控制器参考，
但它建模 0.85 英寸 GC9107 面板与 AtomS3R 身份；Ext 无屏、无 Ext 身份，
不能把 AtomS3R 的结果/固件冒充 Ext，也不能登记为独立 alias。

**最小接入工作（若未来重开）**：等待官方发布 Ext board 构建/固件，或走经审查的
generic-firmware 路径并先确认 Arduino/ESP-IDF 镜像的板级 profile；QEMU 侧可能
需要去掉面板的 Ext 机器变体与对应板级识别探针。当前没有可验证 guest 路径，
不投入 QEMU/矩阵。

**风险**：AtomS3R UIFlow2 固件可能能启动（同 SoC、无屏只是缺显示初始化），
但 board id/检测与板级 profile 不准确，不能作为 C126-Ext 的 PASS；也禁止用
“同芯片”推断真实硬件一致性。

**决策：boundary-only**（保持 visual-only；无机器/profile/矩阵/设备登记）。

### 2) AtomS3R-AI Chatbot（K147，`atoms3r-ai-chatbot`）— composition-only

**硬件构成**：官方页（`https://docs.m5stack.com/en/core/AtomS3R-AI_Chatbot`）
Includes 明确 `1 x AtomS3R + 1 x Atomic Voice Base`；控制器 AtomS3R 的 0.85"
GC9107、九轴、IR，底座 A149 为 ES8311 + MEMS 麦克风 + NS4150B + 1W@8Ω 扬声器
（`https://docs.m5stack.com/en/atom/Atomic_Voice_Base`）。套件不是独立硅片
组合，没有新的 host SoC。

**固件检索结果**：M5Burner 无 K147 设备码/固件（`K147`=0）；官方条目都是
**控制器 + 底座**的应用固件，标签 `ATOMS3R`，描述明确写
“AtomS3R + Atomic Echo Base”组合（XiaoZhi `1897200000000002559`、
OpenAI `1897200000000000358`、小聆 `1897200000000000486`；另有
`Echo Pyramid 小智语音助手` `1897200000000002892` 的硬件是 AtomS3R + Echo
Pyramid，不属于本套件）；GitHub uiflow release 只有 `atoms3r` host UIFlow2，
没有 K147 asset；上游 boards 无 K147 目录。教程
`https://docs.m5stack.com/en/guide/atomic_voice_base/xiaozhi_voice_assistant`
明确“AtomS3 series devices + Atomic Voice Base hardware combination”并按
AtomS3 设备类型刷控制器应用固件。**未发现被忽略的 K147 独立官方固件。**

**可复用数据面**：host `m5atoms3r`（reference-ready，display/input/IMU/RGB/IR/
WiFi/BLE 证据）；底座 A149 与 `m5atomvoices3r`（C126-ECHO）同族：`0111` 补丁
注释记录 ES8311@0x18 在 SYS I2C（SDA G45/SCL G0）、NS4150B 使能 GPIO18、
IR G47、GPIO41 按键、Grove G2/G1（`patches/qemu-m5stack-peripherals/0111-atom-voices3r-board.patch:6-9,30-45`）；
`docs/evidence/2026-11-02-atom-echos3r-host/summary.json` 已给出该机器的
Speaker.begin/tone + I2S1 DMA 非静音 PCM（固件 SHA `9348083a…`），
但**麦克风、IR、NS4150B 声学仍未验证**。组合件可复用 host + base 的既有
证据，不需要也不允许新增独立 host alias。

**最小接入工作**：登记层面零工作（保持 visual-only）；若要做套件级交互验证，
按“m5atoms3r guest + A149 base 模型 + 官方应用固件”的**组合件 case** 另行
立项（应用固件/云服务属于应用层，不是 host 身份）。

**风险**：云端账号/服务（XiaoZhi/OpenAI）不可在本仓库锁定；ES8311 麦克风
通路与 NS4150B 声学未验证；套件机械装配、底座固件版本差异；套件应用固件
不是 UIFlow2 host 构建，不能产生独立设备 PASS。

**决策：composition-only**。

### 3) AtomS3R-CAM AI Chatbot（K147-CAM，`atoms3r-cam-ai-chatbot`）— composition-only

**硬件构成**：官方页（`https://docs.m5stack.com/en/core/AtomS3R-CAM_AI_Chatbot`）
Includes `1 x AtomS3R-CAM + 1 x Atomic Voice Base`；控制器带 GC0308 0.3MP 相机、
九轴、IR，底座 A149 同上。

**固件检索结果**：M5Burner 无 K147-CAM 设备码/固件（`K147-CAM`=0）；
`ATOM_S3` 下的 XiaoZhi CAM/M12 应用固件（`1897200000000002138`，v2.2.2）标签为
`ATOM_S3`，教程明确支持 AtomS3R-CAM/M12 控制器 + Voice Base 组合；GitHub
uiflow release 只有 `atoms3r_cam` host UIFlow2（无 kit asset）；上游 boards 无
K147-CAM board。**未发现被忽略的 K147-CAM 独立官方固件。**

**可复用数据面**：host `m5atoms3rcam`（candidate：启动、板级 id 144、128×128
GC9107、原厂 camera.init()/capture() 多分辨率整帧，证据
`docs/evidence/2026-11-02-atoms3r-cam-geometry/summary.json`，共享官方镜像 SHA
`1b29cc3d…`）+ A149 base（同第 2 款）；两条数据面都已分别存在，组合件只需要
组合验证，不需要新 host。

**最小接入工作**：零登记工作；套件级验证另按组合件 case（CAM host + base）
立项。**风险**：camera+audio 同时工作的资源/时序未组合验证；麦克风/声学、
云端应用与机械件同前。

**决策：composition-only**。

### 4) AtomS3R-M12 Volcengine Kit（D062-M12，`atoms3r-m12-volcengine-kit`）— composition-only

**硬件构成**：官方页（`https://docs.m5stack.com/en/core/AtomS3R-M12_Volcengine_Kit`）
Includes `1 x AtomS3R-M12 + 1 x Atomic Voice Base`；M12 为 OV3660 3MP 相机 +
九轴 + IR 控制器，底座 A149 同上；套件定位 Volcengine 云 AIGC 视觉+语音。

**固件检索结果**：M5Burner 无 D062 设备码（`D062`=0）；官方套件固件条目是
`AtomS3R-M12火山引擎语音助手`（`1897200000000002766`，v1.0-beta，标签
`ATOM_S3`，描述明确“AtomS3R-M12 火山引擎语音视觉套件测试固件：本固件仅供
测试使用……需手机 2.4GHz 热点 SSID M5VolcRTC / 密码 m5volcrtc”）；这是
**套件应用/测试固件**（依赖云与手机热点），不是独立 host 固件；M12 控制器
本体的准确官方固件是 M5Burner「UIFlow2.0 AtomS3R-CAM」条目
（`1897200000000003117`，描述明确覆盖 AtomS3R-CAM 与 AtomS3R-M12），main 的
`atoms3r-m12` 已按该共享镜像接入（证据
`docs/evidence/2026-11-02-atoms3r-m12-host/summary.json`，同一镜像 SHA
`1b29cc3d…`）。GitHub release 无 D062/M12 asset；上游无 M12 board 目录。
**未发现被忽略的 D062-M12 独立 host 固件。**

**可复用数据面**：host `m5atoms3rm12`（candidate：启动、GC9107、OV3660 SCCB、
多分辨率确定性 DVP 帧流）+ A149 base（同第 2 款）。Volcengine 应用固件/云端
链路属于应用层，本任务不接入、不验证。

**最小接入工作**：零登记工作；若未来做套件级验证，按“m5atoms3rm12 + A149”
组合件立项，并单独评估 Volcengine RTC/云依赖（当前 QEMU 网络 route 不覆盖
厂商云协议）。**风险**：v1.0-beta 测试固件与云账号不可复现；Volcengine
实时流未验证；mic/声学同前；套件机械件。

**决策：composition-only**。

> 文档注：`docs/plans/2026-11-02-remaining-visual-hosts-and-units.md` 的
> AtomS3R-M12 行（第 26 行）仍写“否（社区…）”已过时——main 已有
> `atoms3r-m12` + `m5atoms3rm12` 与证据；该行不在本任务允许修改的 5 行内，
> 留给后续文档同步任务修正。

### 5) StickV（K027，`stickv`）— boundary-only

**硬件构成**：官方页（`https://docs.m5stack.com/en/core/StickV`）明确为
Kendryte K210（双核 64-bit RISC-V RV64GC @400MHz + 0.8Tops KPU + FPIOA）、
OV7740 相机、MicroPython 支持、开发平台 PlatformIO；**不是 ESP32**，也不在
UIFlow2/M5Burner 的 ESP32 固件族。

**固件检索结果**：M5Burner 54 个 device 无 StickV/K210；关键词
`StickV`/`K210`/`Maix` 均 0；uiflow-micropython release（`2.5.4`/`2.5.3`）
无 StickV/K210 asset；上游 boards 无 StickV board。官方文档的 StickV 开发路径是
MaixPy（`https://docs.m5stack.com/en/guide/stickv/maixpy`），运行时属于
Sipeed MaixPy/K210 生态（`https://github.com/sipeed/MaixPy`），不是 M5Stack
ESP32 固件；本仓库现有 QEMU xtensa/esp-emu 后端不适用。

**可复用机器**：无（QEMU `xtensa-softmmu` 与 esp-emu 均不覆盖 K210/RV64）。
**最小接入工作**：只可能在独立 K210 后端项目中立项；当前不登记任何 ESP32
alias、machine 或 profile。**风险**：若未来做 K210 后端，需重新评估工具链、
MaixPy 固件、KPU/相机/显示数据面与仓库后端架构，工作量与 ESP32 主机不在
同一量级。

**决策：boundary-only**。

## 对登记/文档的影响

- 五款继续留在 `platform/web/vendor/m5stack-models/vendor-manifest.json` 的
  `visual_only_controllers`；不新增 `devices/`、`platform/qemu/profiles.json`、
  `platform/peripherals/catalog.json`、matrix case 或测试计数。
- `composition-only` 的验证入口固定为“已实现 host + A149 base”的组合件 case，
  不得为套件创建独立 device alias 或伪造 host 身份；`boundary-only` 的验证
  入口为空，除非出现新的官方板级固件。
- `docs/plans/2026-11-02-remaining-visual-hosts-and-units.md` 中五款对应行的
  “当前边界与决策”列已按 `implemented` / `composition-only` / `boundary-only`
  标注。

## 遗留风险与重开条件

- **重开条件（Ext）**：M5Burner 出现 Ext device/固件、上游出现
  `M5STACK_AtomS3R_Ext` board 构建或官方 release 出现 ext asset；或经审查的
  generic-firmware 路径提供准确板级 profile。
- **重开条件（3 个组合件）**：M5Stack 若发布套件专属 host 构建（非应用固件）
  或 M5Burner 新增 kit device 码；否则永远按组合件处理。组合件级验证还依赖
  A149 base 的 ES8311 麦克风通路与 NS4150B 声学（当前 `partial/planned`）。
- **重开条件（StickV）**：仅当仓库决定启动独立 K210 后端评估。
- 五款均未做真机、电气、声学、机械或云服务验证；官方应用固件的二进制 SHA
  未取得（M5Burner 不公开哈希，且本决策未下载），不得在对外材料中声称。
- 本文档不改变 `docs/project-snapshot.md`；新增计划文档会造成快照里的文档
  行数统计漂移，快照更新不在本任务的两个文件提交范围内。

## 证据附录

### A. 官方 release / board 清单

- UIFlow2 release `2.5.4`：`https://github.com/m5stack/uiflow-micropython/releases/tag/2.5.4`
  （57 assets；esp32s3-spiram-8mb 仅 9 个：atoms3r、atoms3r_cam、atom_echos3r、
  papers3、powerhub、stamps3bat、stamps3mini、sticks3、xiao-s3）。
- 上游 board 目录：`https://github.com/m5stack/uiflow-micropython/tree/master/m5stack/boards`
  （56 个 board 目录；无 Ext/M12/kit）。
- UIFlow2 board 身份映射：
  `https://raw.githubusercontent.com/m5stack/uiflow-micropython/master/m5stack/cmodules/m5unified/m5unified.c`
  第 14-82 行（`M5AtomS3R`=18、`M5AtomS3R_CAM`=144、`M5AtomEchoS3R`=145，
  无 Ext/M12/kit）。
- M5Unified 检测枚举：`https://github.com/m5stack/M5Unified/blob/master/src/M5Unified.hpp:399-400,418`
  `board_M5AtomS3RExt`/`board_M5AtomVoiceS3R`（仅检测/配置分支，非固件；
  其中 Ext 在 `:400`、Voice 在 `:418`）。

### B. M5Burner 条目（`2026-11-02` 查询）

| firmwareId | 名称 | 版本 | 标签 | 与决策关系 |
| --- | --- | --- | --- | --- |
| `1897200000000001772` | UIFlow2.0 AtomS3R | v2.5.4 | `ATOMS3R` | AtomS3R host 官方 UIFlow2（无 Ext） |
| `1897200000000003117` | UIFlow2.0 AtomS3R-CAM | v2.5.4 | `ATOM_S3` | 描述明确覆盖 CAM+M12；M12 host 共享镜像 |
| `1897200000000002559` | XiaoZhi Voice Assistant For AtomS3R | v2.2.6-AtomS3 | `ATOMS3R` | 控制器+底座应用固件（K147 组合） |
| `1897200000000000358` | OpenAI Voice Assistant For AtomS3R | v1.0 | `ATOMS3R` | 控制器+底座应用固件（K147 组合） |
| `1897200000000000486` | AtomS3R小聆语音助手 | v1.8.4 | `ATOMS3R` | 控制器+底座应用固件（K147 组合） |
| `1897200000000002138` | XiaoZhi Voice Assistant For AtomS3R-CAM/M12 | v2.2.2 | `ATOM_S3` | CAM/M12 控制器应用固件（K147-CAM/D062 组合） |
| `1897200000000002766` | AtomS3R-M12火山引擎语音助手 | v1.0-beta | `ATOM_S3` | D062-M12 套件应用/测试固件（云+热点） |
| `1897200000000000208` | AtomS3R-CAM M12 User Demo | v0.1 | `ATOM_S3` | M12 默认 user demo（应用） |

查询端点：`https://burner.m5stack.com/api/v1/devices`、
`https://burner.m5stack.com/api/v1/firmwares?deviceId=2093000000000000011`
（ATOMS3R，15 条）、`...?deviceId=1985000000000000204`（ATOM_S3，58 条）、
`...?keyword=<…>`、`.../firmwares/{id}`、`.../firmwares/{id}/versions`。

### C. 官方产品/教程文档

- AtomS3R-Ext：`https://docs.m5stack.com/en/core/AtomS3R-Ext`（无 TFT/显示规格；
  Development Platform 仅 Arduino/ESP-IDF/PlatformIO；Includes 1 x AtomS3R-Ext）。
- AtomS3R：`https://docs.m5stack.com/en/core/AtomS3R`（0.85 英寸 LCD、
  UiFlow2 教程）。
- K147：`https://docs.m5stack.com/en/core/AtomS3R-AI_Chatbot`（Includes
  `1 x AtomS3R + 1 x Atomic Voice Base`）。
- K147-CAM：`https://docs.m5stack.com/en/core/AtomS3R-CAM_AI_Chatbot`
  （Includes `1 x AtomS3R-CAM + 1 x Atomic Voice Base`）。
- D062-M12：`https://docs.m5stack.com/en/core/AtomS3R-M12_Volcengine_Kit`
  （Includes `1 x AtomS3R-M12 + 1 x Atomic Voice Base`）。
- A149：`https://docs.m5stack.com/en/atom/Atomic_Voice_Base`（ES8311 +
  MSM381A3729H9BPC MEMS mic + NS4150B + 1W@8Ω；Base 无 SoC）。
- 组合件教程：`https://docs.m5stack.com/en/guide/atom_s3r/xiaoling_voice_assistant`、
  `.../guide/atomic_voice_base/xiaozhi_voice_assistant`、
  `.../guide/atomic_voice_base/openai_voice_assistant`、
  `.../guide/atomic_voice_base/volcengine_voice_assistant`、
  `.../arduino/projects/atomic/atomic_echo_base`（A149 Arduino/RecordPlay，
  “AtomS3 series devices + Atomic Voice Base”）。
- StickV：`https://docs.m5stack.com/en/core/StickV`（K210/RV64GC/KPU/OV7740/
  MicroPython/PlatformIO）、`https://docs.m5stack.com/en/guide/stickv/maixpy`；
  MaixPy 上游：`https://github.com/sipeed/MaixPy`。

### D. 仓库内可复用证据（file:line）

- `patches/qemu-m5stack-peripherals/README.md:13`：`0111-atom-voices3r-board.patch`
  的 Atom VoiceS3R 机器；同文件 `:14` 为 `0112-atoms3r-cam-board.patch`、
  `:29` 为 `0122-atoms3r-m12-board.patch`。
- `patches/qemu-m5stack-peripherals/0111-atom-voices3r-board.patch:6-9` 与
  `:30-45`：C126-ECHO/Atomic Voice Base 的 ES8311@0x18（SYS I2C，SDA G45/SCL G0）、
  NS4150B 使能 GPIO18、IR GPIO47、GPIO41 按键、Grove G2/G1；注释明确
  NS4150B/IR 未做声学/板级模型。
- `platform/peripherals/catalog.json`：`atom-echos3r` 组件
  `audio-codec es8311 @0x18`、`speaker ns4150b GPIO18`、`ir GPIO47`、
  `microphone es8311`（planned）。
- `devices/esp32-s3/atoms3r/device.json`：runtime `reference-ready`，
  display/input/IMU/RGB/IR/WiFi/BLE 证据。
- `devices/esp32-s3/atoms3r-cam/device.json` 与
  `docs/evidence/2026-11-02-atoms3r-cam-geometry/summary.json`：共享官方镜像
  SHA-256 `1b29cc3d…`、8,384,512 B，camera queue 多分辨率整帧。
- `devices/esp32-s3/atoms3r-m12/device.json` 与
  `docs/evidence/2026-11-02-atoms3r-m12-host/summary.json`：`m5atoms3rm12`、
  OV3660 SCCB/DVP、同一共享官方镜像 SHA-256 `1b29cc3d…`；
  M5Burner 条目 `1897200000000003117` 描述明确覆盖 M12。
- `docs/evidence/2026-11-02-atom-echos3r-host/summary.json`：C126-ECHO
  （AtomS3R + Voice Base 同族硬件）固件 SHA-256 `9348083a…`、board id 145、
  Speaker/I2S1 非静音 PCM；mic/IR/声学未验证。
- `docs/plans/2026-11-02-remaining-visual-hosts-and-units.md:27-30,33`：本决策
  更新的五款行（Ext/K147/K147-CAM/D062/StickV；M12 第 26 行已过时、
  M5Stick 第 31 行亦已由 main 接入，均不在本任务修改范围）。

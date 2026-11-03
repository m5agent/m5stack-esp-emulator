# 剩余仅视觉主机与 Unit 接入计划

日期：`2026-11-02`。范围：`docs/project-snapshot.md` 与视觉库存中“有外壳、
无运行登记”的剩余主机，以及未登记的 Unit。动态计数以自动快照为准；本页只
维护逐型号的接入事实、所需模型和边界取舍。

> **历史计划页**：正文的逐型号表格与 Unit 缺口记录保留 2026-11-02/03 接入
> 过程时点；最终收口状态见页尾“最终状态（2026-11-03 收口）”：**9 host 接入
> + 5 边界决策**、视觉库存 38=33 登记+5 仅视觉、Unit **160=158 implemented
> +2 DEFER**、25 c 类边界、canonical **41 层**、PR #80–#161。当前能力以
> [项目状态](../project-status.md)与[战役汇总](../evidence/2026-11-03-visual-campaign-summary/README.md)
> 为准。

## 已完成批次

| 批次 | 设备 | 结论 |
| --- | --- | --- |
| 1 | AtomS3U（`atoms3u`） | 官方 UIFlow2 v2.5.4 启动、GPIO41 按键、GPIO35 WS2812 RMT；PR #80 |
| 2 | Atom VoiceS3R（`atom-echos3r`） | 官方 UIFlow2 v2.5.4 启动、128×128 面板、Speaker/I2S1 DMA 非静音 PCM；PR #80 |
| 3 | AtomS3R-CAM（`atoms3r-cam`） | 启动、板级识别 144、显示初始化、软件 SCCB 修复后官方 `camera.init()/capture()` 取得 320×240 RGB565 整帧；PR #81 已合入，相机补丁 0115 |
| 4 | Basic v2.7（`basic-v27`） | 官方 UIFlow2 v2.5.4-4MB 启动、板级识别 1、ILI9342C 320×240、QMP 注入 A/B/C、IP5306 `0x75` 寄存器模型与 I2S0 DAC 非静音 PCM；PMIC 电芯/电气、microSD、电源键、背光和 Grove Unit 仍未覆盖 |
| 5 | AtomU（`atomu`） | 官方 UIFlow2 v2.5.4 启动、板级识别 130、GPIO27 SK6812 RMT（QOM 0x204060）、QMP 注入 GPIO39 按键回读与 Grove G26/G32 I2C 控制器扫描；SPM1423 PDM 麦克风、IR 与 Grove Unit 仍未覆盖；固件为固定 SHA 官方 GitHub release 资产（非 M5Burner ID） |
| 6 | Atom Echo（`atom-echo`） | 官方 UIFlow2 v2.5.4 启动、板级识别 142、SK6812 RMT、QMP 按键回读、Grove I2C 扫描、NS4168 I2S1 非静音 PCM 与 SPM1423 PDM RX 注入路径；官方 C008-C 无 ES8311/I2C codec；模拟声学/IR/Grove Unit 仍未覆盖；固件为固定 SHA 官方 GitHub release 资产 |

## 剩余仅视觉主机（历史时点：Atom Echo 接入后 8 款；最终 5 款仅视觉）

固件可用性按 `burner.m5stack.com` 公开列表核对（`2026-11-02`）。只有
“官方 UIFlow2 可用”才走同 guest 参考固件路径；“仅 UIFlow1/社区固件”必须
先在计划中确认镜像格式、板级 profile 和探针，再接入。

| 设备 | SKU | 芯片 | 官方 UIFlow2 | 所需板级/模型工作 | 当前边界与决策 |
| --- | --- | --- | --- | --- | --- |
| AtomS3R-M12 | C126-M12 | ESP32-S3-PICO-1-N8R8 | 否（社区 `AtomS3R-CAM M12 User Demo`、`XiaoZhi` 等） | OV3660 SCCB/DVP 模型；复用 `m5atoms3rcam` 骨架 | 等 camera SCCB/DVP 数据面闭环后再接；不能用 AtomS3R 固件冒充 M12 |
| AtomS3R-Ext | C126-Ext | ESP32-S3-PICO-1-N8R8 | 否 | 与 AtomS3R 同控制器 + 用户键 G41 + IR G47 + Proto 排针 | **boundary-only**（2026-11-02 决策）：M5Burner/GitHub release/UIFlow2 build 均无 Ext 专属固件或 board profile；Ext 无屏 + Proto 扩展板，与 AtomS3R 板级 profile 不同；保持 visual-only，不继承 AtomS3R。详见 [host-boundary-decisions](2026-11-02-host-boundary-decisions.md) |
| AtomS3R-AI Chatbot | K147 | ESP32-S3-PICO-1-N8R8 | 否（套件使用控制器固件） | AtomS3R + Atomic Voice Base A149（ES8311）组合件 | **composition-only**（2026-11-02 决策）：AtomS3R（已接入）+ A149 组合件；M5Burner 官方 XiaoZhi/OpenAI/小聆固件均以控制器+底座组合投放（标签 `ATOMS3R`），无 K147 host alias；按组合件复用既有 host/base 证据验证。详见 [host-boundary-decisions](2026-11-02-host-boundary-decisions.md) |
| AtomS3R-CAM AI Chatbot | K147-CAM | ESP32-S3-PICO-1-N8R8 | 否 | AtomS3R-CAM + Voice Base 组合件 | **composition-only**（2026-11-02 决策）：AtomS3R-CAM（已接入，camera 数据面）+ A149；官方 XiaoZhi CAM/M12 等为控制器应用固件，无 K147-CAM host alias；组合件复用 host/base 验证。详见 [host-boundary-decisions](2026-11-02-host-boundary-decisions.md) |
| AtomS3R-M12 Volcengine Kit | D062-M12 | ESP32-S3-PICO-1-N8R8 | 否 | AtomS3R-M12 + Voice Base 组合件 | **composition-only**（2026-11-02 决策）：AtomS3R-M12（已接入，共享 UIFlow2 CAM-M12 描述覆盖的官方镜像）+ A149；官方 Volcengine 套件固件是应用/测试固件（v1.0-beta，需手机热点），不是独立 host；不新增 alias。详见 [host-boundary-decisions](2026-11-02-host-boundary-decisions.md) |
| M5Stick | K016 | ESP32（classic） | 否（通用 `UIFlow` UIFlow1） | SH1107 64×128 OLED、三键、MPU9250/无 IMU 两个修订 | 需先确定板修订；OLED 控制器模型是新工作 |
| StickT2 | K016-T2 | ESP32（classic） | 否（社区 `StickT2 User Demo`） | MLX90640 热成像、ST7789 135×240 | 依赖 thermal fixture 与该板 I2C 拓扑；按社区镜像单独验证 |
| StickV | K027 | K210（非 ESP32） | 否 | 不属于 ESP32 后端 | **boundary-only**（2026-11-02 决策）：K210 RISC-V/OV7740/MaixPy，非 ESP32；M5Burner/UIFlow2/GitHub release 无任何该板固件；保持 visual-only，K210 后端另行评估。详见 [host-boundary-decisions](2026-11-02-host-boundary-decisions.md) |

## Unit 缺口与方法

- 视觉库存 `184` 款 Unit：最终 catalog `160`（`159` 产品 + `servo8-hat`）
  = **158 implemented/partial + 2 DEFER**，另 25 款 c 类边界，184/184 覆盖；
  本段下方“34/150”是 2026-11-02 计划时点值，已由最终收口取代。
- 接入单位不是“注册一行 JSON”：每款要（1）固定官方协议/寄存器证据，
  （2）在 QEMU 内实现控制器级数据面，（3）提供 fixture 或输入注入，
  （4）用同 guest 的官方驱动探针拿到读写/事件证据，（5）在
  `runtime-coverage.json` 登记，不能靠视觉模型或 host 端假值。
- 建议批次（按可复用度排序，逐款以官方文档确认后实施）：
  1. 与已实现模型同族的 I2C 传感器/控制 Unit（复用 SHT30/QMP6988、
     GPIO/ADC、RMT 等既有数据面）；
  2. 单寄存器 I2C DAC/OLED 类；
  3. 需要新增控制器模型的距离/手势/热成像类；
  4. UART 类（GPS/语音/总线）与 SPI/摄像头类。
- 每一批次沿用本计划的主机侧证据模板：设备本地 probe、matrix case、
  `docs/evidence/<date>-<topic>/` 摘要与 SHA-256。

## 边界

- 本页是计划，不构成能力声明；任何 PASS 必须绑定固件 SHA、device、profile
  和可复现证据。
- 视觉库存里的“模型”和“装配组合件”不等于可独立运行的 host 或 Unit。

## 最终状态（2026-11-03 收口）

- 视觉主机：计划中的剩余主机已全部收口。**9 个独立 host** 已完成同 guest
  原厂固件路径接入（AtomS3U、Atom VoiceS3R、AtomS3R-CAM、AtomS3R-M12、
  AtomU、Atom Echo、Basic v2.7、M5Stick、M5StickT2；每款的范围/未覆盖项见
  [战役汇总](../evidence/2026-11-03-visual-campaign-summary/README.md)）。
  M5Stick 工厂固件路径仍 blocked/partial，只能按 evidence 的限定范围引用。
- 其余 5 项按最终边界决策处理：AtomS3R-Ext / StickV 为 **boundary-only**，
  AtomS3R-AI Chatbot / AtomS3R-CAM AI Chatbot / AtomS3R-M12 Volcengine Kit
  为 **composition-only**（复用已接入控制器 + Atomic Voice Base 数据面，
  不新增 host alias）。详见
  [host-boundary-decisions](2026-11-02-host-boundary-decisions.md)。
- 视觉库存 38 款主机中，33 台有运行登记；余 5 款仅视觉且全部有明确边界，
  不再作为“待接入”队列。
- Unit：原计划“150 款未登记”已收口为 catalog **160 条**（159 个产品 +
  servo8-hat）+ **25 款 c 类边界**，184/184 全覆盖；10 个研究批、对应
  实现/证据 PR #80-#146 与剩余 DEFER/BLOCKED 清单见
  [视觉与 Unit 战役汇总](../evidence/2026-11-03-visual-campaign-summary/README.md)。
- 本页不再是待办队列；后续若出现官方 Ext/kit 固件或新 Unit 驱动，按新任务
  重开，不自动继承既有 evidence。


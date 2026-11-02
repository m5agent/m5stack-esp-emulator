# 剩余 classic / 异构主机接入前可行性研究

日期：`2026-11-02`。范围：`docs/plans/2026-11-02-remaining-visual-hosts-and-units.md`
"剩余仅视觉主机"里的经典 ESP32 / 异构主机——
`atom-echo`（C008-C）、`atomu`（K117）、`m5stick`（K016）、`stickt2`（K016-T2），
以及 StickV（K027）的异构边界确认。

本页是**接入决策与证据清单**，不是能力声明：没有运行 QEMU、没有改
runtime/测试/设备目录，也没有物理硬件结论。所有"可以复用/必须新增"的判断
来自对照当前 QEMU 源码（`hw/xtensa/esp32.c`、`hw/m5stopwatch/*`）与仓库内已
验证的 classic 主机实现，属于代码级可行性，需按每款"最小实现步骤"重新取证。

## 结论总表

| 设备 | SKU | SoC | Flash | 屏幕 | 精确该板官方 UIFlow2 | 结论 | 建议批次 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AtomU | K117 | ESP32-PICO-D4 | 4 MB（推断，见下） | 无 | **有**：官方 2.5.4 构建 `uiflow-…-esp32-4mb-atomu-…bin` | **GO** | 第 5 批（最省） |
| Atom Echo / Atom Voice | C008-C | ESP32-PICO-D4 | 4 MB | 无 | **有**：官方 2.5.4 构建 `…-esp32-4mb-atomecho-…bin` | **GO** | 第 6 批 |
| M5Stick | K016 | ESP32-WROOM32 | 4 MB | SH1107 64×128 | 无（也无 UIFlow1） | **DEFER** | 第 7 批（条件） |
| StickT2 | K016-T2 | ESP32-PICO-D4 | 4 MB | ST7789 135×240 | 无 | **DEFER** | 第 8 批（条件） |
| StickV | K027 | K210（RISC-V） | — | 2.4″ 320×240 | 不适用 | **NO-GO**（ESP32 后端） | 独立后端评估 |

推荐顺序：**AtomU → Atom Echo → M5Stick → StickT2**；StickV 不进入 ESP32
执行队列。理由：AtomU/Atom Echo 只需新增 machine + 板级 glue，I2S/PDM、
RMT/WS2812、GPIO/ADC、Unit runtime 全部可复用；M5Stick 还缺 SH1107 与
MPU9250 两个模型，且没有 UIFlow1/UIFlow2 可走；StickT2 的 Lepton 3.0
热成像与 thermal fixture 是新课题。

## 与既有计划的差异（本页更正）

1. `2026-11-02-remaining-visual-hosts-and-units.md` 把 AtomU / Atom Echo 标为
   "官方 UIFlow2 否，仅 UIFlow1/社区"。实测：**上游官方仓库
   `m5stack/uiflow-micropython` 有独立板级 `M5STACK_AtomU`（BOARD_ID 130）与
   `M5STACK_Atom_Echo`（BOARD_ID 142）**，且官方 GitHub release `2.5.4` 直接
   发布两个精确板级镜像。公开 M5Burner API 目前**没有**对应条目（见"固件来源
   策略"），所以"没有 UIFlow2"只在"M5Burner 渠道"成立，不是事实本身。
2. 同页把 StickT2 写成"MLX90640 热成像"——**错误**。官方 StickT2 页面为
   **FLIR Lepton 3.0**（160×120，I2C + VoSPI）；MLX90640 是别的产品。
3. 同页把 M5Stick K016 的"通用 UIFlow UIFlow1"当可用参考。实测当前
   M5Burner 公开 API 无 K016 设备码/固件，官方 UIFlow1 教程也无 M5Stick 页；
   K016 目前只有官方 EasyLoader 安装包内嵌的 FactoryTest 镜像（见 3.1）。
4. 已登记设备 `stickc`（StickC）在 `devices/catalog.source.json` 使用了
   `"sku": "K016"`，但官方页面 StickC 为 **K016-C**、M5Stick 才是 **K016**。
   接入 `m5stick` 前必须先修这个 SKU 冲突（见 3.1 前置项），不能靠改名绕过。

## 方法与证据边界

- 抓取方式：`curl` 抓 `docs.m5stack.com` HTML 后本地正则/表格解析（该站点
  `web_fetch` 报非公网 IP）；M5Burner 公开 API
  `https://burner.m5stack.com/api/v1/devices`、`/api/v1/firmwares?keyword=`、
  `/api/v1/firmwares/<id>`、`/api/v1/firmwares/<id>/versions`；固件按
  `https://m5burner-cdn.m5stack.com/firmware/<binFileName>`（新式）或
  `https://m5burner-cdn.m5stack.com/community/1/<firmwareId>/<versionId>/bin/<versionId+1>.bin`
  （老式 UIFlow 镜像）下载；官方源码/镜像来自 `raw.githubusercontent.com` 与
  GitHub release；EasyLoader 为官方 OSS 安装包。
- 固件全部落在 `.work/classic-hosts/firmware/`（gitignored），本页只记
  SHA-256/大小/偏移；没有提交任何二进制。
- 镜像解析：bootloader 在 flash `0x1000`、分区表 `0x8000`、app 在 `0x10000`
  为 ESP32 classic 标准布局。所有镜像都为"整片/稀疏 merged 原始 Flash 内容"，
  文件头 `0x0` 为 `0xFF`，不是 app-only 段镜像（除单独说明的 GitHub app bin）。
- 分类口径：**官方 UIFlow2** / **官方 UIFlow1** / **官方工厂固件** /
  **社区镜像** 分开；只有"能证明该板"的固件才可当参考固件，同 SoC 或同系列
  （如 Atom Lite、StickC）不精确的镜像一律标注"不可替代"。
- 抓取/核对日期：`2026-11-02`（+08:00）。网页有改版/下架风险，复现前重抓。

## 1. AtomU（K117）— GO

### 1.1 官方硬件档案

来源：`https://docs.m5stack.com/en/core/AtomU` 与
`https://docs.m5stack.com/en/products/sku/K117`（两页内容一致，2026-11-02 抓取）。

| 项目 | 值 |
| --- | --- |
| SKU | K117 |
| SoC | ESP32-PICO-D4 @ Xtensa LX6 双核 240 MHz |
| SRAM | 520 KB |
| Flash | 官方规格表未列；`m5stack/uiflow-micropython` 板级用 `sdkconfig.flash_4mb`，ESP32-PICO-D4 封装内 4 MB ⇒ 4 MB（推断，需在下一轮用 app/分区实测确认） |
| 接口 | USB-A（FTDI VCP 驱动）、HY2.0-4P Grove ×1 |
| 其他 | SPM1423 PDM 麦克风、IR TX、SK6812 RGB LED、按键、无屏幕、无 PSRAM |

PinMap（官方表格原文）：

```
SPM1423 – PDM : ESP32-PICO-D4  G5(MIC_CLK)  G19(MIC_DATA)  3.3V  GND
IR & SK6812 & BUTTON : G12(IR TX)  G27(SK6812 DIN)  G39(BUTTON SW)
HY2.0-4P : GND / 5V / G26 / G32
```

### 1.2 固件可用性（均实际下载）

| 类别 | firmware_id / 版本 | 文件名 | 大小 | SHA-256 | 镜像布局 |
| --- | --- | --- | --- | --- | --- |
| 官方 UIFlow2 | GitHub release `2.5.4`（板 `M5STACK_AtomU`，BOARD_ID 130） | `uiflow-e437118-esp32-4mb-atomu-v2.5.4-20261030.bin` | 4,186,112 | `affa252d21f223bbe21cf1767604d345df97b2cb8dd62bc76993588d9bd9eda7` | bootloader `0x1000`、ptable `0x8000`、factory `0x10000/0x361000`、vfs `0x371000/0x8D000`；文件到 `0x3FE000`（最后 8 KiB 未写） |
| 官方 UIFlow1 | `1897200000000001759` v1.15.5 | `UIFlow-atom-v1.15.5-lite-0x0.bin` | 4,186,112 | `9144fda7e71fd000fdd7fb9fbdd4ef1b17a40ca8a00bb84f4189487edd22e2bf` | factory `0x10000/0x310000`、vfs `0x320000/0xDE000`、config `0x3FE000`、wifi `0x3FF000`；文件只到 `0x3FE000`，**M5Burner 在烧录时补写 config/wifi** |
| 官方 STT demo（UIFlow1 时代） | `1897200000000001281` v1.1-atomu-cn | `5ssbichxdkvmquv2qmzsrk86mhdzl0xq.bin` | 997,392 | `f799cce4096530c43d1582ec2c47330b27f6a48dac0d5907e178037d00d14b38` | 稀疏：bootloader+ptable+app0（`0x10000`），文件止于 app 结束 `0xF3810`；ptable 为 nvs/otadata/app0/app1/spiffs 双 OTA 布局 |
| 社区 | `1897200000000000024` v1.0 (ATOMU) | `AtomOS` | 4,194,304 | `4fd46ad6005b303cc8e51b00c5308153262d0e544050378ff0d1d2e0e025a2f5` | nvs `0x9000/24576`、phy_init `0xF000/4096`、factory `0x10000/0x350000`、vfs `0x360000/0x9E000`；整片 4 MB |

注意：当前 M5Burner 的 `UIFlow_AtomU` v1.15.5 是 `2026-11-02 09:59` 重新发布的
条目（`downloadCount=0`），其 `binFileName` 是老式命名、`/firmware/<name>` 路径
返回 404；上表字节是通过 version-scoped CDN 路径
`/community/1/<fw>/<versionId>/bin/<versionId+1>.bin` 取得的，app descriptor
编译时间为 `Oct 30 2026`。复现前必须重抓并重新核对 SHA，不能把本表的哈希当
长期发布标识。

准确度判定：

- UIFlow2 资产名/板名/BOARD_ID 均为 AtomU，**精确该板**；与 Atom-Lite 构建
  （`uiflow-…-atom-lite…`，SHA 不同）不可互换。
- UIFlow_AtomU 是 M5Burner 为 AtomU 单独登记的 UIFlow1 条目，但其 `binFileName`
  与 `UIFlow_Lite` 当前版本**完全相同**（`UIFlow-atom-v1.15.5-lite-0x0.bin`），
  说明是 Atom Lite 家族共用 UIFlow1 二进制 + 烧录器写板级 config 的形态。
  只能当"官方 UIFlow1 备选"，**不能当 UIFlow2 参考固件**。
- STT demo 是 2021 年 ESP-IDF v3.3.5 云 STT 演示；可做启动/PDM 采集路径参考，
  不是 UIFlow 参考固件。

来源：
`https://github.com/m5stack/uiflow-micropython/releases/tag/2.5.4`（asset 直链）；
`https://burner.m5stack.com/api/v1/firmwares/1897200000000001759/versions`；
`…/1897200000000001281/versions`；`…/1897200000000000024/versions`。

### 1.3 QEMU 复用分析（源码级）

可复用（已有实现）：
- classic ESP32 machine 与板级注册范式：`hw/xtensa/esp32.c:1038-1050`
  （`m5_board` 分派）、`:1148`（`mc->init = esp32_machine_init`）、
  `:1335-1355`（`m5atomlite` machine 的 init/class/TypeInfo 整套样板）。
- Atom 板级 glue 骨架：`hw/m5stopwatch/m5atomclassic.c:77-124`
  （I2C bus 绑定、`M5Unit` RGB/按键、1×1 诊断 console、input handler、
  `m5_unit_runtime_init(false)`、`m5_unit_classic_adc_init()`）。
- RGB LED 数据面：`m5_unit_gpio.c:775-813` 把 RMT TX 符号解码为 WS2812/SK6812
  颜色链（AtomU 也是 G27、1 颗灯，参数照抄 `io->yellow=27/white=39` 即可）。
- I2S0 PDM 麦克风：classic I2S controller 模型
  `hw/m5stopwatch/m5_i2s_esp32.c:1-10` 明确覆盖 "SPM1423 PDM microphone
  path"，`:236-290` 提供 `M5SW_I2S_RX_PCM_FILE` 主机 PCM 注入；同仓库
  `tests/uiflow2/core2_mic/README.md` 已在 classic ESP32 上验证 "I2S0 PDM RX +
  真实 DMA 描述符 + 注入 PCM" 路径。
- 按键 GPIO 注入、Grove/Unit runtime、classic ADC：沿用 Atom Lite 已有实现。

必须新增：
- `M5_BOARD_ATOMU` 枚举 + `m5atomu` machine 包装 + `m5atomu_board_init()`；
  实际是 `m5atomclassic.c` 的最小变体（1 LED、按键 G39、Grove G26/G32），
  **不需要新设备模型**。
- 如需 IR（G12）：现有 `m5_unit_gpio.c:775-807` 只对 `unit_id=="ir"` 的 Unit
  捕获 TX 脉冲，Atom Lite 也没接线验证；建议第一轮不接 IR（见风险）。

### 1.4 最小实现步骤

1. 前置（跨款）：解决"官方 UIFlow2 只在 GitHub release"的固件来源策略
   （见第 5 节）。
2. QEMU 补丁（下一个编号，0114 起）：新增 `M5_BOARD_ATOMU`、`m5atomu`
   machine、`m5atomu_board_init()`（复用 `m5atomclassic` 的 Unit/按键/console
   骨架，去掉 display 分支），`hw/xtensa/meson.build` 登记。无需新模型。
3. 固件缓存：`platform/.cache/firmware/atomu/uiflow2.bin` = 上面 2.5.4 asset，
   SHA 绑定 `affa252d…`。
4. 设备登记：`devices/catalog.source.json` + `devices/esp32-lx6/atomu/{device,firmware}.json`、
   `README.md`、`index.html`（照 `atom-lite` 模板；`hardware.sensors` 用
   `microphone:spm1423`、`rgb-led`、`ir`；`uiflow2.firmware` 指向固化 URL+SHA）。
5. `platform/qemu/profiles.json`：`backend=qemu-esp32lx6`、`board_model=m5atomu`、
   `peripherals=["gpio-button","rgb-led","esp32-i2s-pdm","grove"]`、
   `runtime_state` 记录 I2S RX PCM 文件。
6. `platform/peripherals/{catalog,runtime-coverage}.json`：新增/复用
   `esp32-i2s-pdm`、`rgb-led`；`atomu` 的 case 为 `console` 模式，
   `blocker` 写清"无屏幕、无扬声器，只验 PDM/按键/RGB"。
7. Probe：`tests/uiflow2/atomu_console_test/{boot.py,main.py}`。建议期望标记
   `ATOMU_BOOT_FLAG`、`ATOMU_MAIN_START`、`ATOMU_M5_BEGIN_OK`、
   `ATOMU_BOARD 130`、`ATOMU_RGB 0x<hex>`、`ATOMU_MIC_STATUS ok`；
   `M5SW_I2S_RX_PCM_FILE` 注入确定性 PCM 后要求 non-zero/peak-to-peak。
8. `tests/uiflow2/device_matrix.json`：`id=atomu`，`machine=m5atomu`，
   `vfs_offset=0x371000`、`vfs_size=0x8D000`、`flash_size=0x400000`、
   `memory=0`、`efuse_pkg_version=5`、`efuse_driver=nvram.esp32.efuse`、
   `mode=console`。
9. 定向跑该 case（同 guest UIFlow2 启动 + 麦克风 + RGB 标记），跑
   `qemu_profiles.py --check`、`runtime_coverage.py --check` 等生成器检查；
   浏览器/WASM 准入另行独立取证（`platform/web/qemu-browser-profiles.json`）。

### 1.5 风险

- **无屏幕、无扬声器**：只能验 boot、麦克风数据面、RGB、按键、Grove；UIFlow2
  的 UI/音频输出不在本机范围。
- PDM 时钟/数据是 G5/G19，和 Atom Echo 的 G33/G23 不同，不能拿 Echo 的探针继承。
- 官方规格表未写 Flash；4 MB 是板级构建+封装推断，QEMU Flash 模型用 4 MB 前
  需在镜像分区表上再确认（已确认 factory/vfs 布局，见 1.2）。
- UIFlow2 headless 启动会进网络配置菜单；探针沿用 Atom Lite 的 boot.py
  `_uiflow_run_main = True` 方式直接跑 `main.py`。

## 2. Atom Echo / Atom Voice（C008-C）— GO

### 2.1 命名与硬件档案

- `C008-C` 官方产品页标题是 **Atom Voice**
  （`https://docs.m5stack.com/en/products/sku/C008-C`，2026-11-02）；
  同一 SKU 的 Arduino 页是 `m5atomecho`（`/en/arduino/m5atomecho/program`），
  M5Burner/官方仓库固件名用 "Atom Echo"/"Atom Voice" 混用。**同一块板**，
  接入登记建议 id `atom-echo`、显示名注明 "Atom Voice（原 Atom Echo）"。

| 项目 | 值 |
| --- | --- |
| SKU | C008-C |
| SoC | ESP32-PICO-D4 240 MHz 双核 |
| Flash | 4 MB（官方规格表明确列出） |
| 显示 | 无 |
| 音频 | 扬声器 0.8 W / NS4168（I²S 功放，无寄存器接口）；麦克风 SPM1423（PDM） |
| 其他 | SK6812 RGB LED、按键、IR-TX、HY2.0-4P Grove、复位键、无 PSRAM |

PinMap（官方表格原文；注意 `G33` 在放音与录音两种半双工模式下复用）：

```
SPK & MIC : Atom Voice  G22=NS4168 AMP DATA  G19=AMP BCLK  G33=AMP LRCK
            SPM1423     G33=MIC CLK         G23=MIC DATA
HMI       : G27=RGB LED Data   G39=Button Input
HY2.0-4P  : GND / 5V / G26 / G32
```

官方引脚补充证据（`raw.githubusercontent.com/m5stack/M5Atom/master/examples/Echo/*.ino`）：
`RecordPlay/PlayMusic/EchoRest` 均为
`CONFIG_I2S_BCK_PIN=19`、`CONFIG_I2S_LRCK_PIN=33`、`CONFIG_I2S_DATA_PIN=22`、
`CONFIG_I2S_DATA_IN_PIN=23`，PDM RX 用 `setPinsPdmRx(33, 23)`，与 PinMap
完全一致。IR-TX 在规格表列出但 PinMap 未给引脚，**未确认**。

### 2.2 固件可用性（均实际下载）

| 类别 | firmware_id / 版本 | 文件名 | 大小 | SHA-256 | 镜像布局 |
| --- | --- | --- | --- | --- | --- |
| 官方 UIFlow2 | GitHub release `2.5.4`（板 `M5STACK_Atom_Echo`，BOARD_ID 142） | `uiflow-e437118-esp32-4mb-atomecho-v2.5.4-20261030.bin` | 4,186,112 | `8bae873945e85eff496670b9fbddcf7b5fecf31c99eba786fc15cce8c8e89472` | factory `0x10000/0x361000`、vfs `0x371000/0x8D000`；文件到 `0x3FE000` |
| 官方工厂固件（A2DP 蓝牙音箱） | `1897200000000001268` v1.0.0（M5Burner 名 "Atom Voice BT Audio"） | `776bd8c3e6b5b3ca14ea7ef8c0da304a.bin` | 2,097,152 | `fa9a4c4491a83fa5b60310ee35b14e3cef71bfeac5e1cd0883b84448f6923951` | 整片 2 MB：`0x0` 起 `0xFF`，bootloader `0x1000`、ptable `0x8000`、factory `0x10000/0x100000`；官方文档注明 BIN burn address `0x0000` |
| 官方 STT demo（UIFlow1 时代） | `1897200000000002476` v1.1-cn | `mxflcxl0tu8elvihbqos2oxyyqbqxvqn.bin` | 997,392 | `9f6e5a99f2d88a1ea5672d2106cec7f99d03f47bf41e4ed467e9e68cd8b447e9` | 稀疏：bootloader+ptable+app0（`0x10000`），止于 `0xF3810`；双 OTA+spiffs 布局 |
| 社区 | `1897200000000003383` v1.0 | `Atom Echo speaker test` | 4,000,000 | `6700907af9e5092434b265cc8100a61479e296f14beedcb1f4853d24b8ed6e89` | nvs `0x9000/20480`、otadata `0xE000/8192`、app0 `0x10000/0x300000`、spiffs `0x310000/0xE0000`、coredump `0x3F0000/0x10000`；文件止于 `0x3D0900`（稀疏） |
| 社区 | `1897200000000000088` v1.0.0 | `record&play_bin` | 4,194,304 | `1f3cf80b0d8254dc474e5a0ae9513179bd53488032ac44dbe0fb2b84376acb13` | 同上 4 MB 布局但 app0 到 `0x310000`；整片 4 MB |

准确度判定：

- UIFlow2 资产是精确板级构建（板名 `M5STACK Atom Echo` 已从镜像字符串核实，
  见 `0x2E0A0`/`0x574F0`），**精确该板**。
- 官方工厂 A2DP 固件与 M5Stack 官方仓库
  `M5-ProductExampleCodes/Core/Atom/AtomEcho/Factory_BT_SPEAKER_Firmware/BIN/Atom_echo_a2dp_led_0x00.bin`
  **SHA 完全相同**（互相印证），是官方精确该板工厂镜像；但它是 **ESP-IDF A2DP
  蓝牙音箱**，功能依赖蓝牙经典音频，而当前 classic ESP32 QEMU 无蓝牙音频模型，
  只能当"启动/初始化"证据，**不能当音频数据面参考固件**。
- EchoSTT 是官方 Atom Echo STT 演示（云 HTTP + 麦克风），可作 PDM/扬声器初始化
  参考，但不是 UIFlow 参考固件。
- 社区 speaker test / record&play 属于"同 SoC、可能同板"的社区镜像；可用来做
  PCM 数据面穷举，但**必须在证据里标社区**，不能算官方参考。

### 2.3 QEMU 复用分析（源码级）

- 板级骨架：同 AtomU，复用 `m5atomclassic.c:77-124`（G27 RGB、G39 按键、
  1×1 诊断 console、input handler）。
- 扬声器：classic I2S controller 模型就是为 "NS4168 speaker path +
  SPM1423 PDM microphone path" 写的（`m5_i2s_esp32.c:1-10`），
  `:91-130` 提供 `M5SW_I2S_PCM_FILE` 的 DMA 边界 PCM 捕获；仓库已在
  **Basic v2.7**（I2S0 DAC PCM）和 **Core2**（I2S1 NS4168）验证过这条模型，
  `tests/uiflow2/core2_audio/README.md` 明确其边界。
- 麦克风：同上 `core2_mic` 已验 PDM RX。
- 必须新增：`M5_BOARD_ATOM_ECHO` 枚举 + `m5atomecho` machine +
  `m5atomecho_board_init()`（Atom Lite 变体 + 无 display 分支）。**不需要新设备
  模型**；I2S0 已经由 SoC 初始化无条件注册（`hw/xtensa/esp32.c:648`
  `m5_esp32_i2s_board_init(...)`）。
- 新 guest 路径（本板特有，必须单独证明）：NS4168（I2S TX 标准模式）与
  SPM1423（PDM RX）在**同一 I2S0** 上按放音/录音切换，且 `G33` 在 LRCK 与
  PDM CLK 间复用；Core2 是 I2S1 放音 + I2S0 录音，不能直接继承这个半双工时序。

### 2.4 最小实现步骤

1. 固件来源策略同 AtomU（GitHub release → catalog/测试策略，见第 5 节）。
2. QEMU 补丁：`M5_BOARD_ATOM_ECHO` + `m5atomecho` machine +
   `m5atomecho_board_init()`（RGB G27、按键 G39、Grove G26/G32；IR 先不接），
   无新模型。
3. 固件缓存 `platform/.cache/firmware/atom-echo/uiflow2.bin`，SHA 绑定
   `8bae8739…`。
4. 设备登记：`devices/catalog.source.json`（id `atom-echo`，SKU C008-C，
   alias 记 Atom Voice）+ `devices/esp32-lx6/atom-echo/*`（`atom-lite` 模板；
   `sensors` 加 `speaker:ns4168`、`microphone:spm1423`、`rgb-led`、`ir`）。
5. Profiles/peripheral catalog/runtime-coverage：`m5atomecho`、外设
   `esp32-i2s-tx`（或复用 `esp32-i2s-dac` 命名，按现有 catalog 语义定）、
   `esp32-i2s-pdm`、`rgb-led`、`gpio-button`。
6. Probe `tests/uiflow2/atom_echo_console_test/`：期望标记
   `ATOM_ECHO_BOOT_FLAG`、`ATOM_ECHO_MAIN_START`、`ATOM_ECHO_M5_BEGIN_OK`、
   `ATOM_ECHO_BOARD 142`、`ATOM_ECHO_RGB 0x…`、`ATOM_ECHO_SPEAKER_RUNNING 1`、
   `ATOM_ECHO_MIC_STATUS ok`；PCM 断言照 Basic 的
   `min_nonzero≥1000, min_peak_to_peak≥1000`；麦克风用
   `M5SW_I2S_RX_PCM_FILE` 注入。
7. Matrix case `id=atom-echo`、`machine=m5atomecho`、
   `vfs_offset=0x371000`、`vfs_size=0x8D000`、`flash_size=0x400000`、
   `memory=0`、`efuse_pkg_version=5`、`mode=console`。
8. 定向 + 生成器检查，浏览器准入另立条目。
9. 官方 A2DP 工厂固件只登记为"boot-only 参考"：可另起 boot smoke，
   不得把"启动成功"写成音频 PASS。

### 2.5 风险

- 蓝牙经典 A2DP 不在 QEMU 模型内；官方工厂固件无法作为扬声器数据面参考。
- I2S0 半双工切换（TX ↔ PDM RX）与 G33 复用是全新 guest 路径，需要单板
  专项证据；如果固件在切换时依赖真实时钟行为，可能暴露模型缺口。
- IR-TX 引脚未确认（PinMap 无），不要"按 AtomU 的 G12 猜"。
- UIFlow2 无屏幕：验收以串口标记 + PCM/麦克风数据面 + RGB/按键为主。

## 3. M5Stick（K016）— DEFER

### 3.1 官方硬件档案与前置冲突

来源：`https://docs.m5stack.com/en/core/M5Stick`（2026-11-02）。

| 项目 | 值 |
| --- | --- |
| SKU | K016 |
| SoC | ESP32-WROOM32 双核 240 MHz |
| Flash | 4 MB |
| PSRAM | 无（未列） |
| 显示 | 1.3″ 64×128 OLED，**SH1107**（SPI：CS/DC/RST/D0/D1） |
| 其他 | 蓝色 LED、有源蜂鸣器、IR 发射、自定义按键、MPU9250 九轴（仅灰色版）、IP5306 电源管理、80 mAh 电池、Grove、USB-C |
| 蓝牙/Wi-Fi | 2.4 GHz Wi-Fi |

PinMap（官方表格原文）：

```
LED/BUTTON/BUZZER/IR : G17(IR Tx)  G19(Blue LED)  G26(Buzzer)  G35(Button)
OLED (SH1107)        : G14(CS) G27(DC) G33(RST) G18(D0) G23(D1)
MPU9250 (Gray ver.)  : G22(SCL) G21(SDA)
HY2.0-4P             : GND / 5V / G32 / G33
```

前置冲突：官方 StickC 是 `K016-C`（`https://docs.m5stack.com/en/core/StickC`
抓到 `SKU:K016-C`），而已登记设备 `stickc` 在
`devices/catalog.source.json` 里写的是 `"sku": "K016"`。接入 `m5stick` 前必须
先把 `stickc` 的 SKU 修正为 K016-C，否则两个设备共用同一 SKU 且与官方事实
冲突（这是 catalog 数据缺陷，不在本次研究范围内修复）。

### 3.2 固件可用性（官方 UIFlow 全缺；工厂镜像为安装包内嵌）

检索方式与结果（2026-11-02）：
- `https://burner.m5stack.com/api/v1/devices` 共 54 个设备码，**无 M5STICK/
  K016 设备**；`/api/v1/firmwares?keyword=M5Stick` 311 条结果全为
  StickC/Plus/Plus2/S3 等，没有 K016。
- `docs.m5stack.com` 只有 `/en/core/M5Stick`；UIFlow1 教程列表无
  `m5stick`（只有 m5stickc 系列），UIFlow2 板列表也无 M5Stick。
- 文档页 "M5Stick Factory Test Example" 指向
  `github.com/m5stack/M5Stack/tree/master/examples/Stick/FactoryTest`，
  2026-11-02 该路径返回 **HTTP 404**（`M5Stack` 仓库 tree 中已不存在；仅 `M5-ProductExampleCodes` 下的 AtomEcho 工厂固件目录仍 200）。
- 唯一官方可执行固件：官方 EasyLoader 安装包
  `https://m5stack.oss-cn-shenzhen.aliyuncs.com/EasyLoader/Windows/CORE/EasyLoader_M5Stick_FactoryTest.exe`。

实测下载与提取（提取脚本见"复现"）：

| 产物 | 大小 | SHA-256 | 说明 |
| --- | --- | --- | --- |
| `EasyLoader_M5Stick_FactoryTest.exe`（官方安装包） | 9,463,808 | `99c640b0ed51bd9670f544164f5542cb9c0303f1b6f84a4ee91e33e6c82e69f4` | Windows 安装器，内含多段 firmware blob |
| 提取的连续 Flash 段（flash `0x1000`–`0x481E0`） | 291,296 | `808cf8968df8b5d039391dc27f6346042fa6e4685c27393290edeb04ad1994dd` | bootloader `0x1000`（28,672 B，含 0x1000–0x8000 区间）、ptable `0x8000`、app `0x10000` |
| 规范化 4 MB merged（头部 `0x0–0xFFF` 补 `0xFF`） | 4,194,304 | `d960e57e0220c7c92ace223a3e8e71c52fe6fa3da60e23800a93bb68cd1ec4b5` | 可直接按 flash 0 地址烧录 |

提取镜像的分区表（flash 偏移）：

```
nvs     0x9000/0x5000    otadata 0xE000/0x2000
app0    0x10000/0x140000 app1    0x150000/0x140000
spiffs  0x290000/0x170000（无 VFS 分区；spiffs 未包含在 4 MB 提取内容里，尾部为 0xFF）
```

app 位于 `0x10000`，6 段共 229,856 B；app 字符串含 `Hello`、`World!`、
`mpu9250 addr: `，与官方文档"FactoryTest 按 A 键打印 helloworld"和
九轴探测一致。**注意**：同一安装包还内嵌了其它无关 firmware blob
（含 `nesgame` 分区镜像），提取必须以 bootloader/ptable/app 三段为白名单，
不能整包当固件。

准确度判定：官方 EasyLoader 是官方渠道的**工厂测试固件**，可当"该板官方
固件"；但没有 UIFlow1/UIFlow2，因此没有同 guest 的 UIFlow2 API 面与
board-probe 注入路径。**这是 DEFER 的核心原因之一。**

### 3.3 QEMU 复用分析（源码级）

- 可复用：classic ESP32 machine；IP5306 I2C 寄存器模型（
  `patches/qemu-m5stack-peripherals/0113-basic-v27-board.patch` 新增
  `hw/m5stopwatch/m5_ip5306.c`、`TYPE_M5_IP5306`、`battery-mv` QOM fixture），
  Basic v2.7 已验证 guest 读 `0x75`、充电请求、READ0/READ4；
  GPIO 输入/输出、RMT/IR 脉冲捕获（`m5_unit_gpio.c:775-807`）、classic ADC、
  Unit runtime 都可复用。
- 必须新增：
  1. **SH1107 OLED 模型**：SPI 4 线（CS/DC/RST/SCLK/MOSI）、64×128 单色
     framebuffer + 命令解析。现有 `m5_spi_panel.c` 是 RGB565/ST77xx–ILI9342
     类面板（`m5_spi_panel.c:1-10`），**不能**直接当 SH1107；QEMU 树内也没有
     SSD1306/SH1107 现成模型（`hw/display/` 只有 ssd0303/ssd0323），需要新写。
  2. **MPU9250（九轴）I2C 模型**：现有 `m5sw_i2c_devs.c:20-52` 模型枚举里没有
     MPU9250（只有 MPU6886/BMI270/BMM150 等）。MPU9250 与 MPU6886 寄存器族
     相近但 WHO_AM_I=0x71 且带 AK8963 磁力计，可扩 `m5sw_i2c_devs.c` 或在
     `m5_unit_i2c_sensors.c` 侧加模型。
- 蜂鸣器：无源/有源蜂鸣器在这块板是 GPIO 直驱；现有模型可观测 GPIO/PWM
  边沿/频率（`m5_unit_pwm_observe`），但没有声学输出——登记时要写清
  "digital-only"。
- 屏幕帧：只有 SH1107 模型落地后才有帧数据面。

### 3.4 结论与最小实现步骤

**DEFER**。触发条件（任一即可启动）：
1. 有 UIFlow1/UIFlow2 或其它带可注入文件系统的官方固件出现；或
2. 决定投入 SH1107 + MPU9250 两个模型，并把"工厂测试固件 boot/显示/九轴读取"
   作为可接受验收面；且
3. `stickc` 的 SKU 冲突已修正。

若启动，最小步骤：
1. 修 `stickc` SKU（K016-C）；新增 `m5stick` 设备与 `M5_BOARD_M5STICK` +
   `m5stick` machine + 板级 glue（IP5306 `0x75`、按键 G35、LED G19、IR G17、
   蜂鸣器 G26、SH1107 SPI 面板、MPU9250 `0x68`）。
2. 新增 SH1107 面板模型 + 64×128 帧 fixture；新增 MPU9250 I2C 模型。
3. Probe：因为固件不是 MicroPython，**现有 device matrix 的
   `files_dir` 注入模式不适用**（`run_device_matrix.py` 会对 `base`+`files_dir`
   组合生成镜像）。需要新增"外部工厂固件"case 模式或直接用
   `run_profile_ui_test.py --allow-static-frame` 捕获固定帧；串口只认
   `Hello`/`World!`/`mpu9250 addr: ` 这类固定串。
4. 验收标记建议：`M5STICK_BOOT`（若串口可见）、SH1107 64×128 帧非全黑、
   按键后帧变化、"mpu9250 addr: " 串口、QOM 上 IP5306 寄存器读写。
5. 明确边界：这是"官方工厂测试固件 boot/显示/传感器读取"，不是 UIFlow2
   功能验证，也不继承 StickC/AXP192 的任何结论。

### 3.5 风险

- 只有 Arduino 1.x/ESP-IDF v4.4 时代的工厂测试固件；没有 UIFlow2 路径，
  无法复用仓库的 UIFlow2 探针/API sweep 架构（需要新的 external-firmware 模式）。
- 板修订：官方写 MPU9250 仅"Gray version"；黑色版无九轴。固件/视觉外壳都不
  能区分修订，接入前必须定修订或把 IMU 标 `partial`。
- 固件提取依赖 EasyLoader 安装包内部布局（非文档化契约），换版本会变；
  必须钉住安装包 SHA 并保留提取脚本。
- SH1107 + MPU9250 + 新 matrix 模式三项成本叠加，收益只有一块 64×128 单色屏，
  性价比低于 Atom 两款。

## 4. StickT2（K016-T2）— DEFER

### 4.1 官方硬件档案（含一处既有计划错误）

来源：`https://docs.m5stack.com/en/core/StickT2`（2026-11-02）。

| 项目 | 值 |
| --- | --- |
| SKU | K016-T2 |
| SoC | ESP32-PICO-D4 240 MHz |
| Flash | 4 MB |
| 屏幕 | 1.14″ 135×240 IPS，**ST7789** |
| 热成像 | **FLIR Lepton 3.0**（160×120，LWIR，I2C 命令 + VoSPI 视频，25 MHz 输入时钟） |
| IMU / PMIC | MPU6886 `0x68` / AXP192 `0x34`（同一 G22/G21 I2C） |
| 麦克风 | SPM1423（PinMap 标 SCL=G0 / SDA=G34，实为 PDM CLK/DATA） |
| 输入 | 按键 A G37、B G39、旋转编码器 |
| 电池 | 300 mAh |
| Grove | HY2.0-4P G32/G33 |

PinMap（官方表格原文）：

```
Button A/B : G37(Button A)  G39(Button B)
IPS Screen (ST7789) : G15(MOSI) G13(CLK) G23(DC) G18(RST) G5(CS)
Microphone MIC (SPM1423) : G0(SCL) G34(SDA)
MPU6886(0x68)/AXP192(0x34) : G22(SCL) G21(SDA)
Rotary Encoder : PA2(SW) PA3(EN_B) PA4(EN_A)
HY2.0-4P : GND / 5V / G32 / G33
```

**未确认项（阻塞级）**：文档编码器 PinMap 写 `PA2/PA3/PA4`（ESP32-PICO-D4
没有这种引脚名），而官方 `M5-StickT` 示例却是通过 `Wire1` 访问 **I2C 编码器
`0x30`**（`examples/M5StickT_Lepton_opensource_v1/M5StickT_Lepton_opensource_v1.ino:81-118`）。
两者矛盾，建模前必须从原理图/库源码定案。

### 4.2 固件可用性（均实际下载）

| 类别 | firmware_id / 版本 | 文件名 | 大小 | SHA-256 | 镜像布局 |
| --- | --- | --- | --- | --- | --- |
| 官方工厂 Demo | `1897200000000001879` v1.0（M5Burner "StickT2 User Demo"） | `8babd7ac4c0a36ae63b4d0127e2c2e63.bin` | 4,194,304 | `bb33ffd41f9c6f9235b2fb44eac893b7ce6f70879f48eed9cb1ff75ef9419cd7` | bootloader `0x1000`、ptable `0x8000`、ota_0 `0x10000/1536000`、ota_1 `0x190000/1536000`、nvs_key `0x307000/4096`；app 在 `0x10000`（6 段，段区结束 `0x78144`）；`0x101000` 后全 `0xFF` |
| 官方源码/分段镜像（`m5stack/M5-StickT` 仓库） | `examples/M5StickT_Lepton_opensource_v1/bin/` | app `M5_StickC_Lepton_opensource_v1.ino.bin` + `…partitions.bin` | 426,352 / 3,072 | app `361f0d25e5ad7d5dbb8fb52a4e412dcf9fc118c7b0a3aef73fc3159bad539b40`；ptable `efba4421982bd177695a2e2091828fe3b6aa42076be3844a84f0fb08085cead4` | app-only 镜像（烧 `0x10000`）+ 独立分区表（烧 `0x8000`）；ptable：nvs/otadata/app0 `0x10000/1310720`/app1 `0x150000/1310720`/spiffs `0x290000/1507328` |

发现与判定：
- M5Burner 的 STICK_T2 设备条目 `firmwareCount=0`，"StickT2 User Demo" 被 API
  标在 **STICKC** 设备下；但固件名/板级 Demo/官方仓库均指向 StickT2，属于
  "官方精确该板固件、API 设备标签不精确"，接入时按名称+板级证据登记，
  不按 device tag 继承。
- 该 4 MB 镜像的 bootloader/ptable/app 都在标准偏移，app 可解析；但
  **app 段结束到 `0x101000` 之间存在非 `0xFF` 数据**（约 0x78'000–0x100'000，
  含 ESP-IDF BT controller 字符串如 `ld_acl.c`/`Coex`），不属于任何命名分区，
  来源未确认（疑似 M5Burner 打包/历史 flash 残留）。接入前必须决定
  "原样烧录整 4 MB"还是"只写 bootloader/ptable/app 三段"，并在证据里记录；
  不能把这段数据当已解释内容。
- 无 UIFlow1/UIFlow2；能走的是 generic full-flash 路径（工厂 Demo）或官方
  分段 app 镜像。

### 4.3 QEMU 复用分析（源码级）

- 可复用：`m5stickc.c:16-45` 的 I2C 设备集（AXP192 `0x34`、PCF8563 `0x51`、
  MPU6886 `0x68`）、软 I2C 引脚初始化；ST7789 面板参数沿用
  `m5stickc.c:51-71`（135×240、read-id `0x85`、offset 52/40、invert，
  且该处 `esp32_spi_attach_m5_panel(..., 23)` 注释已给出
  SCK13/MOSI15/CS5/RST18/DC23 的同一套接线），
  只要把 SPI 接线换成 StickT2 的 `MOSI15/CLK13/DC23/RST18/CS5`；
  SPM1423 PDM RX 走 classic I2S 模型（`m5_i2s_esp32.c`，G0/G34）；
  按键 G37/G39 与经典 GPIO 输入模型。
- 必须新增：
  1. **FLIR Lepton 3.0 模型**：I2C `0x2A` 命令/寄存器文件（PING、AGC、FFC、
     telemetry 等）+ VoSPI 帧流（SPI 从设备，按 164×122 规格包/行/帧 marker
     发送 160×120 热数据）+ thermal fixture（温度场注入，不能伪造物理温度）。
     这是本款最重的新工作，且官方示例 `lepton.cpp` 的 `begin()` 会同步等待
     SPI 帧，**没有 Lepton 模型连 boot 都可能阻塞**。
  2. 编码器模型（待定：I2C `0x30` 编码器或 GPIO 正交编码，取决于 4.1 的
     矛盾结论）。
- 屏幕、PMIC、IMU、麦克风都已有现成模型，不需要新写。

### 4.4 结论与最小实现步骤

**DEFER**。阻塞原因不是 SoC，而是：(a) Lepton 3.0 + thermal fixture 是新
设备类（`docs/runtime-model-gap-register.md` 的"没有数据面不能写 simulated"
边界）；(b) 编码器接口矛盾未定；(c) 4 MB 工厂镜像的异常数据段未解释；
(d) 没有 UIFlow2 可走，难以复用现有 UIFlow2 探针架构。

若启动，最小步骤：
1. 先解决编码器与异常数据段两个未确认项。
2. QEMU：`M5_BOARD_STICKT2` + machine + 板级 glue（AXP192/MPU6886/ST7789/
   PDM/按键）+ Lepton 模型 + thermal fixture（QOM/环境变量注入温度场）。
3. Probe：外部工厂 Demo 无 MicroPython 文件系统，需要 external-firmware case
   模式；期望标记建议 `STICKT2_BOOT`、135×240 帧、`LEPTON_FRAME`（fixture 下
   帧变化/QOM 计数）、`STICKT2_ENCODER`（定案后）。
4. 明确边界：热成像是 fixture 数据面，不是光学/温度测量；AXP192 电气、电池、
   Lepton 机械/光学均 NOT RUN。

### 4.5 风险

- Lepton VoSPI 时序/包结构对固件同步很敏感，模型偏差会表现为 boot hang。
- 4 MB 镜像异常段来源不明；若原样烧录，需在证据说明"未解释字节"。
- 编码器接口文档自相矛盾，且 2020/2021 两个硬件修订（官方 Version Change）
  可能改变编码器结构。
- 官方 Demo 无串口标记（镜像里未见可识别 probe 字符串），证据只能靠帧 + QOM。

## 5. StickV（K027）— NO-GO（异构）

- 官方页面 `https://docs.m5stack.com/en/core/StickV`：**Kendryte K210**
  （RISC-V 双核 400 MHz + KPU），不是 ESP32，因此不属于 `qemu-esp32lx6` 后端，
  与现有 ESP32 所有结论不可继承。
- M5Burner API 搜 `StickV` 结果为 0 条（2026-11-02），也没有 UIFlow2/UIFlow1。
- 决策：**NO-GO（ESP32 后端）**。若将来要接，只能像 CardputerZero 一样建
  独立后端（K210 模拟器/开发板），并在 `platform/qemu/profiles.json` 里用
  `separate-backend` 表达；不创建 ESP32 alias，不占 ESP32 执行队列。
  本页只确认边界，不做技术选型。

## 6. 固件来源策略（跨 AtomU/Atom Echo 的阻塞项）

实测（2026-11-02）：
- M5Burner 公开 API 的 UIFlow2 列表（54 条）**没有** `UIFlow2.0 AtomU` /
  `UIFlow2.0 Atom Echo`；ATOM_LITE 设备下 25 条、ATOM_SERIES 下 10 条也都没有。
- 但官方 GitHub `m5stack/uiflow-micropython` release `2.5.4` 直接发布
  `…-esp32-4mb-atomu-…bin`、`…-esp32-4mb-atomecho-…bin`（还有 atom-lite /
  atom-matrix / stickc / stickcplus 等），且板级 `mpconfigboard.cmake` 明确
  BOARD_ID 130/142、`sdkconfig.flash_4mb`，属于官方精确构建。
- 仓库现状 `platform/tests/test_catalog.py:139-144` 强制
  `uiflow2.firmware.download_url.startswith("https://m5burner-cdn.m5stack.com/")`
  且 `firmware_id` 非空；`platform/tools/fetch_firmware.py` 也从 M5Burner API
  解析 URL（`--no-resolve` 时才直接用 catalog `download_url`）。
- 结论：AtomU/Atom Echo 的 UIFlow2 参考固件**必须先扩展固件来源策略**，可选：
  1. 允许 catalog 记录"官方 GitHub release asset + 固定 SHA-256"作为受控来源，
     同步放宽 `test_catalog` 与该 URL 断言（推荐；官方来源、SHA 可钉）；
  2. 等 M5Stack 把镜像发布到 M5Burner 再接入（不阻塞研究，但接入不可排期）；
  3. 走 reviewed artifact archive 固定副本（增加发布/审计成本）。
  本页不实现该策略，只把它列为 Atom 批次的第 0 步。

UIFlow1 的 AtomU 镜像虽然 M5Burner 有官方条目，但其 4 MB 文件只到 `0x3FE000`，
而分区表在 `0x3FE000`/`0x3FF000` 还有 `config`/`wifi` 两个自定义分区——**推断**
配置由 M5Burner 烧录时补写（未找到公开文档确认，见第 9 节）；generic full-flash
路径若不补 config，UIFlow1 的板级选择/网络配置可能不生效。UIFlow2 镜像同样
只到 `0x3FE000`（vfs 结束），但 UIFlow2 没有 config/wifi 分区，补 `0xFF` 到
4 MB 即可（仓库已有"稀疏 merged 补齐"先例：`docs/firmware-manifest.md:32-41`、
`docs/firmware-manifest.md:637-639`）。

## 7. 预期探针标记汇总

| 设备 | 建议标记（串口） | 数据面断言 |
| --- | --- | --- |
| atomu | `ATOMU_BOOT_FLAG` / `ATOMU_MAIN_START` / `ATOMU_M5_BEGIN_OK` / `ATOMU_BOARD 130` / `ATOMU_RGB 0x…` / `ATOMU_MIC_STATUS ok` | `M5SW_I2S_RX_PCM_FILE` 注入后非静音；RGB QOM 颜色 = guest 写入值；按键 GPIO 回读 |
| atom-echo | `ATOM_ECHO_BOOT_FLAG` / `ATOM_ECHO_MAIN_START` / `ATOM_ECHO_M5_BEGIN_OK` / `ATOM_ECHO_BOARD 142` / `ATOM_ECHO_RGB 0x…` / `ATOM_ECHO_SPEAKER_RUNNING 1` / `ATOM_ECHO_MIC_STATUS ok` | 扬声器 PCM 文件 non-zero/peak-to-peak（照 Basic 阈值）；麦克风注入 PCM；RGB/按键 |
| m5stick | 仅固件原生串（`Hello`/`World!`/`mpu9250 addr: `；无 UIFlow 标记） | SH1107 64×128 帧；按键后帧变化；QOM IP5306 读回 |
| stickt2 | 仅固件原生串（未发现可用 probe 串） | ST7789 135×240 帧；Lepton fixture 帧/计数（模型落地后）；编码器定案后另加 |

标记命名只是建议，实现时以现有 `device_matrix` 的 `serial_expect` 语义为准；
每个标记必须绑定固件 SHA、machine 和运行证据，不能跨设备继承。

## 8. 需要的 QEMU 模型一览

| 设备 | 新 machine | 新设备模型 | 复用 |
| --- | --- | --- | --- |
| atomu | `m5atomu` | 无 | classic machine、I2S0 PDM RX（`m5_i2s_esp32.c`）、RMT/SK6812（`m5_unit_gpio.c`）、GPIO、Unit runtime |
| atom-echo | `m5atomecho` | 无（半双工 I2S0 需新 guest 证据） | 同上 + I2S0 TX PCM 捕获（`m5_i2s_esp32.c:91-130`） |
| m5stick | `m5stick` | **SH1107 面板**、**MPU9250 I2C** | IP5306（`m5_ip5306.c`）、GPIO/RMT、ADC、Unit runtime |
| stickt2 | `m5stickt2` | **Lepton 3.0（I2C+VoSPI+fixture）**、编码器（待定） | AXP192/MPU6886/ST7789 面板/PDM RX/GPIO |
| stickv | —（NO-GO） | — | 独立后端，不接 |

## 9. 未确认项

1. **AtomU Flash 4 MB**：官方规格表未列，来自 UIFlow2 板级 `sdkconfig.flash_4mb`
   + ESP32-PICO-D4 封装；接入前用 app/分区实测/官方 datasheet 再确认。
2. **Atom Echo IR-TX 引脚**：规格表有 IR-TX，PinMap 未给；不要猜 G12。
3. **Atom Echo NS4168 使能/静音控制**：PinMap 只列 3 根 I2S，需原理图确认是否有
   额外 GPIO 使能（若无，模型侧不能凭空造）。
4. **M5Stick 板修订**（Gray/Black）与 IMU 是否存在；IP5306 I2C 总线在
   G21/G22 是"与 MPU9250 共享"的推断，需官方 `Power.pdf` 原理图确认。
5. **M5Stick 工厂固件提取**：安装包内部布局非契约；换版本需重提取并重新
   钉 SHA；同一安装包内还有 `nesgame` 等无关 blob，必须白名单提取。
6. **StickT2 编码器接口**：文档 `PA2/PA3/PA4` vs 官方示例 `Wire1` I2C `0x30`
   矛盾；以及 2020/2021 两版硬件差异。
7. **StickT2 4 MB 镜像 `~0x78'000–0x100'000` 非 `0xFF` 数据**：不属于任何分区，
   来源未确认；决定原样烧录还是只写三段前必须解释或记录。
8. **UIFlow1 `config`/`wifi` 分区写入约定**：镜像在 `0x3FE000` 截断，分区表却
   声明了 `config`/`wifi`；推断 M5Burner 烧录时补写，但未找到公开契约/格式说明。
9. **UIFlow2 GitHub release 的长期可用性**：release asset 不是 CDN 稳定契约
   （可能随仓库/流量策略变化），需要 SHA 固定 + 受控镜像策略（第 6 节）。

## 10. 复现与本地证据（不提交）

固件/抓取物都在 `.work/classic-hosts/`（gitignored）：
`firmware/`（所有 `.bin` 与 `sha256.txt`）、`docs/`（docs.m5stack.com HTML
快照 + `txt/` 文本提取）、`github/`（官方仓库源文件）、`devices.json`、
`versions.json`。

关键命令（节选）：

```bash
# docs 页面
curl -sL 'https://docs.m5stack.com/en/products/sku/C008-C' -o atom-echo.html
# M5Burner 元数据
curl -s 'https://burner.m5stack.com/api/v1/firmwares/<firmware_id>/versions'
# 新式 CDN
curl -sL 'https://m5burner-cdn.m5stack.com/firmware/<binFileName>'
# 老式 UIFlow 镜像
curl -sL 'https://m5burner-cdn.m5stack.com/community/1/<fw>/<versionId>/bin/<versionId+1>.bin'
# 官方 UIFlow2 精确板镜像
curl -sL 'https://github.com/m5stack/uiflow-micropython/releases/download/2.5.4/uiflow-e437118-esp32-4mb-atomecho-v2.5.4-20261030.bin'
# M5Stick 工厂测试固件（EasyLoader 安装包）
curl -sL 'https://m5stack.oss-cn-shenzhen.aliyuncs.com/EasyLoader/Windows/CORE/EasyLoader_M5Stick_FactoryTest.exe'
```

M5Stick 4 MB 规范化算法（可复现）：在安装包内定位 bootloader `0x1000` 偏移的
ESP image（提取位置 `0x527b41`）、分区表 `aa50`（`0x52eb41`）、app `0x10000`
偏移 ESP image（`0x536b41`）；以 bootloader 起点为 flash `0x1000`，取连续
`0x471E0` 字节写入 4 MB `0xFF` 缓冲的 `0x1000` 处，得
`d960e57e…`（4 MB）/`808cf896…`（291,296 B 段）。

## 11. 建议的下一批执行顺序

1. **第 5 批：atomu**（GO）——先做固件来源策略（第 6 节）+ 无屏幕 UIFlow2
   板级 glue；零新设备模型，最快闭环 PDM/RGB/按键，为 atom-echo 铺路。
2. **第 6 批：atom-echo**（GO）——复用第 5 批 machine 模板，新增 I2S0 放音
   PCM + 半双工切换证据；官方 A2DP 工厂固件只做 boot smoke。
3. **第 7 批：m5stick**（DEFER→条件 GO）——先修 `stickc` SKU 冲突并决定
   SH1107/MPU9250/external-firmware matrix 模式三项投入。
4. **第 8 批：stickt2**（DEFER）——等 Lepton 模型 + thermal fixture 架构决策；
   编码器/异常数据段先定案。
5. **StickV**：NO-GO（ESP32 后端），只保留独立后端评估条目。

每一批都必须：设备本地 probe、`runtime-coverage.json`/`qemu_profiles.json`
登记、targeted matrix、证据 SHA、状态/台账更新；不能用 Atom Lite 或 StickC
的 PASS 继承。

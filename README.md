# M5Stack Multi-Device Simulator

[![CI](https://github.com/m5agent/m5stack-esp-emulator/actions/workflows/ci.yml/badge.svg)](https://github.com/m5agent/m5stack-esp-emulator/actions/workflows/ci.yml)

面向 UIFlow2 固件验证、UI 预览、自动测试和未来设备中心接入的多主控模拟平台。

![设备目录](docs/images/device-gallery.png)

项目按芯片架构分组保存 14 个 M5Stack 主控档案。13 台 ESP32 主控均已完成官方
UIFlow2 启动和统一矩阵验收；其中有屏设备已验证目标分辨率首帧与触摸/按键重绘，
无屏 NanoC6 验证串口启动链路。CardputerZero 使用独立 ARM64 Linux 后端，当前已
完成官方镜像启动、320×170 ST7789v3 帧缓冲、键盘输入、主要 I2C 外设和音频播放
与麦克风 PCM 双向回放、IP2315 充放电状态、GL852G High-Speed Hub、
SR9900A 以太网帧回环、寄存器驱动的 IMX219 + Unicam V4L2 实帧采集、
GL852G MTT 兼容全/低速下游路由，以及 GPIO 红外收发。

外设仿真采用统一契约而不是逐设备硬编码：所有非显示外设必须在
`platform/peripherals/catalog.json` 中声明芯片、总线、地址、注入接口和实现状态。
新增设备若漏登记 IMU、音频、继电器等能力，CI 会失败。设计说明见
[`docs/peripheral-simulation-architecture.md`](docs/peripheral-simulation-architecture.md)。
当前 14 个虚拟主机中 13 个已通过全部登记外设的数据面验收；Tab5 仍受原生
P4 CSI/I2S/USB/SDIO 与动态 I2C 后端缺口限制，不能误标为全外设闭环。

## 快速开始

```bash
./start.sh
```

打开 `http://127.0.0.1:8080/platform/web/`。

也可以直接启动：

```bash
python3 platform/tools/serve.py 8080
```

浏览器设备目录只需要 Python 3。完整 QEMU/UIFlow2 回归还需要本地准备：

- `.work/M5StopWatch-QEMU/`：按 `patches/qemu-*/README.md` 应用板级补丁并构建 QEMU；
- `.work/esp-emu-versions/0.50.0/`：ESP32-C6/P4 使用的 `esp-emu`；
- Espressif QEMU ROM/eFuse 文件：按上游许可自行获取；
- `UIFLOW_MICROPYTHON_DIR`：指向 UIFlow2 源码 checkout；
- `python3 platform/tools/fetch_firmware.py <device>`：下载公开固件到本地缓存。

固件、ROM、QEMU 二进制和构建目录都被 `.gitignore` 排除，不进入公开仓库。

## 能力分层

| 状态 | 含义 | 型号 |
| --- | --- | --- |
| `reference-ready` | 官方固件启动、目标尺寸画面、输入注入均可用 | StopWatch、StickS3、AtomS3R、CoreS3、Cardputer-ADV、StamPLC、StackChan、PaperColor、PaperMono、Nesso N1、Core2、Tab5 |
| `boot-capable` | 官方固件启动并可查看串口，设备本身无显示屏 | NanoC6 |
| `backend-required` | UIFlow2 运行时不能直接调度，需要独立架构后端 | CardputerZero（ARM64 Linux，独立后端已可启动并部分验收） |

> `boot-capable` 只表示对应芯片固件能启动并输出串口，不表示所有 UIFlow2 外设和 UI 已通过。当前 13 台 ESP32 虚拟主机均完成矩阵验收；Nesso N1 与 Tab5 的真实分辨率、首帧和输入重绘均已通过。Tab5 使用 P4 仿真专用 M5GFX framebuffer 构建，当前启用原生 M5GFX/UIFlow2 UI 路径，LVGL Python 绑定暂不在仿真构建中启用。

CardputerZero 的 BCM2837 后端、DTB 修复、guest probe、键盘/帧缓冲和 I2S PCM
测试见 [`tests/cardputer_zero/`](tests/cardputer_zero/)。

![UIFlow2 虚拟主机验收矩阵](docs/images/uiflow2-virtual-host-matrix.png)

## 设备目录

```text
devices/
├── catalog.json                 # 设备中心可读目录
├── esp32-s3/
│   ├── sticks3/
│   ├── cores3/
│   ├── stopwatch/
│   ├── cardputer-adv/
│   ├── papermono/
│   ├── papercolor/
│   ├── stackchan/
│   ├── atoms3r/
│   └── stamplc/
├── esp32-c6/
│   ├── nanoc6/
│   └── nesso-n1/
├── esp32-p4/
│   └── tab5/
├── esp32-lx6/
│   └── core2/
└── linux-arm64/
    └── cardputer-zero/
```

每个设备目录包含：

- `device.json`：芯片、内存、显示、控制、外设、UIFlow2、运行时状态
- `firmware.json`：UIFlow2 版本、公开 firmware ID、下载地址和缓存路径
- `README.md`：设备能力与边界
- `index.html`：打开对应模拟页面
- `web/`：仅设备专属运行时使用，目前是 StopWatch

## UIFlow2 固件

StopWatch 的 QEMU 后端已修复官方 UIFlow2 v2.5.3 的启动链：可从 ROM 进入 UIFlow2 启动器并输出 466×466 UI；同时提供了本地 `main.py` UI 交互测试。修复说明、复现命令和边界见 [`docs/stopwatch-uiflow2-qemu.md`](docs/stopwatch-uiflow2-qemu.md)，补丁见 [`patches/qemu-stopwatch-uiflow2-boot/`](patches/qemu-stopwatch-uiflow2-boot/)，测试见 [`tests/uiflow2/stopwatch_ui_test/`](tests/uiflow2/stopwatch_ui_test/)。

ESP32-C6 的 QEMU 后端已完成 NanoC6 控制台、RGB/按键/蓝灯/红外，以及 Nesso N1 板型探测、ST7789、触摸、共享 SPI 外设和 USB-Serial-JTAG console；两种 C6 板型按 `M5SW_C6_BOARD` 独立装配，不再互相挂载外设。补丁与边界见 [`patches/qemu-esp32c6-uiflow2-adapters/`](patches/qemu-esp32c6-uiflow2-adapters/)、[`tests/uiflow2/nanoc6_peripherals/`](tests/uiflow2/nanoc6_peripherals/) 和 [`tests/uiflow2/nesso_n1_ui_test/`](tests/uiflow2/nesso_n1_ui_test/)。Core2 的完整 320x240 首帧和 FT5x06 触摸重绘已通过，测试见 [`tests/uiflow2/core2_ui_test/`](tests/uiflow2/core2_ui_test/)。

### CoreS3 动画与 Canvas

CoreS3 的 M5GFX 面板使用 `offset_rotation=3`，横屏 320×240 应设置为
`M5.Display.setRotation(1)`；设置成 `0` 会得到 240×320 的逻辑绘图区并裁掉右侧。

[`tests/uiflow2/cores3_pelican_bike/`](tests/uiflow2/cores3_pelican_bike/)
用单个复用 M5GFX Canvas 绘制文字、图形、滚轮、踏板、围巾和道路动画，完成后一次
`push()` 呈现。拖动公路可调整 0–4 档速度，长按鹈鹕触发铃声，点击右上角按钮可
暂停；BMI270 的 X/Y 加速度会平移和抬降骑手，Z 轴陀螺仪会驱动围巾与速度线。
该样例同时验证 320×240 帧、连续帧变化、FT6336 拖拽/长按/点击以及
`Imu.getAccel()/getGyro()` 注入回读。长按铃声通过 AW88298 + I2S TX 播放
1000 Hz / 800 Hz 两段 tone，QEMU 捕获到非静音 PCM。

```bash
M5SW_I2S_DMA_IRQ=1 \
M5SW_I2S_PCM_FILE=/tmp/m5-cores3-pelican/speaker.pcm \
PYTHONPATH=.work/py python3 tests/uiflow2/run_profile_ui_test.py \
  --base platform/.cache/firmware/cores3/uiflow2.bin \
  --machine m5cores3 \
  --files-dir tests/uiflow2/cores3_pelican_bike \
  --vfs-offset 0xAA0000 --vfs-size 0x4C0000 --flash-size 0x1000000 \
  --expected-size 320x240 \
  --qom-set /machine/bmi270 accel-x 0.65 \
  --qom-set /machine/bmi270 accel-y -0.25 \
  --qom-set /machine/bmi270 accel-z 0.75 \
  --qom-set /machine/bmi270 gyro-z 35 \
  --input drag:45,220,285,220 --input longpress:170,130,0.9 \
  --input touch:280,25 --capture-frames 18 --capture-interval 0.1 \
  --capture-each-input \
  --out-dir /tmp/m5-cores3-pelican
```

PCM 校验：

```bash
python3 tests/uiflow2/check_pcm.py \
  /tmp/m5-cores3-pelican/speaker.pcm \
  --min-nonzero 1000 --min-peak-to-peak 1000
```

![CoreS3 鹈鹕骑自行车动画](docs/images/cores3-pelican-bike.gif)

![BMI270 中立与倾斜注入对照](docs/images/cores3-pelican-bike-imu-compare.png)

![FT6336 拖拽、长按和暂停状态](docs/images/cores3-pelican-bike-touch-states.png)

[CoreS3 铃声 PCM 预览](docs/audio/cores3-pelican-bell-preview.wav)
（去除直流偏置并提高可听度的预览；原始捕获见
[`cores3-pelican-bell-raw.wav`](docs/audio/cores3-pelican-bell-raw.wav)）

公开仓库不附带官方 UIFlow2、UserDemo 或 Espressif ROM 二进制。使用
`platform/tools/fetch_firmware.py` 从 M5Stack 公开固件 CDN 下载到被忽略的本地缓存。

## 虚拟烧录

ESP32-S3、ESP32-C6 和 Tab5 的 ESP32-P4 通过 `esp-emu` 的下载模式暴露
`esptool socket://`，实际执行 `write-flash`，校验成功后再由 QEMU 启动
同一份虚拟 flash：

```bash
python3 tests/uiflow2/flash_device.py \
  --device sticks3 \
  --firmware platform/.cache/firmware/sticks3/uiflow2.bin \
  --out-dir /tmp/m5-flash-sticks3
```

Core2 使用同一 QEMU 的 ESP32 ROM UART 下载模式和 `esptool --no-stub`
写入虚拟 flash；QEMU 的 UART `baud-scale` 属性只用于仿真下载链路加速，
正常工作负载仍使用默认值。补丁见
[`patches/qemu-core2-qemu-esptool/`](patches/qemu-core2-qemu-esptool/)。

统一回归入口：

```bash
python3 tests/uiflow2/run_device_matrix.py \
  --out-dir /tmp/m5-uiflow2-device-matrix
```

它会按设备矩阵先烧录测试镜像，再启动对应虚拟后端、检查目标分辨率首帧与输入后的
画面变化、生成规范 PNG；NanoC6 检查串口标记并通过独立 runner 验证 RGB、
按键、蓝灯和 IR，CardputerZero 明确标记为非 ESP32 后端并排除。

14 台设备的虚拟主机适配分组、优先级和缺口见 [`docs/qemu-device-adaptation-matrix.md`](docs/qemu-device-adaptation-matrix.md)；机器可读注册表在 [`platform/qemu/profiles.json`](platform/qemu/profiles.json)。

列出可下载型号：

```bash
python3 platform/tools/fetch_firmware.py --list
```

下载单个型号或全部：

```bash
python3 platform/tools/fetch_firmware.py nanoc6
python3 platform/tools/fetch_firmware.py --all
```

固件缓存在 `platform/.cache/firmware/<device>/`，不会提交到 Git。

## 导出与迁移

按设备导出独立 ZIP：

```bash
python3 platform/tools/export_bundle.py --device stopwatch
python3 platform/tools/export_bundle.py --device sticks3 --device cores3
python3 platform/tools/export_bundle.py --all
```

导出包包含共享运行时、设备档案、页面、文档和当前设备目录中的固件文件，不包含本机固件缓存。输出目录默认 `dist/`，已通过 `.gitignore` 排除。

## 自动化接口

设备页面暴露：

```js
window.m5emu = {
  loadFirmware,
  loadFirmwareUrl,
  reset,
  pause,
  resume,
  press,
  touch,
  setImu,
  setBattery,
  setRtc,
  execPython,
  getFrame,
  getLog,
  getState,
  screenshot
}
```

StopWatch 参考运行时和通用设备页都兼容这组接口。设备也通过 `postMessage` 向父页面发送 `m5emu:ready` 和 `m5emu:state`。

## 设备中心接口

静态 API：

- `GET /api/devices`
- `GET /api/devices/<chip-group>/<device>`
- `GET /health`

详细契约见 [docs/device-center-adapter.md](docs/device-center-adapter.md)。

## 验证

```bash
python3 platform/tests/test_catalog.py
```

浏览器测试需要 Playwright：

```bash
cd platform/tests
npm install
npx playwright install chromium
M5_SIM_BASE=http://127.0.0.1:8080 npm test
```

自动测试会检查 14 个设备、StickS3 页面、CardputerZero 后端状态和
StopWatch 页面接口。设置 `M5_STOPWATCH_FIXTURE_URL` 后可额外验证真实固件出帧；
2026-10-21 本机已用 Playwright Chromium 通过完整固件测试。

跨设备显示旋转、输入硬断言、墨水屏局部刷新和 I2S PCM 捕获修复见
[`docs/uiflow2-cross-device-regression-audit.md`](docs/uiflow2-cross-device-regression-audit.md)。

## 外设 API 测试

StickS3、AtomS3R、CoreS3、StopWatch、StamPLC、StackChan、Cardputer-ADV、
PaperMono、PaperColor、Core2 与 Nesso N1 的 IMU、磁力计、按键、触摸、
电源、RTC、继电器、IO 扩展器、电量计、充电器、INA226/INA3221、SDMMC、
SPI SD、RMT/NEC 红外、I2C NFC、音频 PCM、PDM 麦克风、舵机和摄像头探测
结果见
[`docs/uiflow2-peripheral-test-matrix.md`](docs/uiflow2-peripheral-test-matrix.md)。

```bash
PYTHONPATH=.work/py python3 tests/uiflow2/run_peripheral_matrix.py \
  --out-dir /tmp/m5-uiflow2-peripheral-matrix
python3 tests/uiflow2/run_peripheral_matrix.py \
  --device stackchan --out-dir /tmp/m5-stackchan-peripherals
```

当前已确认 BMI270 完整配置与数据读取、BMM150 Sensor Hub、触摸/PWR、
电源与 RTC、GPIO 扩展器、INA226/INA3221、SDMMC/SPI SD 块读写、
RMT/NEC 红外收发、ST25R3916 NFC、ESP32-S3 与 ESP32 classic I2S/PDM
音频注入与抓取、SCS 舵机，以及 GC0308 + LCD_CAM + GDMA 的
`camera.snapshot()` 和屏幕显示闭环。StamPLC 的 TWAI CAN、PWR485 和
I2S 蜂鸣器也已通过虚拟对端双向验收；Nesso N1 的 BQ27220 电量计、
AW32001 充电器与双 PI4IOE 也已闭环。CardputerZero 的 IMX219 已通过
Unicam CSI1 输出由 V4L2 控制项驱动的可重复帧；GL852G MTT 兼容路径已通过
Full-Speed 以太网和 Low-Speed HID。Tab5 的 SIT3088 RS-485 已通过
UART1 半双工 TX/RX 主机对端验收；MIPI-CSI、ES8388、P4 I2S/PCM、
SDIO 等尚未闭环的外设仍按器件登记，
不会用 Python 假数据或“通用 I2C ACK”冒充完成。

Tab5 的内部 I2C 已经通过 P4 控制器实际访问 `G31/G32`：INA226 厂商 ID 和校准
寄存器、两颗 PI4IOE5V6408 的 ID/输出回读、RX8130 时间寄存器回读均通过。
INA226 场景覆盖充电 `8000mV / 1248mA / 87%` 和低电量放电
`7200mV / -501mA / 37%`；PI4IOE2 的主动低电平 CHG_STAT 也已让
`Power.isCharging()` 在充电/放电两种状态下正确返回。
Tab5 BMI270 仍只确认地址响应，且 UIFlow2 启动路径会清除预载 CHIP_ID；
实测从 `main.py` 写回 `0x24` 可成功，说明 P4 I2C 控制器和寄存器设备正常，
但还缺少真实复位/初始化状态机与动态采样，因此 Tab5 继续保持 `partial`。
所需 P4 后端接口和逐项验收条件见
[`docs/p4-peripheral-backend-requirements.md`](docs/p4-peripheral-backend-requirements.md)。

外设契约现在同时检查模型和板级后端：`simulated` 模型必须有数据面、注入
接口和已验证设备；设备只要引用 `partial/planned` 组件，就必须逐项声明
相同的阻塞模型。新增设备或外设若只实现显示/触摸，CI 会直接失败。

设备中心可直接读取完整外设清单：

```bash
python3 platform/tools/peripheral_inventory.py
python3 platform/tools/peripheral_inventory.py --device cardputer-zero --json
curl http://127.0.0.1:8080/api/peripherals
curl http://127.0.0.1:8080/api/peripherals/stackchan
curl http://127.0.0.1:8080/api/peripheral-interfaces
curl http://127.0.0.1:8080/api/peripheral-interfaces/bmi270
```

外设接口清单会把证据矩阵里的 QOM、QMP、PCM、RMT、SD、UART 和 framebuffer
操作展开成机器可读描述；设备清单中的 `runtime_cases` 则给出该设备实际需要
执行的矩阵或 external probe。

## 参考项目与致谢

本项目的多主控适配和验证流程参考了以下公开项目：

- [zqqf16/M5StopWatch-QEMU](https://github.com/zqqf16/M5StopWatch-QEMU)：
  StopWatch QEMU 适配、板级模型与早期 UI 验证思路的重要参考。
- [espressif/esp-emulator](https://github.com/espressif/esp-emulator)：
  ESP32-C3/C6/P4 RISC-V 运行时、esptool 下载接口、UART/GDB 控制能力。
- [espressif/qemu](https://github.com/espressif/qemu)：
  ESP32/S3/P4 QEMU SoC 与板级模型的源码基础。
- [m5stack/uiflow-micropython](https://github.com/m5stack/uiflow-micropython)：
  UIFlow2 固件构建、板型配置和 MicroPython API 来源。
- [m5stack/M5GFX](https://github.com/m5stack/M5GFX) 与
  [m5stack/M5Unified](https://github.com/m5stack/M5Unified)：
  显示、触摸、板型探测和设备外设路径。
- [espressif/esp-toolchain-docs](https://github.com/espressif/esp-toolchain-docs)：
  QEMU 与 esptool/ESP-IDF 联调方法的公开文档。
- [m5stack/m5stack-linux-dtoverlays](https://github.com/m5stack/m5stack-linux-dtoverlays)：
  CardputerZero 官方 Linux 设备树 overlay 来源。
- [CardputerZero/FactoryTest](https://github.com/CardputerZero/FactoryTest)：
  CardputerZero 官方外设探测、音频、摄像头和电源接口行为参考。
- [torvalds/linux `sound/soc/codecs/es8389.c`](https://github.com/torvalds/linux/blob/master/sound/soc/codecs/es8389.c)
  与 [bouffalolab/bouffalo_sdk `audio_codec_es8389.c`](https://github.com/bouffalolab/bouffalo_sdk/blob/master/bsp/common/audio_codec/audio_codec_es8389.c)：
  ES8389 寄存器布局、身份寄存器与编解码控制路径参考。
- [Linux `r8152.c`](https://github.com/raspberrypi/linux/blob/rpi-6.6.y/drivers/net/usb/r8152.c)
  与 [CoreChips SR9900A 数据手册](https://www.lcsc.com/datasheet/C521278.pdf)：
  SR9900A 的 RTL8152-compatible USB 控制、TX/RX 描述符和以太网数据面参考。
- [Genesys Logic GL852G 数据手册](https://www.lcsc.com/datasheet/C7501404.pdf)：
  `05e3:0610` 默认身份、四口 Hub 与 USB 2.0 行为参考。

各组件的许可与二进制再分发边界见
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。

## 当前边界

- 官方 UIFlow2 merged bin 不保证在仿真器中完成板级初始化。
- 除 StopWatch UserDemo 外，其余设备的 framebuffer 回传依赖对应 QEMU board model；当前 9 台 S3、Nesso N1、Core2 和 Tab5 已通过 screendump/原生 framebuffer 与输入重绘。
- ESP32-S3/C6/P4 的测试镜像通过 `esp-emu` + `esptool` 写入；Core2 通过 QEMU ESP32 ROM + `esptool --no-stub` 写入，均由测试端逐字节校验完整虚拟 flash。
- NanoC6 本身没有板载显示屏；其模拟页面以控制台和设备状态为主。
- CardputerZero 是 Linux ARM64，不是 ESP32/UIFlow2 固件目标；其官方镜像和
  当前登记的外设数据面已通过 QEMU 验证，但不能用 UIFlow2 真机状态标签描述。
- 仿真不能替代真机屏幕、音频、电源、射频、总线时序和产线烧录验收。
- 公开仓库不包含第三方固件、ROM、设备序列号或云端凭据；相关文件需按各自许可自行获取。

## License

项目原创代码与文档采用 [MIT License](LICENSE)。QEMU 补丁、内置 WASM、
产品参考图和上游代码片段继续遵循各自许可，详见
[`THIRD_PARTY_NOTICES.md`](THIRD_PARTY_NOTICES.md)。

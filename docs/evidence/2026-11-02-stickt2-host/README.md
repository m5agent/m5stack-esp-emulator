# M5StickT2（K016-T2）主机接入：FLIR Lepton 3.0 热成像 + ST7789 + I2C 编码器

日期：`2026-11-02`。范围：虚拟设备（QEMU 原生 `m5stickt2`）。物理 LWIR 光学/热测量、
Lepton 机械/电气、PDM 麦克风、Grove Unit、编码器实际接线与完整工厂 UI `NOT RUN`。
配套补丁 `patches/qemu-m5stack-peripherals/0124-stickt2-board.patch`
（base = canonical native 层 `0109` + `0110`…`0119` + main `0120`/`0121`/`0122`/`0123`，
即 QEMU 树 `acfb7f4`；fix commit `47cd598`；补丁 SHA-256 `203bdfee…`）。

## 固件来源

1) **官方 M5Burner `StickT2 User Demo`**（firmware_id `1897200000000001879`，v1.0，
   OFFICIAL，4,194,304 B，SHA-256 `bb33ffd4…`）。布局：bootloader@0x1000、
   partition table@0x8000、ota_0@0x10000/1536000、ota_1@0x190000/1536000；app 段
   结束于 0x78144，`~0x78000–0x100000` 有来源未确认的非 `0xFF` 字节（不属于任何分区，
   按原样保留、不作为已解释内容）。无 MicroPython 文件系统，**不可注入探针**。
   官方仓库 `m5stack/M5-StickT` 另有分段 app（`361f0d25…`）+ 分区表
   （`efba4421…`）作为备选来源，同样不可注入。

2) **自建 bare-metal 探针**（`tests/uiflow2/stickt2_probe`，已提交源码）：用
   Espressif xtensa-esp-elf 14.2.0 编译为 ELF（SHA-256 `8eed52a9…`），由 QEMU
   `-kernel` 直接载入新 machine；探针通过真实内存映射控制器驱动 UART0、GPIO
   bit-bang I2C（Lepton CCI @0x2A、编码器 @0x30）、classic HSPI（VoSPI）与
   VSPI（ST7789）。宿主只通过 QOM 注入编码器 delta，不向帧路径注入任何数据；
   探针从 VoSPI 包重建 160×120 热帧并打印标记。

官方 demo 的黑盒结果（确定性 icount、`-accel tcg,thread=single -icount shift=2`）：
修复 classic UART `TX_DONE` 电平位（改为锁存 + INT_CLR 清除，Arduino-ESP32
1.0.4/IDF v3 驱动需要）后，4 MB 工厂镜像可完成 ROM/二级 bootloader 并启动到
`M5StickC initializing...OK`；但在 150 s 窗口内没有观测到 Lepton CCI 命令或
VoSPI 包读取，热成像/UI 路径未到达。**因此官方 demo 只作为“同板固件可启动到
app”的旁证，数据面证据来自探针。**

## 结果（探针，2 次运行一致 PASS）

```
STICKT2_BOOT baremetal-v1
LEPTON_CCI_PING 0000
LEPTON_CCI_SERIAL 1000:1001:1002:1003:1004:1005:1006:1007
LEPTON_CCI_TEMP 30000 29950
LEPTON_CCI_SET_OK
STICKT2_PANEL_INIT 135 240
VOPSI_FRAME 0 160 120 38400 0xeef6b214 4300 9978
VOPSI_FRAME 1 160 120 38400 0x07861e5a 4311 10399
VOPSI_FRAME 2 160 120 38400 0xcdea9a2b 4322 10399
VOPSI_FRAME_ERRORS 0   (x3)
STICKT2_ENCODER 5 0    (x3, QOM 注入 increment=5 被 guest 读回)
STICKT2_PANEL_OK 135 240
STICKT2_STATUS ok
```

- **VoSPI**：classic HSPI（SCK G2 / MISO G25 / CS G0，GPIO 手动片选）读取
  164 字节包（byte0 = segment<<4、byte1 = line 0…59、bytes2–3 CRC 字段本驱动
  不校验、bytes4–163 = 80 个 big-endian 16-bit 像素）；4 段 × 60 包 = 160×120。
  连续 3 帧 guest FNV-1a digest 与宿主按模型 fixture seed 0/1/2 独立重建
  **完全一致**（`0xeef6b214` / `0x07861e5a` / `0xcdea9a2b`），且每帧 raw
  min/max 一致；0 包错误。QOM：`frames-started=3`、`segments-served=12`、
  `packets-served=720`。
- **CCI**：16-bit 寄存器地址 + 16-bit 数据字；PING、8-word FLIR 序列号、
  FPA/AUX 温度 GET（30000/29950 = 300.00K/299.50K）与 OEM sync SET
  （0x4854/0x4858）全部被 guest 驱动成功读取/写入（QOM `commands=6`、
  `gets=4`、`sets=2`）。
- **面板**：ST7789 135×240 经 VSPI（MOSI G15/SCK G13/CS G5/DC G23/RST G18）
  初始化并把热帧渲染到可见区；QMP 截图 135×240、32,400 非黑像素、89 种颜色、
  PANEL SHA-256 `eb4a8e25…`（两次运行一致）。
- **编码器**：官方示例用 I2C 0x30（指针 0x10=switch、0x00=2 字节大端 delta、
  0x20 写清 delta）；QOM 注入 increment=5 被 guest 连续 3 次读回。
- **设备矩阵**：`run_device_matrix.py --device stickt2` 以新增 `kernel` lane
  运行探针 ELF，PASS（见 matrix-summary.json）；探针细节证据
  `tests/uiflow2/stickt2_probe/evidence-2026-11-02.json`。

## 接口矛盾记录

产品文档 PinMap 把旋转编码器写成 `PA2/PA3/PA4`，但 ESP32-PICO-D4 没有这种引脚名；
官方示例 `examples/M5StickT_Lepton_opensource_v1` 通过 `Wire1` 访问 I2C 编码器
`0x30`（寄存器 0x00/0x10/0x20），并且 Lepton CCI 与 AXP192/PCF8563/MPU6886 共用
G21/G22 总线。本模型按**官方示例的可执行行为**建模：编码器 I2C 0x30；文档引脚名
视为错误并记录，不作为证据。

## QEMU 实现（0124）

- `m5stickt2` machine：ESP32-PICO-D4、4 MiB flash、无 PSRAM；复用 classic ESP32
  SoC、共享 G21/G22 soft-I2C 桥、ST7789 135×240 面板模型（VSPI，DC G23）；
  AXP192 0x34 / PCF8563 0x51 / MPU6886 0x68 / Lepton CCI 0x2A / encoder 0x30。
- `m5.lepton` 模型：**传输驱动**的 VoSPI 包流（164 字节/包；每 60 包推进一段，
  4 段一帧后按 `auto-increment` 推进 `frame-seed` 并重建确定性合成热帧）；
  VSYNC 在每段起点输出低脉冲（`vsync-width-us`，默认 1000 µs）供中断/轮询
  guest 使用；RESET 引脚复位流到 seed 帧第 1 段；CRC 字段置 0 并注明“官方驱动
  读取但忽略”。QOM：`frame-seed`/`auto-increment`/计数器/`frame-digest`。
- Lepton CCI 从设备：16-bit 寄存器文件 + 命令执行；encoder 从设备：QOM
  `increment`/`switch`。
- classic SPI 新增通用 `esp32_spi_attach_spi_slave`（guest 通过 GPIO 片选，
  USR 数据阶段按字节转发给从设备），供 VoSPI 使用；不影响 flash/panel 路径。
- classic UART：`TX_DONE` 改为锁存、`INT_RAW`/`INT_ST` 由 `INT_CLR` 清除（原实现
  从 FIFO 电平推导，Arduino-ESP32 1.0.4 驱动会永久电平中断并卡在
  `Serial.begin`）。该修复让官方 StickT2 demo 到达 app 启动标记。

## 复现

```bash
# 1) 编译探针（需要 Espressif xtensa-esp-elf 14.2.0；脚本内可用 CC/XTENSA_GNU_CONFIG 覆盖）
tests/uiflow2/stickt2_probe/build.sh platform/.cache/firmware/stickt2/probe
# 2) 探针 + 宿主 oracle/面板/编码器证据
python3 tests/uiflow2/run_stickt2_probe.py --build \
  --out-dir /tmp/m5-stickt2-probe --json-out /tmp/m5-stickt2-probe/result.json
# 3) 矩阵 kernel lane
PYTHONPATH=platform/tools python3 tests/uiflow2/run_device_matrix.py \
  --device stickt2 --out-dir /tmp/m5-stickt2-matrix
```

期望：`STICKT2_PROBE_OK` 与 `[stickt2] PASS`。

官方 demo 黑盒（可选）：

```bash
python3 platform/tools/fetch_firmware.py --firmware-id 1897200000000001879 --chip-id 0x0008
# 将 .cache/community/1897200000000001879.bin 复制为 platform/.cache/firmware/stickt2/factory-4m.bin
.qemu ... -M m5stickt2 -accel tcg,thread=single -icount shift=2,align=off,sleep=off \
  -drive file=platform/.cache/firmware/stickt2/factory-4m.bin,if=mtd,format=raw \
  -serial file:/tmp/stickt2-factory-uart0.log
```

期望：出现 `M5StickC initializing...OK`；热成像/UI 路径未到达，属 `NOT RUN`。

## 未覆盖

- 物理 LWIR 光学/镜头/曝光/热测量、Lepton 机械与电气时序；
- SPM1423 PDM 麦克风、Grove G32/G33 Unit、编码器实际硬件接线；
- AXP192/PCF8563/MPU6886 的板级数据面、按键事件与完整工厂 UI；
- 任意第三方固件、真机；不转授 StickC/StickC Plus/其它 classic ESP32 主机。

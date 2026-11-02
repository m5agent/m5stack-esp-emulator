# AtomS3R-M12（C126-M12）主机接入：OV3660 相机 + 共享官方固件路径

日期：`2026-11-02`。范围：虚拟设备（QEMU 原生 `m5atoms3rm12`）。物理光学/镜头/
曝光、DVP/SCCB 电气时序 `NOT RUN`。配套补丁
`patches/qemu-m5stack-peripherals/0122-atoms3r-m12-board.patch`
（base = 当前原生层序列 `0109` + `0110`/`0111`/`0112` + `0113`…`0120`，即 QEMU 树
`0f384fa`；fix commit `6f742e2`）。

## 固件来源（先查证，不冒充）

M5Burner 公开检索 `api/v1/firmwares?keyword=M12` 返回 4 个结果。官方 UIFlow2
没有 M12 专属条目，但 **`UIFlow2.0 AtomS3R-CAM`（firmware_id
`1897200000000003117`，v2.5.4，SHA-256 `1b29cc3d…`）的条目标述明确为
“UIFlow2 for AtomS3R-CAM and AtomS3R-M12”**，且镜像内编译了 OV3660 驱动；
运行时由 esp32-camera 在 `0x3c` 自动探测 OV3660。本记录把它作为
“同一官方镜像、官方声明覆盖 M12”的路径使用，并在设备档案里显式标注
“无 M12 专属 UIFlow2 条目”，不是用 AtomS3R（非 CAM）固件冒充。

另一条独立固件路径（黑盒）：M5Burner `AtomS3R-CAM M12 User Demo`
（firmware_id `1897200000000000208`，v0.1，发布 2024-11-11，OFFICIAL，
2,413,726 bytes，SHA-256 `96b9acc6…`）下载、静态分析并在同一机器上启动；
它不是 MicroPython/UIFlow2 镜像（无 VFS、无法注入 console 探针），因此
只作为 OV3660 控制面黑盒证据。

## 结果

### 1) 官方共享 UIFlow2 镜像：完整虚拟设备相机数据面 PASS

```
M12_BOARD 144
M12_I2C_SCAN ['0x8', '0x10', '0x3c', '0x68']
M12_PID 3660
M12_INIT True
M12_CAPTURE_BYTES 153600
M12_FRAME_SHA256 09c8ded08e8164eb6e6fe6a2a3f54fb2d6d1eed7930ab64e0802c1371c9a0696
M12_GEOM QQVGA 1 160 120 38400 94203cc2…bae69034
M12_GEOM VGA 10 640 480 614400 94a147ff…6fa6e412
M12_GEOM HD 13 1280 720 1843200 990f35de…25d5fec3
M12_GEOMETRY_DONE 3 3
M12_STREAM_CAPTURED 5
M12_STREAM_BYTES_OK 5
M12_STREAM_DISTINCT 5
M12_STATUS ok
```

- guest 通过 machine.I2C（16-bit 寄存器写地址）读到 OV3660 PID `0x3660`；
- 原厂 `camera.init()`（默认 QVGA）返回 True，`capture()` 返回 153,600 B；
- QQVGA/QVGA/VGA/HD 四档帧的 guest SHA-256 与宿主按 LCD_CAM 确定性 DVP
  波形重建一致（QVGA 为向后兼容的单帧基线，其余为 `M12_GEOM`）；
- QOM `auto-increment` 下连续 5 帧 digest 互异且各自等于重建的 scene seed 0–4
  帧（无撕裂/半帧）；宿主 oracle
  `tests/uiflow2/atoms3r_m12_console_test/frame_oracle.py` 对两次独立矩阵运行均输出
  `M12_FRAME_ORACLE_OK geometry=4 stream=5`。
- 设备矩阵 `run_device_matrix.py --device atoms3r-m12 --flash-transport direct`
  两次运行均 PASS。

### 2) 社区/官方 User Demo（黑盒）：OV3660 控制面确认，数据面未建模

M12 User Demo 镜像在 `m5atoms3rm12` 上启动后（UART1 应用日志）：

```
[I] get 0x10 / get 0x3c / get 0x68 / device num: 3
[I] bmi270 init ok / bmm150 init ok / ir init
[I] camera init
I (910) camera: Detected camera at address=0x3c
I (912) camera: Detected OV3660 camera
I (912) camera: Camera PID=0x3660 VER=0x00 MIDL=0x00 MIDH=0x00
I (1150) cam_hal: cam config ok
[I] usb_webcam: Selected Camera Board M5STACK AtomS3R-CAM
[I] usb_webcam: Service uvc started
```

即该 demo 自带的 esp32-camera（硬件 I2C port1，SCCB 引脚 12/9）在真实寄存器
路径上识别并初始化了我们建模的 OV3660；它的板级 I2C 扫描恰好得到
`0x10/0x3c/0x68` 三个器件，和机器清单一致。

限制：demo 选择 MJPEG UVC 输出，而 LCD_CAM 模型只提供 UIFlow2 路径使用的
确定性 RGB565 DVP 波形（无 JPEG 编码器），因此 `cam_hal` 报 `NO-SOI`，
应用随后以 `rst:0x3 (RTC_SW_SYS_RST)` 周期性自复位（30 s 内 21 次 NO-SOI、
23 次复位）。**社区 demo 的完整应用/UVC/Web 行为、MJPEG 数据面均 `NOT RUN`**；
该镜像只用于证明 OV3660 的 SCCB/ID/初始化控制面在第二条独立固件路径上成立。
demo 镜像为 8 MiB flash 的 sparse merged image（bootloader@0、分区表@0x8000、
factory app@0x10000，project `usb_webcam`，IDF v5.1.4，无文件系统），需以
`0xFF` 补齐到 8 MiB 后交给 QEMU；应用启动会写 NVS，因此每次运行都要从未
修改的 sparse 镜像重新补齐（pristine padded SHA-256 `dffada54…`）。

## QEMU 修复（0122）

- 新 machine `m5atoms3rm12`：复用 AtomS3R-CAM 的控制器/GC9107 面板/N8R8
  8 MiB PSRAM/LCD_CAM/专用 SCCB 桥，仅按 M12 硬件清单挂
  BMM150 `0x10`、BMI270 `0x68`、OV3660 `0x3c`（AtomS3R-CAM 模型里的
  LP5562/ES8311/PI4IOE 不属于 M12，未挂载）；
- OV3660 I2C 从设备模型：16-bit SCCB 寄存器空间（写 = 地址高、地址低、数据；
  读 = 先写地址再独立读事务），只读 PID `0x300A/0x300B = 0x3660`，
  `0x3008` bit7 软复位，`0x3808-0x380b` 输出宽高解析后发布给 LCD_CAM，
  由 LCD_CAM 在 `CAM_START` 锁存；
- 数据面仍由 LCD_CAM/DVP 合成帧 + 宿主重建 oracle；没有 host 造帧、
  注入帧数据或伪造 PID（QOM 只切换帧计数行为）。

补丁校验：fix 树 `git apply --reverse --check` 通过；在 pristine
`6961d82`（0112）上按 `0113`…`0120` 顺次应用后，`git apply --check 0122`
通过，证明 base 序列成立。

## 复现

```bash
python3 platform/tools/fetch_firmware.py atoms3r-m12   # 共享官方镜像，SHA-256 1b29cc3d…
PYTHONPATH=platform/tools python3 tests/uiflow2/run_device_matrix.py \
  --device atoms3r-m12 --flash-transport direct --out-dir /tmp/m12-matrix
python3 tests/uiflow2/atoms3r_m12_console_test/frame_oracle.py \
  /tmp/m12-matrix/atoms3r-m12/serial.log
```

期望：`[atoms3r-m12] PASS` 与
`M12_FRAME_ORACLE_OK geometry=4 stream=5`。

社区 demo（可选、黑盒）：

```bash
python3 platform/tools/fetch_firmware.py --firmware-id 1897200000000000208 --chip-id 0x0009
python3 - <<'PY'   # 补到声明的 8 MiB flash（0xFF 为擦除态）
from pathlib import Path
src = Path("platform/.cache/firmware/community/1897200000000000208.bin").read_bytes()
Path("/tmp/m12-demo-8m.bin").write_bytes(src + b"\\xff" * (8 * 1024 * 1024 - len(src)))
PY
truncate -s 4096 /tmp/efuse.bin
.qemu ... -M m5atoms3rm12 -drive file=/tmp/m12-demo-8m.bin,if=mtd,format=raw \
  -drive if=none,id=efuse,file=/tmp/efuse.bin,format=raw \
  -serial file:/tmp/m12-demo-uart0.log -serial file:/tmp/m12-demo-uart1.log
```

## 未覆盖

- 物理光学/镜头/曝光/白平衡、DVP/SCCB 电气时序与驱动力；
- 社区 usb_webcam demo 的 MJPEG/UVC 数据面、UVC 枚举、Web server 与完整应用行为；
- 运行中动态改 framesize、超过 OV3660 驱动最大尺寸的请求；
- IR GPIO47、Grove G2/G1 Unit、USB CDC 控制台、任意第三方固件、真机；
- 不转授 AtomS3R-CAM、AtomS3R 或其它 S3 主机。

# Cardputer-ADV 用户固件显示、时钟与输入复核

日期：`2026-10-29`

验证类别：`virtual-device validation`。物理硬件：`NOT RUN`。

## 样本

| 项目 | 值 |
| --- | --- |
| 固件 | `GAME Piano Tiles ADV 2.0 (13.06.2026)` |
| 设备 | Cardputer-ADV |
| 完整 Flash SHA-256 | `470aabe22c27a764ac0226058a94e856fcb14d767abfb66c41582fa2ac872f0a` |
| 大小 | 4 MiB |
| 浏览器 QEMU 源码 | `40edccac415693c5130f91c01d84176ae6008566` |

该 BIN 不在仓库中。复现时使用原文件，并由
`platform/tests/test_public_qemu_cardputer_legacy_user.mjs` 校验完整 Flash SHA。

## 根因

1. 固件发布于 2026-06-13，早于 M5GFX 提交 `5f8a783f`
   (`Fix CardputerADV being misdetected as plain Cardputer`)。旧代码在
   VAMeter 探测时覆盖了 GPIO 探测结果，因此后续 ADV 位判断永远看到 `0`，
   串口输出 `auto detect board:14`。这是固件缺陷；同一份软件在真实
   Cardputer-ADV 上也会选择旧矩阵键盘路径。
2. QEMU 面板初版把 240×320 控制器内存裁成 320×240，再使用错误的横向
   偏移。应用切到 135×240 竖屏窗口后只显示左侧 135 像素。
3. ESP32-S3 模拟 eFuse 没有有效的 ADC curve-fitting 校准字段，导致
   `adc_cali_create_scheme_curve_fitting()` 持续报错。
4. 浏览器在启动后没有主动聚焦设备 canvas；但本样本更主要的输入失败原因
   是第 1 项固件误识别。

## 修复与验证

- 完整 Flash 的 S3 profile 注入合成 ADC calibration eFuse。该值只用于虚拟
  设备曲线拟合，不声称物理 ADC 精度。
- Cardputer-ADV 面板保留 240×320 控制器内存、`(52,40)` 偏移、MADCTL
  和 glass rotation 1，原生帧覆盖完整 240×135；浏览器根据 panel
  `logical-orientation` 检测 135×240 竖屏窗口，并同步旋转 3D 设备和平面帧。
- TCA8418 数据面保持原路径。仅当 guest 把 G8/G9/G11 都配置成 push-pull
  输出并实际执行旧 Cardputer 矩阵扫描时，才激活旧矩阵兼容输入；该额外
  路径把同一物理按键状态送入 G13/G15/G3/G4/G5/G6/G7。
- 本固件在兼容路径下仍输出 `auto detect board:14`，这是上游固件旧版
  M5GFX 的已知行为，不是新的板型误判。固件升级到包含 `5f8a783f` 的
  M5GFX 后应输出 board 24。

实际浏览器结果：

| 检查 | 结果 |
| --- | --- |
| 串口 ADC calibration 错误 | `0` |
| 原生 QEMU 帧 | `240×135`，全部像素区域有内容 |
| 平面帧 | `135×240`，方向正常，无黑边裁切 |
| 3D 设备 | 自动旋转 `-90°`，屏幕方向与平面帧一致 |
| `Enter` | 保持 500 ms 后触发画面切换；前后帧序号差 `23` |
| 5.0126 s 墙钟 / 5.0119 s 虚拟时间 | 比例 `0.999856` |

其它主机核查：

- `test_public_qemu_profiles.mjs` 遍历所有已登记 S3 profile，确认同一组合成
  ADC calibration 字段存在；没有发现另一块 S3 需要不同的 eFuse 字段。
- `test_model_shell.mjs --case controller:cardputer-adv` 与
  `controller:stamplc` 均通过，确认新增设备旋转接口没有破坏另一块
  240×135 设备模型。
- CoreS3 默认 `div8` 和 Core2 确定性 `icount` 是有意执行 profile；不能用
  Cardputer-ADV 的 wall-clock 比例覆盖。

## 复现

```bash
python3 platform/tools/bootstrap_qemu_browser_runtime.py --check
python3 platform/tools/build_public_site.py \
  --output .work/public-site \
  --base-path /m5stack-esp-emulator/ \
  --qemu-runtime .work/qemu-browser-runtime \
  --littlefs-runtime .work/browser-littlefs
M5_PUBLIC_SITE=.work/public-site \
M5_USER_FIRMWARE=/path/to/PianoTilesADV-2.0.bin \
M5_USER_FIRMWARE_SHA256=470aabe22c27a764ac0226058a94e856fcb14d767abfb66c41582fa2ac872f0a \
M5_PUBLIC_BASE_PATH=/m5stack-esp-emulator/ \
M5_PUBLIC_QEMU_OUT=.work/cardputer-user-firmware \
node platform/tests/test_public_qemu_cardputer_legacy_user.mjs
```

另通过：

- `test_public_qemu_profiles.mjs`
- `test_public_qemu_instance.mjs`
- `test_public_qemu_runtime.mjs`
- `test_public_qemu_entry.mjs`
- `test_model_shell.mjs --case controller:cardputer-adv`
- `test_model_shell.mjs --case controller:stamplc`
- `runtime_coverage.py --check`
- `peripheral_catalog.py --check`
- `qemu_profiles.py --check`
- `project_snapshot.py --check`

## 边界

- 本记录不证明物理 LCD 光学方向、色域、背光、键盘电气特性或真机时序。
- 旧矩阵兼容仅在 guest 明确执行旧扫描模式时启用，不能用于宣称 ADV 硬件
  原生兼容旧 Cardputer 键盘。
- 其它 S3 板型共享 ADC eFuse 修复和虚拟时钟基线；每块板仍需独立固件、
  输入和显示路径验证。
- CoreS3 的默认 `div8` 与 Core2 的确定性 `icount` 是有意 profile，不继承
  Cardputer-ADV 的墙钟比例。

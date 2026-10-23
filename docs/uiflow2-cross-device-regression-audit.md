# UIFlow2 跨设备显示、输入与音频回归审计

日期：`2026-10-21`

> 历史证据：本文固定记录当轮跨设备假阳性修复和截图。后续全矩阵、
> Core2 零重试和统一运行时结果见
> [项目当前状态](project-status.md)。

本轮从 CoreS3 鹈鹕动画暴露的问题出发，检查同类故障是否会静默影响其他
虚拟主机。所有结论均为 QEMU 仿真验证，不是真机验收。

## 1. 屏幕旋转与绘图区裁切

M5GFX 的 `offset_rotation` 会改变某一 rotation 对应的逻辑尺寸：

- CoreS3、StackChan 和 Core2 的 ILI9342 配置为 `offset_rotation=3`；
- rotation `0` 实际是 240x320，不是横屏 320x240；
- 三台设备的 UI 测试均改为 rotation `1`。

复测前，Core2 和 StackChan 的蓝色边框最大 x 坐标为 `239`，最右 80 列完全
没有绘图；修正后蓝色边框恢复到 `x=314`。CoreS3 同样恢复了完整 320 列。

其余设备检查结果：

| 设备 | 目标尺寸 | 可见边框/页面范围 |
| --- | --- | --- |
| StopWatch | 466x466 | `(5,5)` 到 `(461,461)` |
| StickS3 | 135x240 | `(4,4)` 到 `(130,235)` |
| AtomS3R | 128x128 | `(3,5)` 到 `(123,125)` |
| Cardputer-ADV | 240x135 | `(3,3)` 到 `(235,130)` |
| StamPLC | 240x135 | `(3,3)` 到 `(235,130)` |
| PaperColor | 400x600 | 完整页框和底部彩色测试块 |
| PaperMono | 480x800 | 完整页框和底部触摸块 |
| Nesso N1 | 135x240 | `(2,2)` 到 `(131,236)` |
| Tab5 | 1280x720 | P4 专用 GDB framebuffer 测试通过 |

## 2. 输入测试假阳性

旧矩阵只要求输入前后截图哈希不同。Core2 曾出现：

- 触摸计数仍为 `0`；
- UI 正在重绘，半帧内容发生变化；
- 矩阵因此误报 PASS。

修复后：

- 触摸设备使用 1 秒 `longpress`，给 QEMU 中的触摸轮询足够时间；
- 每个 UI 测试在 UIFlow2 识别到输入后绘制固定颜色标记；
- `device_matrix.json` 使用 `post_frame_color` 直接断言该像素；
- 不再依赖串口刷新、OCR 或单纯截图哈希。

Core2 最终截图为 `touches: 1 / last: 159,182`，且固定绿色标记命中。
StopWatch、StickS3、AtomS3R、Core3、Cardputer-ADV、StamPLC、StackChan、
PaperColor、PaperMono 和 Nesso N1 均使用同一机制复测通过。

### 外设矩阵伪 PASS

外设矩阵旧版把 `checks` 当成静态 PASS 元数据；只要 QEMU 正常退出且画面非空，
即使设备返回 `camera partial / snapshot returned None` 也会判 PASS。现已改为：

- 每个用例必须配置串口成功标记、QOM、PCM、RMT、磁盘或固定 UI 像素中的
  至少一种运行时证据；
- guest 串口出现 panic、Traceback、`status=error` 或 `FAIL` 直接失败；
- `summary.json` 的每个 check 状态由运行结果生成，并附 `evidence` 列表；
- 相机必须出现 `CORES3_CAMERA_PASS 320x240 153600 bytes`，PaperMono 电源
  必须出现 `PAPERMONO_POWER 87 4000 1`。

## 3. 墨水屏刷新

PaperColor 最初在每次按键后整屏重绘，输入后的截图可能停在第 13 次
`frame-start`，尚未执行 `frame-end`。SPI/EPD trace 证明完整帧本身能写入
120000 bytes，问题来自测试在 EPD 上高频整帧刷新。

PaperColor 测试改为：

- 启动时只画一次静态页面；
- 按键后仅刷新 `keys` 所在的小矩形和固定标记；
- 输入后等待 2 秒，而不是反复提交整帧。

修改后 before/after 都保留完整页面、绿色测试块和按键标记。

## 4. I2S PCM 捕获

ESP32-S3 原模型同时执行：

- 整个 DMA ring snapshot；
- 单描述符 completion；
- 跳过全零块；
- 按哈希去除重复块；
- 最多只写 8 次。

这些规则会让导出的 PCM 少块、乱序、丢静音或失去真实时长。ESP32 classic
路径也有重复块过滤和固定 64 次写入限制。

新增 `0004-m5stack-i2s-pcm-capture.patch`：

- ESP32-S3 DMA IRQ 模式只使用按序 descriptor completion 采集；
- 从首个非静音 descriptor 开始；
- 开始后连续写入，包括中间静音；
- 不再按哈希删除重复块；
- 以字节上限而不是写次数停止；
- ESP32 classic linked-list I2S 使用同一策略。

音频回归结果：

```text
CoreS3       PASS
StickS3      PASS
StopWatch    PASS
Cardputer    PASS
StackChan    PASS
PaperColor   PASS
Core2        PASS
StamPLC buzzer PASS
```

CoreS3 Speaker 使用 48 kHz、16-bit、mono。此前按 16 kHz 导出会同时改变
时长和音高。CoreS3 鹈鹕铃声改用确定性整数 PCM：

```text
1000 Hz 50 ms + 10 ms silence + 800 Hz 60 ms
```

最终捕获为 32768 bytes / 16384 samples，非零样本 5277，峰峰值 4476；
前 50 ms 有约 99 次符号翻转，后段约 97 次，与 1000/800 Hz 一致。

## 5. 环境与运动传感器

环境交互抽查使用 QOM 物理值注入，经真实 I2C/芯片寄存器进入 UIFlow2 API：

- CoreS3 BMI270：`0.25 / -0.50 / 0.75 g`、`10 / -20 / 30 dps`；
- CoreS3 BMM150：注入 `30 / -20 / 45 uT`，按 M5Unified 板级轴映射回读
  `30 / 19.5 / -90 uT`；
- CoreS3 LTR553：环境光 `640`；
- PaperColor SHT4X：温湿度测量与 CRC 校验 PASS；
- StamPLC LM75：`37.5 C`、raw `2580` 与 11-bit 编码一致。

CoreS3 外设、PaperColor SHT4X 和 StamPLC LM75 三个用例均为 PASS。

## 6. 验证边界

- 以上均为 QEMU 仿真，不是真实屏幕、真实触摸或真实声学验收；
- PCM 波形证据证明数字 I2S 输出，不证明物理扬声器声压或最终音色；
- 单指点击、长按和拖拽已覆盖，多点触控仍未验证；
- QEMU 构建目录与另一条外设开发会话共享，本轮避免覆盖其正在迭代的
  CoreS3/USB 设备模型。

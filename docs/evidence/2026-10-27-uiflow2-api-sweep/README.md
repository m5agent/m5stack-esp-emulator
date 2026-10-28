# UIFlow2 双主机接口审计与运行时修复

执行日期：2026-10-27 至 2026-10-28。源码起点：
`47af9e76f89912028db06d9dee0b0bcc5425c852`。验证类型：
`virtual-device validation`；物理硬件为 `NOT RUN`。

本轮从已合并主线继续处理 Core2 首帧/WLAN/LVGL 的公开最小复现，
并按用户要求扩展到 CoreS3、Cardputer-ADV 的 UI、硬件、系统/通信及
Device Service 接口审计。接口被列出、被调用或返回成功均不自动算功能 PASS。
原始私有应用归档不可用，因此不宣称原完整应用或业务已经回归通过。

## 修复及证据

- QEMU `0051–0061`：Cardputer-ADV 内部 I2C 上拉与板型识别、CoreS3
  SPI2/GDMA 显示接线、S3 WDT 配置、I2S 实际采样推进、相机 DMA/EOF、
  SPI SD 多块传输、GC0308 SCCB 分页、Canvas 分块游标、DVP 字节顺序、
  GDMA 新链/STOP/reset/RESTART 及跨通道生命周期。
- Device Service：esp-emu 就绪检查、Cardputer 源码/实时程序准入、Unit
  主机准入发现、TTL 严格校验、普通 QEMU 音频/SD 路由、触摸像素逆变换、
  BLE peer 角色与订阅生命周期、companion 清理取证。
- SDK `0001–0020` 是固定官方源码上的独立候选补丁，包括 M5UI 参数封送、
  form 编码、raw buffer 长度、图片路径、回调/继承/整数/用户数据、TLS epoch、
  USB Buffer、动画、observer 清理和 cache-entry 分配。
  默认参考固件保持冻结，stock、matching SDK、候选固件与 Python source
  override 分开记账。详见[候选补丁表](../../../patches/uiflow2-api/README.md)。

最终运行时 SHA256：
`cc21773f0ad91fa589447d3badb1eb681b74170cd8b749153f37ad23cebc70c2`。
QEMU base 为 `40edccac415693c5130f91c01d84176ae6008566`，28 个补丁、
112 个源文件通过 exact-upstream 正向、反向和往返回放。
最终完整外设矩阵 **68/68 PASS，自动重试 0**。它属于仓库回归开发路径；
固件功能测试另经隔离 Device Service 的可见 session 执行。

| 证据 | 内容与边界 |
| --- | --- |
| [runtime-regression.json](runtime-regression.json) | 最终运行时、补丁哈希、完整矩阵逐 case 的固件/源码命令、串口/帧/数据文件哈希及检查结果；不拼接旧矩阵 PASS |
| [ui-summary.json](ui-summary.json) | 原生 LVGL 1,845 个 own/module 接口的明确分母、逐项状态、stock 失败与独立候选对照；继承引用不冒充独立执行 |
| [ui-highlevel-summary.json](ui-highlevel-summary.json) | 618 个高层文档 callable、每板 Display/Canvas 实际导出、507 个 M5UI 方法槽位及分组无损表；保留 pending、文档归属错误和未执行项 |
| [display-remaining.json](display-remaining.json)、[widgets-qrcode-geometry.json](widgets-qrcode-geometry.json)、[canvas-allocation.json](canvas-allocation.json) | 字体/stream/show 实际数据与原生 QR 残影、Canvas 分配失败异常的同源对照；独立候选不替换 stock |
| [hardware-summary.json](hardware-summary.json) | 460 个公开接口 × 2 主机；最终运行时摄像头六个完整 raw 观察点与 JPEG/BMP、两板 SD/FAT 和 PCM/WAV、Canvas 像素，以及较早输入/USB 收据 |
| [hardware-cores3-status.json](hardware-cores3-status.json)、[hardware-cardputer-adv-status.json](hardware-cardputer-adv-status.json) | 两板各 460 条无损逐项审计，配置/常量/状态/数据面/失败/阻塞分别保留；`required_evidence_met` 不补足缺失的运行时身份 |
| [system-protocol-status.json](system-protocol-status.json) | 两板各 5,624 个源码/导出槽位；完整状态、原因与执行收据，不将可选外设目录和常量当作主机功能通过 |
| [tls-epoch.json](tls-epoch.json) | stock/matching SDK 的证书时间失败与 CoreS3 候选五项 CERT_REQUIRED/mTLS 对照；不转授 Cardputer 候选或其它固件 |
| [device-service.json](device-service.json) | HTTP operation 正向和边界、实际 Unit/Live/网络路径与生命周期收据；拒绝响应和元数据操作不是整机功能 PASS |

最终运行时摄像头的完整 RGB565 内容与预期场景哈希一致，BMP 解码像素完全
一致，JPEG 在独立误差阈值内。SD 包含 1536-byte 原始块、guest FAT 格式化、
8225-byte 文件同步/重新挂载及宿主独立 FAT 字节比对，源 artifact 不变。
两板 Mic 录音通过实际 I2S 路径得到 440 Hz；允许 M5Unified 的增益、去直流
和削波，不声称逐字节音频保真或物理声学测量。

## 复现与取证

入口为 [`tests/uiflow2/api_sweep`](../../../tests/uiflow2/api_sweep/README.md)，
硬件、UI、通信和 HTTP 的具体命令在各子 README。使用 Python 3.12+、
固定固件及依赖，明确独立端口、状态目录和 control token。用户的 8787
测试服务不用于本轮后续测试，不停止或重启；最终功能回归使用独立 8788。

可见会话在停止前请求 evidence ZIP，核 ZIP/hash、固件与实际运行时、串口、
帧和相关输入/控制器数据；再 `purge=0` 停止，检查历史保留、Flash 释放和
运行时/companion 生命周期。较早收据缺字段时保持其真实证据层，不倒填。
大型固件、ROM、完整串口、逐帧/PCM/磁盘、ZIP 和私密凭据留在 ignored
本地归档；本目录仅包含派生总结、哈希及可无损展开的紧凑审计表。
压缩 JSON 的 encoding/decoded SHA 在各文件中，系统表用
`compact_system_results.py --expand` 展开。

## 保留的限制

- 系统表的主机可调用且属于系统/通信范围的普通 `NOT_RUN` 为零，
  全表仍有大量未选外设/其它 lane 的 `NOT_RUN`；CoreS3 4,010、
  Cardputer-ADV 4,002。两板系统表分别保留 16/4 个 `FAIL`，`ERROR`、
  `STATE_PASS` 和继承观察也单列，不等于全接口功能通过。
- 硬件审计仍为 `AUDIT_PARTIAL`，保留磁力计、Timer.value 以及
  Cardputer IR/I2C 的原厂行为失败和其它具体模型/fixture 阻塞。
- native binding、关闭的 LVGL build feature、迭代器/回调等剩余范围
  以 UI 逐项表为准；候选补丁通过不会改写 stock 结果。
- WDT warm reboot、睡眠/唤醒/断电、多点触摸、未实现 USB OTG/端点、
  ESPNow packet/IRQ、其它相机模式及未选外设未获本轮完整功能 PASS。
- 原 issue #2/#3 的 Core2 公开最小路径证据见
  [Core2 启动记录](../2026-10-27-core2-startup/README.md)。旧 UIFlow1
  LVGL7 `RUNTIME-03` 与原私有应用不由本轮 UIFlow2 结果关闭。
- 不建立物理 RF、电气、光学、声学、时序或任意固件兼容结论。

用户要求本轮立即收尾后，不再扩展测试。高层表剩余 Cardputer Canvas 三个
逐方法结果槽及 Cardputer 无 LVGL 的两个联合声明槽保持 NOT_RUN；
M5UI 80 个 frame/input pending 与三个删除后画面 pending 不计功能 PASS。
ADV ImagePlus 四方法保留失败，原生 Image 对照同样空白，未误定为 Plus 独有缺陷。

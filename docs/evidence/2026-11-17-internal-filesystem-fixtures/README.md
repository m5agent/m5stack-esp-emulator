# 会话私有文件系统夹具

复核日期：`2026-11-17`。本页是 virtual-device validation。常驻部署、
浏览器 guest 和物理硬件为 NOT RUN。

Device Service `dbddd47db4ab8d6c66e569d98dcdcca755f14e65` 的
`storage.filesystem` API 选择可写数据分区。计划绑定已准入镜像、
原分区和夹具。服务再次核对会话私有 Flash 字节与目标区间，记录
`PREPARED` 与有效 Flash SHA。实际挂载由 guest 驱动读回。

- **UIFlow2 LittleFS**：初代 Cardputer 使用原底包 `d9e1287e…`、
  vfs 夹具 `90480900…`、preboot Flash `f121f7fa…`。StickS3
  使用原底包 `fd85648d…`、vfs 夹具 `2f845135…`、preboot Flash
  `15783cdf…`。两台在 Xtensa `bef8e5f1…` 上都列目录、读预置文件、
  写入，并经同会话复位读回。实际 retained Flash 的 vfs 区间外仍与
  原始补齐镜像字节一致。两份证据 ZIP CRC 通过并保留停止的会话。
- **ESP-IDF SPIFFS**：同一基底 `b943f008…` 加 `d53424b5…`，
  在初代 Cardputer、StickS3 和 Dial 上以 Xtensa `06db397c…`
  走标准 HTTP 会话创建。三台均列目录、读取、写入和重新挂载。
  初代 Cardputer 同会话复位后读回；没有夹具的控制会话不见预置文件。
  实测有效 Flash `6d9377a6…` 与只替换 `0x110000–0x210000`
  的预期字节匹配，两个源 artifact 与区间外字节保持不变。
  四项无效请求在分配会话前拒绝。
- **格式边界**：ESP-IDF subtype `0x83` 的 LittleFS 几何已支持主机准入，
  本轮 LittleFS guest 证据来自原 UIFlow2 `vfs`；不能转授到其他
  固件的挂载逻辑。签名、只读、加密或明确安全状态未知的布局会拒绝。
  PaperDIY CARD_DET 与外接卡不在本证据范围。

SPIFFS 运行条件和可重建源码见
[ESP-IDF 夹具](../../../tests/firmware/spiffs_partition/README.md)。
SD 导出与跨会话复用独立记录在
[原生 SPI SD 接入](../2026-11-17-spi-sd-admission/README.md)。

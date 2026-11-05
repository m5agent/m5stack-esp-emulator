# 统一 Web 工作台验收

日期：2026-11-05。验证层级：`virtual-device validation`；物理硬件 `NOT RUN`。
设计与边界见[实施计划](../../plans/2026-11-05-unified-web-workbench.md)。

## 变更

本机根入口和 Pages 使用同一工作台。主机模型旁可配置 Unit，在同页编辑、
导入、运行或中断 MicroPython，并查看已有服务会话。Unit 草稿挂到当前主机，
启动时冻结实际拓扑；无效草稿不会被当成空配置启动。既有会话只借用其视图，
停止查看不会关闭原会话；本页创建的 Preview 才由本页停止。

原生编程复用现有 Preview/revision/Run 和同 guest UART；普通旧会话保留
真实执行 CAS 和替换能力，其 API 没有独立中断。浏览器继续使用原 UART runner。
未实现的浏览器 Unit 控制器仍需要支持该 Unit 的服务，不从模型或原生结果授予
浏览器执行能力。QEMU、固件、时钟配置和既有启动缺口未改。

## 已执行

- Chrome host：18 项通过，覆盖主机装配、四个宽度、失效草稿、快速切板、
  已有会话切换与非拥有视图清理；没有运行 guest/WASM。
- 原生服务：新首页 CoreS3 + PIR，13 项通过。三次代码运行通过同 VM nonce
  核对；PIR 两次状态改变经原驱动、GPIO/QOM、串口读回。红/绿实际 framebuffer
  与主机显示像素一致；导入 UTF-8 源码与中断均通过。
- 停止前产品实际取得 ZIP，成员 CRC 与 session/固件/三次 execution 身份通过；
  UI 停止后 PID 消失、lease 释放、Flash 释放且历史保留，浏览器正常关闭。

- browser-WASM：CoreS3 完整编辑器 63 项通过，12 次 raw-paste，含未改默认源码
  两次运行、UTF-8、长源码、异常恢复、导入、暂停/继续、中断、红帧与硬复位后
  新代码。normal QMP exit 0、零 forced/fallback，iframe 前和 context 前的实际
  六个 CDP Worker targets 全部消失。单次 ready 8.151 秒只作功能观察。

精确身份与保留失败：[host 摘要](host-summary.json)、[原生摘要](native-summary.json)、
[浏览器摘要](browser-summary.json)。原生 Flash 为 `0ede4060…c7c78e8`，native QEMU
为 `6d9af027…00f39d`；browser Flash 为 `52f38f56…`，WASM 为 `96ea9f91…`，
二者没有相互借用设备结果。

原生前提失败（缺运行文件、缺 esptool、工具主版本不匹配）、观察器错误
（隐藏控件、30 秒误截创建、网络响应体 0 字节）独立保留。最终 ZIP 使用产品
实际保存的非空 Blob，核对真实 HTTP 长度和完整 CRC/执行身份，未以后停止包替代。
本轮不改 Device Service 客体 ready 阈值，不重跑十九板或原生全外设矩阵。

范围限于本轮所测设备和执行通路；不授予所有 Unit、其它固件或物理属性。

## 复现

先按仓库启动说明准备原生运行时、ROM、固定 CoreS3 参考固件及 esptool 5.x，
使用独立服务、状态目录和控制凭据；不要使用已有用户会话或保留端口。
原生测试默认只输出计划，显式执行时：

```sh
node platform/tests/test_public_unified_service_browser.mjs --execute \
  --service "$SERVICE_URL" --token-file "$CONTROL_TOKEN_FILE" \
  --out .work/unified-native-new --python "$PYTHON" --chrome "$CHROME"
```

browser-WASM 使用本仓库 exporter 的完整产物与对应源码/许可，不在服务中运行：

```sh
M5_PUBLIC_SITE="$EXPORTED_SITE" M5_PUBLIC_BASE_PATH=/m5stack-esp-emulator/ \
M5_QEMU_DEVICE=cores3 M5_WASM_CHROME="$CHROME" \
M5_PUBLIC_QEMU_OUT=.work/unified-browser-new \
node platform/tests/test_public_uiflow_guest.mjs
```

两个输出目录都必须是新的忽略目录。摘要绑定实际执行源码、固件、运行时与
profile，不能用其它导出或旧缓存的 PASS 替代。

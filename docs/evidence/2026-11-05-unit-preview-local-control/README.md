# Unit 预览与本机无 Token 编程

日期：2026-11-05。验证层级：`virtual-device validation`。物理硬件 `NOT RUN`。
[设计与范围](../../plans/2026-11-05-unit-preview-local-control.md)解释模型所有权与访问边界。

## 结果

- Chrome host：20 项通过，实际独立 Unit 模型、主机草稿、运行视图隔离、
  异步迟到清理、绘制暂停/恢复和四宽度通过。没有启动 guest。
- 无 Token 原生 CoreS3 + PIR：14 项通过。网页发出的 8 次 Preview POST
  均无 Authorization 且 Origin 与请求/页面同源；3 次程序同 VM、两次 PIR
  原驱动/GPIO/QOM/串口读回、红绿屏与主机纹理、中断、导入及停止清场通过。
  停止前实际产品 Blob 的 ZIP 成员 CRC、字节/哈希和会话/固件/执行身份一致。
- browser-WASM CoreS3：独立 Unit 目录模型保持打开，完整编辑器 65 项通过，
  包含原 12 段程序、两次默认 Run、异常恢复、中断和硬复位后新代码。
  Unit 未添加到 guest；前后保持同一目录模型。正常 QMP exit 0、零 forced/
  fallback，iframe 前和 context 前均观测到六个实际 CDP targets 全部消失。
- HTTP/context 负控：配置 Token 后缺失/错误凭据仍拒绝；无 Token 的跨源、
  恶意 Host、不同端口、非 loopback peer/监听和 mode-only Fetch 均拒绝，
  不调用 coordinator。现有 owner、revision、CAS 和错误形状不变。

## 身份与保留失败

[Host 摘要](host-summary.json)、[原生摘要](native-summary.json)、
[浏览器摘要](browser-summary.json)记录各自 source/runtime/firmware 身份与清理。
原生为 QEMU `6d9af027…`、UIFlow Flash `0ede4060…`；浏览器为 WASM
`96ea9f91…`、Flash `52f38f56…`，两条通路没有借用彼此的结果。

原生首轮 Node fetch 自动添加 mode-only 元数据，观察器 GET 被拒；后续使用
不发送 Fetch Metadata 的原始 HTTP CLI。第二轮完成实际程序与 UI 停止后，
同步 ZIP 观察器无界等待；改为原 JSON 的文件输入和有界子进程，CRC/身份
断言未减少。另纠正观察器过度要求 Fetch-Site 必须存在的条件，保留真实
Origin 同源检查。前两轮 FAIL 与清理证据独立保留，未改写为整轮 PASS。
最终原生使用已验证 Flash 缓存的独立副本，不授予 esptool 传输结论。

## 复现

准备独立 loopback Device Service、固定 CoreS3 参考固件、原生 QEMU/ROM 和
Python 依赖；明确不配置 API Token。禁止复用用户测试端口和状态目录。

```sh
node platform/tests/test_public_unified_service_browser.mjs --execute \
  --tokenless-local --service "$SERVICE_URL" --python "$PYTHON" \
  --chrome "$CHROME" --out .work/tokenless-new
```

Browser 使用 exporter 的完整静态产物与其对应源码/许可：

```sh
M5_PUBLIC_SITE="$EXPORTED_SITE" M5_PUBLIC_BASE_PATH=/m5stack-esp-emulator/ \
M5_QEMU_DEVICE=cores3 M5_UIFLOW_UNIT_PREVIEW=1 M5_WASM_CHROME="$CHROME" \
M5_PUBLIC_QEMU_OUT=.work/unit-preview-browser-new \
node platform/tests/test_public_uiflow_guest.mjs
```

两者都必须使用新的忽略输出目录。本轮不重跑全部十九板或全部 Unit，不关闭
既有 C 运行时、长期稳定性或物理边界。部署与用户原服务是否加载新 Python
需要单独回读确认，不能从源码 checkout 更新推断。

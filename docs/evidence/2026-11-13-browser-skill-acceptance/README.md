# #211 浏览器上传、输入与证据验收

结果为 **PASS，virtual-device validation (browser WASM)**，限定当前导出 UI、
固定浏览器运行时和以下两份固件。它不代表新一次 Pages 发布或原生网络通过。
逐固件、运行时、画面和取证身份见 [白名单摘要](summary.json)。

## 结果

- 原有 `6d02f466` 已实现文件选择状态、启动/首帧/应用标记分层、输入与运行映像
  双 SHA、独立 REPL 状态、下载请求状态和 Skill 的 native picker 回退说明。
- 当前导出的 CoreS3 LVGL + PIR demo 通过 49 项实际浏览器检查。真实 mouse
  down、650 ms hold、up 经 guest 触摸控制器产生 `touch_clicked`，冷启和重开
  均从 Clicks 0 更新为 Clicks 1，并匹配两块实际像素区域；按钮外负控不计数。
  PIR 的两个方向均有 QOM 读回和 guest 回显。停止时先确认 pthread 退出，
  移除 iframe 后确认所有实际 CDP Worker 目标消失，再关闭浏览器上下文。
- 原报告的 UIFlow2 v2.5.3 BIN（输入 SHA `1324f12d…`）通过 13 项检查。
  从真实文件输入启动，画面进入 Develop / Web IDE；输入 16,121,856 字节与
  补齐后 16,777,216 字节的双 SHA 分别显示并进入下载记录。
- 原版 BIN 的应用就绪自动判据仍为 `unknown`，人工及稳定 ROI 确认了官方
  页面。实际 REPL 尝试未响应，页面单独显示该状态，运行状态仍为 running，
  不产生固件运行失败 banner。下载有 `download-requested` 状态，保存的 JSON
  已解析并核对同会话与双 SHA；停止后全部六个 Worker 目标清零。
- 再以错误输入 SHA 启动被拒绝，未复用上一帧、固件身份栏或运行记录。

## 本轮修复和失败保留

首次本地测试服务器在读取缺失文件前已经写入 200 响应头，错误分支再次写 404
导致 `ERR_HTTP_HEADERS_SENT`。这属于测试基础设施失败，没有授予固件失败结论。
`test_public_qemu_guest.mjs` 现先读取文件，再写成功响应头；修复后的同一导出
通过上述 demo 浏览器验收。首次日志哈希保留，未覆盖为成功。

## 复现与边界

对固定导出设置 `M5_PUBLIC_SITE`、匹配的 `M5_PUBLIC_BASE_PATH`、独立输出目录
`M5_PUBLIC_QEMU_OUT` 与可用 Chrome 的 `M5_WASM_CHROME`，执行
`node platform/tests/test_public_qemu_guest.mjs`。原版 BIN 验收从文件输入选择摘要
中的原始 SHA，显式选择浏览器运行，依次检查官方页面、双 SHA、实际 REPL 尝试、
下载、停止清场与错误 SHA 负控。原始记录保留在忽略存储，公开摘要不含端点或身份。

Playwright 本地文件输入本轮可用；扩展的 file URL 权限错误未复现，Skill 已明确
其属于工具权限阻断及 native picker 回退，不把它当作固件拒绝。物理硬件、
浏览器公网/云端配对、其它固件 REPL 和任意其它输入方式不继承本轮结果。

# 公共 main.mpy 运行 API 证据（2026-10-27）

本目录记录 gen45 的单轮真实公共 API 验收：stock 源码循环与 MPY 拒绝、candidate 同字节入口重复运行及仅依赖更新、异常与坏容器拒绝、PIR 输入到串口/QOM/PNG，以及源码恢复。同一任务只启动 3 个可见 guest，没有自动重建重试。普通会话分别先取 ZIP 再停止；托管 Preview 交给真实 Web 页面，返回后另取最终 ZIP 再关闭。最后进程、可变 Flash、租约均释放，历史末帧精确 SHA 保留。

`runtime/preview/report.json` 保留交接时 HANDOFF READY 原结论，`runtime/finalization.json` 单独记录 Web 归还后的资源清理；不要将交接前报告误读为 Web 测试结果。Web 原报告指纹由 finalization 绑定，完整 Web 证据由相邻 Web 归档负责。

`index.json` 每行明确区分 `original`、`redacted-json`、`redacted-text`、`hash-only`、`generated`。`original_sha256`/`original_bytes` 永远描述原输入；`archive_sha256`/`archive_bytes` 描述实际归档文件。只有 `original` 两者相等。脱敏 JSON 使用 `archive_notice` 与 `document` 包装，已移除 base64 文件数据；脱敏文字有首行标记。不得称其为原字节。绝对本机目录、私网地址和 MAC 也按策略替换，并记录转换。原 ZIP、MPY、固件和 ROM 二进制不入库。原 ZIP 的 SHA/大小及每个原成员 SHA/大小保留，安全的文本和 PNG 成员从 ZIP 提取归档；含 MPY/base64 的成员单独脱敏。

所有 fixture 的原 Python 源码、`mpy-cross` 官方 commit/可执行 SHA/精确 `-s` 参数和输出 SHA 都保留在 `prepared/` 与 `reproducibility.json`。因此可重编证明同一 main.mpy SHA 和两版 dep.mpy SHA。运行环境和显式 candidate manifest base 只按 SHA 与原 API 元数据绑定；重建候选固件还需要独立的 loader 源码 patch/build provenance。一次候选 PASS 不意味着任意 stock UIFlow 固件都有 run-as-main 入口能力。

离线校验：`python3 verify_archive.py`。校验器只读当前目录，核对完整文件清单、分类、归档 SHA、所有 PNG CRC、原 ZIP manifest 到提取成员的原 SHA 对应、源码/编译 recipe 与 package identity。不会联系服务、启动虚拟机或改变设备。可选 `python3 verify_archive.py --compiler /path/to/mpy-cross`：先核对官方编译器 SHA，再在临时目录重编 5 个 fixture 并比对原 MPY SHA，仍不运行 MPY。

本结果是虚拟设备验证，物理硬件为 NOT RUN。PIR 证明 guest GPIO 驱动路径，未证明 AS312 的物理时间、电气或光学行为。LOAD 只表示 import 请求，所有 MPY API application_started/application_ready 保持 null；真实应用执行另由样本自己的 if-main、对象身份、nonce/count 和新鲜输入输出证明。

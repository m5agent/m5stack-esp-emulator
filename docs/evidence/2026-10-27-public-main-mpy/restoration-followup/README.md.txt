# gen46 正常 main.mpy 路径复验（2026-10-27）

本目录独立保留 gen46 正常 stock/candidate 复验，与相邻 gen45 API-runtime 和 Web 证据分开。两次可见 CoreS3 虚拟会话、9 次执行，其中 5 次是 main.mpy；stock 的两种入口拒绝继续保护旧程序，candidate 验同字节重复导入、仅依赖更新、正常顶层异常、PIR 输入和 loop 中断后回源码。同一个 candidate VM 的 nonce/owner 保留，MPY 计数为 1→2→3→4→5；正常 loop 收尾的 ERROR 和后续源码 owner 断言共同证明正常恢复。

本次没有新 Web 验收，也没有异常命名空间污染程序的 guest 验证。缺终结 marker 的失败构造与修复仅保留 host 证据，见 `../host-followup/`；本目录不能把该 host negative 升级为 guest PASS。gen45 的真实 Web 结果仍属于其原运行与原源码，不替换成 gen46。物理硬件为 NOT RUN。

两个会话分别先取 evidence ZIP，再停止并释放进程、可变 Flash 与租约。原 ZIP 不入库，保留其原 SHA/大小与全部 16+42 个成员的原 SHA/大小；安全文本、JSON 和 PNG 提取归档，原 MPY/固件/ROM/ELF 不入库。JSON 的 base64 文件 payload 改成原始字节 metadata，并显式分类 `redacted-json`；原 SHA 与 archive SHA 分开，不把脱敏文件当原字节。`original` 项保持原字节。私有本机目录、私网地址、MAC 与凭据字段按既有规则脱敏。

`index.json`、`INDEX.sha256` 是完整清单与入口。`runtime/` 保存本轮响应与报告，`zip-members/` 保存安全成员，`prepared/` 与 `reproducibility.json` 保存既有官方 bytecode fixture 的源码、编译 recipe、编译器/输出 SHA 和 package identity；原始 prepared metadata 中未执行的 Preview fixture 信息不扩大本轮范围，其 Preview 源码未复制。`runner/` 保留实际 runner 与公共 helper 源码。83 项冻结产品源指纹与本轮报告对应，启动/overlay 和全平台测试日志由 `../host-followup/` 持有。

便携离线校验：`python3 -B verify_archive.py`，只读本目录，无网络、无 API、无 guest 启动。它核对所有文件/分类/归档 SHA、PNG CRC 与实际 phase/motion 像素、ZIP manifest 到每个原成员指纹、实际 HTTP execution 数、模块身份/计数/依赖、正常中断 ERROR、源码 owner 恢复、进程/Flash/租约清理和历史末帧精确 SHA。可选 `--compiler /path/to/mpy-cross` 先核对官方编译器 SHA，再于临时目录重编 5 个既有 fixture 比对 SHA，不运行 MPY。

LOAD 只说明 import 请求，不代表应用开始或就绪；本轮 MPY API 的 application_started/application_ready 仍为 null。PIR 是虚拟 GPIO/guest/QOM/frame 路径，不证明 AS312 的物理时间、电气或光学特性。各观测分次采集，不是原子快照。

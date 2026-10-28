# C/QEMU WASM 构建与浏览器入口证据

日期：2026-10-28。类别：源码构建、真实浏览器宿主/控制回归，无 guest 固件。

固定当前完整板级/Unit 补丁后，QEMU 9.2.2 实际编译链接为 WASM；Chromium
运行完整产物的版本、板型列表，并通过原 QMP 完成 capabilities/query-status。
256 MiB 初始配置的 CLI 退出码为 0；初版 QMP quit 的退出缺口已用独立诊断
定位到 C main 返回之后，显式 process-exit 修正后，版本、板型和无固件 QMP
三组均退出码 0，四个 Worker 在强制清理前自然关闭。失败轮保留，不将原生、
Rust 原型或板型枚举当固件 PASS。

- [结构化摘要与原始指纹](summary.json)
- [实验解释、复现要点与未验范围](../../qemu-wasm-port-research.md)
- [源补丁、来源和许可](../../../patches/qemu-wasm-probe/README.md)

原始构建日志、失败轮、浏览器报告和脚本保留于 ignored 实验目录，并追加到
本地工作记录。源码只保留精简 summary、hash 和补丁；不包含 ROM/Flash、
WASM/静态库、SDK、trace 或原始页面响应。没有发布站点，没有使用用户测试服务。

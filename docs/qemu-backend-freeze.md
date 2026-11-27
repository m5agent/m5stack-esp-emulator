# QEMU 后端封存记录

日期：`2026-11-26`。状态：封存（frozen），可随时重启。

本仓库的 QEMU 9.2.2 + M5 补丁后端、闭源 esp-emu（Tab5/P4）和 QEMU-WASM 浏览器
运行时自本日起停止新功能开发。新设备与新外设工作转到
[esp32sim 迁移计划](plans/2026-11-26-esp32sim-migration.md)。QEMU 只接受阻断性修复。
本页记录重启所需的全部入口，不改变任何已有验证结论。

## 封存点

| 项目 | 值 |
| --- | --- |
| 源码提交 | `54bf88b7a`（main，PR #276 合并后） |
| Git 标签 | `qemu-backend-freeze-20261126`（本地 annotated tag，未推送） |
| 已部署原生 rollout | `afd1c635fa702b201508a5d5d689cb67ed1243f3-main-1102-review-sta-activity-20261125`，`status: APPLIED`，manifest SHA-256 `9f1e23e5…c1baec519` |
| rollout 对应源码 | `afd1c635f`（main 的祖先），`source_tree` `2b862410…` |
| 原生 Xtensa QEMU | `native/qemu-system-xtensa` SHA-256 `04abc3ba8cb115919e7faebd55425c802f4f6e40b10bc3cc422c51700add728e`，上游 QEMU 源 `40edccac`，最后补丁 `0232-atoms3-lcd-gpio-probe.patch` |
| 原生 C6 QEMU | `native-c6/qemu-system-riscv32` SHA-256 `69493c4edccaab5bc24961982ddb9097dda11c9b3418f9cdc0aaa2b27ae865a4` |
| Tab5 esp-emu | `native/esp-emu-tab5-dsi` SHA-256 `633a35f993300a765634ed78a2dbcfd5ffcd5c3f2f354a2dddabeb6108240828` |
| 浏览器 WASM | [`scripts/qemu-wasm-build/sources.lock.json`](../scripts/qemu-wasm-build/sources.lock.json) 锁定 QEMU、emsdk 3.1.50、依赖与 52 个 `patches/qemu-wasm-probe` 补丁；23 个已编译 profile |

rollout 目录位于本机
`~/Library/Application Support/m5agent/native-device-rollouts/`，约 1.1 GiB。
它不入 Git（见 [部署说明](deployment.md#为什么不能提交-work)）。保留该目录及
前五个历史 rollout，不做清理。

## 保留内容

- 全部 QEMU 补丁：`patches/`（约 467 个文件）及其 README、apply 顺序。
- Device Service、Reviewer、QMP/QOM 适配：`platform/tools/`、`platform/tests/`。
- 回归用例与证据：`tests/`、`docs/evidence/`、`docs/validation-ledger.md`。
- 浏览器 QEMU-WASM：`platform/web/public-qemu-*.js`、`scripts/qemu-wasm-build/`。
- 未完成项：[Backlog](project-backlog.md) 与 [运行时缺口](runtime-model-gap-register.md)
  中的 QEMU 条目原样保留，不关闭、不改写。

## 重启步骤

1. `git checkout qemu-backend-freeze-20261126`，或在 main 上继续。
2. 原生运行时：按 [部署说明](deployment.md#部署-qemu-设备服务) 方案 A 恢复上表哈希一致的
   运行时包；或指向已部署 rollout 的 `native/`、`native-c6/`（`M5_QEMU_XTENSA`、
   `M5_QEMU_RISCV32`、`M5_TAB5_DSI_EMULATOR` 等环境变量）。
3. 浏览器运行时：`python3 platform/tools/bootstrap_qemu_browser_runtime.py`，
   按 `sources.lock.json` 校验每个归档与补丁哈希。
4. 用私有端口和状态目录启动 `platform/tools/serve.py`，先跑 `platform/tests` 全套与
   四个 validator（见根 [AGENTS.md](../AGENTS.md)），再按 [tests/AGENTS.md](../tests/AGENTS.md)
   跑受影响设备矩阵，确认与封存前一致后再恢复开发。

## 封存时的对照基线

2026-11-26 在私有 Device Service（`127.0.0.1:18941`）上用封存 rollout 运行了 CoreS3
产品文档 Arduino 示例（15 个，固件由文档源码编译）。逐例画面与输入结果、原始
ZIP 留在 `.work/esp32sim-cores3-20261126/qemu-service/`（不入 Git），作为 QEMU 与
esp32sim 的同一输入对照基线。

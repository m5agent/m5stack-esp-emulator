# CoreS3 UIFlow 工作台：精确固件正常钟后续验收

日期：`2026-11-04`。同一 CoreS3 工作台 Flash、同一 fresh 74-patch WASM 的正常钟候选完成 **54/54 PASS**。本次 click-to-ready 为 **10.971 s**，此前 div8 完整验收为 **27.483 s**。两次各一次，包含下载、组合和启动；约 `2.51×` 的观测比值不是重复性能基准，也不证明 CPU 吞吐或物理时序。

这是 **virtual-device validation**：真实网页编辑器经 UART0 raw-paste 驱动原 UIFlow2 VM。测试使用独立源码 overlay 和静态候选导出，`publication_eligible=false`；未发布 Pages。功能改动随后按相同内容哈希应用 canonical，但新 C 运行时仍需独立复验。`UI-03` 保持 **PARTIAL**，其余 18 款新默认 guest 和完整按键矩阵仍为 **NOT RUN**。

## 结果及同轮身份

| 项目 | 本次观察 |
| --- | --- |
| 完整编辑器 | 54/54；10 次真实 raw-paste 程序，9 次 console epoch 0、1 次 epoch 1 |
| 代码路径 | 中文与长 UTF-8 源码、多行循环、预期 SyntaxError/RuntimeError、`.py` 导入、错误后再次运行 |
| 生命周期 | 无限循环暂停/继续后真实 Ctrl-C 中断；新代码同 VM 执行；硬 reset 取消旧 owner，旧执行 AbortError，新 epoch boot 后再执行 |
| 显示 | 实际 `M5.Lcd.fillScreen(0xFF0000)` 产生 320×240 RGB565 红帧，digest `6c3c796f…3245cc86`；截图已视觉复核 |
| 正常清理 | guest exit0；5 个 nested pthread 消失时 iframe 仍保留；全部 6 个实际 CDP Worker 在关闭 context 前消失；零强制 pthread 清理、零 engine fallback、零页面错误、零 Device Service 请求 |
| 执行配置 | `cores3-wasm-uiflow-workbench-wallclock-candidate`，divisor 1、oneInsnPerTb=true；实际参数为 `-accel tcg,thread=multi,one-insn-per-tb=on`，无 icount/clock override |

| 身份 | SHA-256 |
| --- | --- |
| 完整工作台 Flash | `52f38f562f6e3749357a2ed4834efd72d16870046ea052f2f31691743cb5384d` |
| fresh 74-patch WASM | `2c72cda0858521b47e730f4d19ae4ba9de9d800d9568fa25d20d41dbd8de5d14` |
| 运行时 manifest | `80307d4f7710518d2cbda4dd308206a1c5d4b5bfcfc70257dbf2f89fece739bf` |
| guest 控制脚本 `test_public_uiflow_guest.mjs` | `f15a2888f77b4a651ce9251086e04ce1373b1a37ac6ea95502f0e3b36953294b` |
| 未修改的 provenance helper | `7a8d75a2bf4d8ce51c611530f0c69403e1b0930385f786397dcc105a12d67935` |
| 功能源码 `public-uiflow-firmware.js` | `0a44300b6c437dece030cde1bd1a76eb985e217d1671fbf63be8467ef023d8c6` |
| 功能源码 `qemu-browser-profiles.json` | `6b37e3c0f2702584383240a3e88b017fc197a2c3b9142952f5cdc1d58dada877` |
| 候选站 manifest | `2ea44afce4ee0682ac74c487083fd67dbd9e5fa8d16680bdde30898d4074a67b` |
| 原始报告，5,163,477 B | `bc8c26c6515194d5f28aa583f5ddfc980b9cb9ae95327822c8ea039ee2e30efd` |

Flash、官方基底、boot/main、运行时各资产、全部 25 个执行 web 源码/导出文件及实际输入程序的完整哈希见 [summary.json](summary.json)。原始报告、截图、固件和 ROM 不进入源码 Git；摘要只保留有界观察与身份。

## 显式源码链与精确策略

候选从项目提交 `dd9ae2a08bec4263a22b0e49c0507f9ae22ec4a3` 开始，应用两文件功能 patch（SHA `7649d6ed…a2aa7898`）。该功能只新增完整工作台 Flash 的 source-code variant，并允许 resolver 保留与工作台 `main.py` SHA、ready marker 和 `uiflow-workbench-v1` fixture 全部匹配的精确行；`0027` 的路径/哈希仍由 schema 和运行时 manifest 校验。未知 CoreS3 Flash 继续 div8，其余 18 款工作台镜像不继承此策略。

随后只在独立 overlay 将 CoreS3 admission 从 `public` 改为 `candidate`，使用原 exporter 的显式候选入口。此 preview-only transform 后的 registry 源码 SHA 为 `62f5e1ec…2eca350`，确定性筛选/排序后的导出 SHA 为 `f3d74052…e24966a`。原 capture helper 和 guest 控制脚本未放宽或改写；完整 canonical→功能 patch→preview admission→源码/导出链均在摘要。preview admission 变更未应用产品源码，profile ID 保留本次实际测试值。

功能双文件随后以表中完全相同的 SHA 应用 canonical。精确 Flash/source/main/ready/fixture、错误或缺失 `0027`、runtime patch 缺失/错误/重复、未知固件与其余 18 板不继承等正负控制已并入现有 [固件合同](../../../platform/tests/test_public_uiflow_firmware.mjs)，该合同及 profiles/runtime/entry/artifacts 五个窄 Node 合同通过。host 合同只证明选择和绑定规则，不替代新 WASM 的 guest 验收。

## 复现与范围

构建与全编辑器入口见[前轮工作台证据](../2026-11-04-browser-uiflow-workbench/README.md#复现入口与原始证据)。使用与上表功能源码 SHA 相符的独立源码 checkout，核对同轮 Flash/WASM，然后仅在该独立 checkout 中把 CoreS3 admission 设为 `candidate`，保留其余字段；从该 checkout 导出：

```sh
python3 platform/tools/build_public_site.py \
  --output .work/uiflow-candidate-site --base-path /showcase/ \
  --qemu-runtime .work/uiflow-runtime --littlefs-runtime .work/browser-littlefs \
  --qemu-candidate-profile cores3
M5_PUBLIC_SITE="$PWD/.work/uiflow-candidate-site" \
M5_WASM_NODE_MODULES="$PWD/platform/tests/node_modules" \
M5_WASM_CHROME="<system-Chrome-executable>" M5_QEMU_DEVICE=cores3 \
node platform/tests/test_public_uiflow_guest.mjs
```

测试默认执行全部检查；不设置 smoke-only。新构建、不同锁或不同导出产生新身份，必须记录自己的结果。本记录不授予其余 18 款新默认固件、全部按键、重复速度基准、任意上传应用或线上部署通过。

[前轮摘要](../2026-11-04-browser-uiflow-workbench/summary.json)中的首次 signed-array **FAIL**、旧 `3c6b2490…` 20 项 smoke PASS、同 `2c72cda0…` div8 的 54 项 PASS 全部保留；本次结果不改写这些历史观察。

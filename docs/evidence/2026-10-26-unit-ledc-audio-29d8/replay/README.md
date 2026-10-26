# LEDC readback 七补丁独立重放

日期：2026-10-26。结果：**PASS**。

在新的local shared clone中验证固定QEMU base与冻结bootstrap的完整7patch序列。未修改已有source/build，未运行新build、API、session、QEMU、guest或硬件。

## 结果

- Base commit：`40edccac415693c5130f91c01d84176ae6008566`。
- Base tree：`ddde372fbcc1b22e99f24372e14dee425be3193b`。
- Forward：逐补丁7次`git apply --check`及7次apply全部通过。
- Source：7patch的`+++ b/`完整集合恰为106文件；106/106 SHA同时匹配冷构建manifest与当前冷构建source。
- Reverse：严格7→1逐补丁7次reverse-check及7次reverse-apply全部通过。
- Final：HEAD/tree仍为base；Git status空，worktree/index diff均空；106受影响路径的文件存在性和bytes精确还原至base。
- Preservation：冷构建106源文件、binary、build manifest、bootstrap与7patch前后未变。

## 身份与范围

- 冷构建manifest SHA256：`890bc3022d28588dc09e93a7b35f460a8e414eef3ab381bd47d449c4d0198448`。
- 已有冷构建binary SHA256：`29d8f6ecdc83f4cbd2ca013291b05bc9ef44fb438a115b0ca97f7b5d46d8d28d`。
- 106源文件对照JSON SHA256：`d2352442b2531f5baf648ab80677ccdacf7d5865336c8553cfc3436b0e91dceb`。

本结果证明独立重放出的106个源文件与该冷构建清单及其当前source逐字一致。已有binary只做只读SHA绑定；没有声称在第二目录重建了bit-identical binary，也没有新增功能PASS。

Clone使用本机既有仓库object store的`--shared --no-checkout`，随后detach至固定commit；没有network fetch。重放clone保留在`qemu/`且现为clean base。它的Git对象依赖原object store；所有7patch输入与106份正向source快照另行保存在本目录，供不依赖dirty worktree的审阅。

## 证据入口

- `replay.py`：完整执行器，只向本审计目录写入。
- `receipt.json`：机器可读最终结果。
- `commands.json`与`logs/`：41条真实命令、returncode、输出SHA与原始输出。
- `inputs/`：冻结build manifest、bootstrap与7patch原始字节。
- `patches.json`、`tools.json`：补丁顺序与SHA，Python/Git工具身份与SHA。
- `forward.json`、`reverse.json`：逐步check/apply结果。
- `forward-source-comparison.json`：106逐文件三方SHA对照。
- `forward-source/`：逆序前保留的106份源文件。
- `base-source-files.json`：base时106受影响路径存在性、大小与SHA；reverse后逐项等同。
- `cold-build-source-before.json`/`cold-build-source-after.json`：既有106源文件前后一致。

## 补丁顺序

| 顺序 | 补丁 | SHA256 |
| --- | --- | --- |
| 1 | `patches/qemu-unit-runtime/0001-reconstructed-xtensa-source.patch` | `e3cefb24205dc3cc366839c56d65aa4f53e352502eced3c30ffcf248e84bd36b` |
| 2 | `patches/qemu-unit-runtime/0002-wifi-radio-lifecycle-compat.patch` | `77ee7805521fabd9ceb8b4b9683a392157fee98768333e9545824de16869933e` |
| 3 | `patches/qemu-m5stack-peripherals/0033-unit-runtime-core-and-routing.patch` | `aba1dc082746f04924cbff936bbcb7ffcd7c38ddcc5a574a21ecc1070a1ffce2` |
| 4 | `patches/qemu-m5stack-peripherals/0034-unit-i2c-sensors.patch` | `723a4ab8c5ac98a329f33f925a4a6061464aae3a0289dc431817ab9dc3a2e757` |
| 5 | `patches/qemu-m5stack-peripherals/0035-unit-i2c-controls.patch` | `5b009b4644d505085ab759effe933abe8acadeaa1b680a70fb0c18ee4915926c` |
| 6 | `patches/qemu-m5stack-peripherals/0036-core2-soft-i2c-handoff-compat.patch` | `bfb18690400f3385ccf4224e34f0021f1c5179e47f62e9b321aff6c4a06bdae8` |
| 7 | `patches/qemu-m5stack-peripherals/0037-s3-ledc-duty-readback.patch` | `7d1350423fe3b7a6e583567c3b702ceda18d1268fb9045a73269a828b619c84a` |

# Unit Glass BLOCKED 根因修复与 guest 证据（task-75）

日期：`2026-11-03`。范围：解锁 batch11 中 **glass BLOCKED** 的根因。旧证据为
main 上 `docs/evidence/2026-11-03-unit-batch11/report-glass.json`（历史 BLOCKED，
保留不改写；本 worktree base 早于该 PR，故不写相对链接，rebase 后可直接打开）。

## 结论：根因 + 修复 + PASS

- **根因**：官方 M5GFX 的 `M5UnitGLASS` 驱动**不是 SSD1309 控制字节协议**
  （`0x00` 命令 / `0x40` GDDRAM）。它使用自定义 STM32 寄存器协议：
  `writeCommand()` 发送 little-endian word，**首字节是 REG_INDEX**：
  `0x00` clear、`0x10` show、`0x20` draw string、`0x30` point、`0x40` line、
  `0x50` circle、`0x60` invert、`0x70` display on/off、`0x80` string buffer、
  `0x90` picture buffer、`0xA0` color invert、`0xB0` draw picture、
  `0xC0` buzzer、`0xD0` read key、`0xFE` firmware version；init 先写
  `0xFE` 再读 1 字节。
- 旧 QEMU 模型把首字节当作 `glass_control`，只对 `0x00/0x40` 计数，因此
  真实驱动的 `0xFE/0x90/0xB0/0xA0…` 事务全部被忽略：QOM
  `commands=0/data-bytes=0`，`panel-framebuffer` 不变——这正是 batch11
  看到的 BLOCKED 现象，不是 I2C 地址/端口/pin 问题（I2C scan 能看到 0x3D）。
- **修复**：补丁 **`0157-unit-glass-m5gfx-protocol.patch`**（base canonical
  35 层链 through 0156；下一号 0158）实现自定义协议解析：命令/数据计数、
  `0x90` picture-buffer payload 写入 GDDRAM digest、`0x10/0xB0` 页更新计数
  （新增 QOM `pages`）、显示开关、buzzer payload、`0xFE`/`0xD0` 读取 fixture。
  不宣称光学/按键/蜂鸣器语义。
- **guest 重跑**：官方 `unit/glass.py` → `M5.addDisplay` → `fillScreen/
  fillRect/print`；QOM 观测到：
  `commands=4366`、`data-bytes=13144`、`pages=44`、
  `command-hex=10`、`panel-framebuffer=8458bede`、`i2c-address=0x3D`。
  状态 **PASS**。

## 关键信息

| 项 | 值 |
| --- | --- |
| QEMU 源码 | canonical `75f1d24` + 36 层链（0120–0156）+ **0157** |
| 运行时二进制 SHA-256 | `893a8d2127d28846baa5212841255b1002b1c11e839130b83203d171761f6d65` |
| Device Service | 独立 `127.0.0.1:8821`（`.work/glass-unblock-service.port`），独立 state/token、host-image；未触碰 8787/8799/8801/8802/8803/8831 |
| 参考固件 | cores3 `platform/.cache/firmware/cores3/uiflow2.bin` |
| 路径 | 官方 M5GFX M5UnitGLASS（I2C 0x3D，PORT.A）→ 自定义寄存器协议 → QOM |

## 边界

- 这是 **virtual-device validation**，不是透明 OLED 光学/亮度/透过率验证。
- 2 个按键与蜂鸣器仍无可用内部固件协议表：按钮/QOM 静态 fixture 不宣称
  语义；蜂鸣器只记录 payload 字节，不宣称声音。
- 0x3D 与 LCD/OLED/MiniOLED/Glass2 冲突保留；一总线一显示。
- 修复只建立 controller-level 命令/数据/页更新路径；真实面板光学、物理
  按键、蜂鸣器声学、电气与真机均 **NOT RUN**。

## 复现

```bash
M5_SERVICE_FLASH_MODE=host-image \
M5_QEMU_XTENSA="$PWD/.work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa" \
M5_QEMU_XTENSA_ROM_DIR="$PWD/.work/M5StopWatch-QEMU/build/qemu/pc-bios" \
  PYTHONPATH=platform/tools python3.12 platform/tools/serve.py 8821 \
  --bind 127.0.0.1 --state-dir .work/glass-unblock-service \
  --api-token "$(cat .work/glass-unblock-service.token)"

export M5_SERVICE_API_TOKEN="$(cat .work/glass-unblock-service.token)"
PYTHONPATH=platform/tools python3.12 tests/units/run_batch11_cases.py \
  --api-url http://127.0.0.1:8821 --case glass --out-dir .work/glass-unblock-evidence
```

每 session 先 ZIP 后 `purge=0`；原始执行产物留在本地 ignored `.work`，仓库只
提交摘要、哈希与复现命令。

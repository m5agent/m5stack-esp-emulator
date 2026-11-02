# Unit batch12a 7 款 driver-gap 虚拟设备证据

日期：`2026-11-03`。范围：把 batch-12a 7 款 **无官方 Unit 驱动**的
I2C/GPIO 产品（`byteswitch`/`bytebutton`/`step16`/`timerpwr`/`mq`/
`8servos2-i2c`/`cardkb2`）通过 guest **raw machine.I2C 探针**在独立 Device
Service 的可见会话中记录为虚拟设备证据。机械/电气/光学/热学/声学语义全部
`NOT RUN`。

本页是验证证据，不定义当前能力；当前能力以
[项目当前状态](../../project-status.md) 为准。结果只覆盖表内记录的主机、固件
SHA、QEMU 二进制 SHA 和检查项，不转授未列组合。

## 关键点：driver-gap raw 探针 + 0160 证据修复

7 款都**没有官方 UIFlow2 Unit 驱动**，没有可执行的冻结驱动路径，因此 guest
探针直接使用 `machine.I2C` 读写 Unit 寄存器文件（与既有 raw-byte responder
证据同一口径）。所有结论只到字节/寄存器层。

| 项 | 值 |
| --- | --- |
| QEMU 源码状态 | canonical `75f1d24` + canonical 链 **39 层**至 `0159` + **0160（本轮证据修复）** |
| QEMU 树 | `.work/native-lock-source/qemu`（`rm -rf build` 后重新 `configure`） |
| 运行时二进制 SHA-256（签名部署副本） | `bf304e61…`（每条 report 一致） |
| 参考固件 | cores3 `platform/.cache/firmware/cores3/uiflow2.bin`（`1324f12d…`） |
| Device Service | 独立 `127.0.0.1:8804`、独立 state/token、`M5_SERVICE_FLASH_MODE=host-image`；`8787` 与占用 `8799/8801/8803/8831` 的并行服务均未触碰 |
| 探针 | guest `machine.I2C(0, scl=WHITE, sda=YELLOW)` 原始寄存器读写，无官方驱动 |

**证据修复 0160**：`0160-unit-batch12a-evidence-fixes.patch`（base canonical
39 层链至 `0159`）。MQ 的 ADC12 QOM getter 对 `sensor-mv*4095/ref-mv` 做了
截断（2233），而寄存器刷新用 `llround`（2234），导致 guest 读到的 0x08BA 与
QOM `adc12` 不一致；修复后两者都用四舍五入值。

## 结论

7 款各建 1 个可见 session（每款顺序独立 session，避免 0x48/0x56/0x11/0x25/0x5F
地址冲突），均通过 guest raw I2C 探针读写并取得 evidence ZIP，停止使用
`purge=0`：

| Unit | 地址 | guest 证据 | 结果 |
| --- | --- | --- | --- |
| `byteswitch` | 0x46 | 位图 0xA5 + ch0/ch7/FW；写亮度 0x42/模式 1/RGB 11-22-33/save/IRQ 后读回；QOM state-bitmap/rgb-hex/save/irq 一致 | PASS |
| `bytebutton` | 0x47 | 位图 0x5A + ch0/ch7/FW；同套写入读回；QOM 一致 | PASS |
| `step16` | 0x48 | position=7；写 direction 0/brightness 42/RGB 0x123456/save 后读回；QOM position/direction/rgb/save 一致 | PASS |
| `timerpwr` | 0x56 | buttons=0、电池 raw LE32 0x172（3700mV）、charging=1；写 Grove 输出/背光/12:34 定时/cycle 后读回；QOM 一致 | PASS |
| `mq` | 0x11 | valid=1、ADC8=139、ADC12=2234、NTC 10000Ω、ref 1100mV；写 mode/LED/heat 后读回；QOM 一致（valid 极性按驱动，PDF 冲突 unresolved） | PASS |
| `8servos2-i2c` | 0x28（rotary=3） | 读 UID fixture/modes/FW；写 mode 2/servo 10..17/PWM 50..57/RGB 块后读回；QOM rotary/i2c-address/servo/pwm 一致 | PASS |
| `cardkb2` | 0x5F | 读 legacy raw key=0x71、0xF1 FW=1；QOM key-code/firmware 一致 | PASS |

每个会话停止前取得 evidence ZIP，停止使用 `purge=0` 并回读保留 history。
**driver-gap caveat 已写入每条 report/profile blocker**：这些证据来自原始
`machine.I2C` 探针，不是官方 Unit 驱动路径；UART AA03/v2 report/BLE HID/
ESP-NOW（cardkb2）、机械/光学/电气/热学语义都 `NOT RUN`。

## 复现

```bash
# 1) QEMU：canonical 39 层至 0159 + 0160
rm -rf .work/native-lock-source/qemu/build
cd .work/native-lock-source/qemu && ./configure ... && ninja -j10 qemu-system-xtensa
cp build/qemu-system-xtensa ../../M5StopWatch-QEMU/build/qemu/build/
xattr -c ../../M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa
codesign --force --sign - ../../M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa
# 2) 独立 Device Service（8804）
M5_SERVICE_FLASH_MODE=host-image \
M5_QEMU_XTENSA="$PWD/.work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa" \
M5_QEMU_XTENSA_ROM_DIR="$PWD/.work/M5StopWatch-QEMU/build/qemu/pc-bios" \
  PYTHONPATH=platform/tools python3.12 platform/tools/serve.py 8804 \
  --bind 127.0.0.1 --state-dir .work/unit-batch12a-service \
  --api-token "$(cat .work/unit-batch12a-service.token)"
export M5_SERVICE_API_TOKEN="$(cat .work/unit-batch12a-service.token)"
PYTHONPATH=platform/tools python3.12 tests/units/run_batch12a_cases.py \
  --api-url http://127.0.0.1:8804 --case byteswitch --out-dir .work/unit-batch12a-evidence
```

## 未覆盖与边界

- 机械/电气/光学/热学/声学物理、WS2812/舵机/PWM 波形、INA199 精度、9-24V 供电、
  MQ-5 气体曲线/预热、RTC 长定时/电池充放、真实 FLASH 持久化：全部 `NOT RUN`；
- `cardkb2` 仅覆盖 legacy I2C 子集；UART AA03/v2 report/BLE HID/ESP-NOW 与
  PORT.CUSTOM G26/G25 准入没有验证；
- MQ valid 极性（驱动 ==1 vs PDF 0=有效）、8servos2 MCU 型号冲突、各地址冲突
  （0x48/0x56/0x25/0x26/0x5F）保持 unresolved/显式；
- 只覆盖 cores3 + 记录固件 SHA + 记录 QEMU 二进制 SHA，不转授其他主机/固件。

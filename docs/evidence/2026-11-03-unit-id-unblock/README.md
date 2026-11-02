# Unit ID（ATECC608A）解锁虚拟设备证据

日期：`2026-11-03`。范围：把 batch6b 唯一 BLOCKED 的 `unit-id`（U124，
ATECC608B-TNGTLSU-G，I2C 0x35）通过**独立 Device Service** 的可见 `/api/v1`
会话记录为**虚拟设备**证据。真实密码学/密钥/证书与物理安全语义全部 `NOT RUN`。

本页是验证证据，不定义当前能力；当前能力以
[项目当前状态](../../project-status.md) 为准。结果只覆盖表内记录的主机、
固件 SHA、QEMU 二进制 SHA 和检查项，不转授未列组合。

## 根因与修复（补丁 0156）

batch6b 证据（[report-unit-id.json](../2026-11-03-unit-batch6b/report-unit-id.json)）
显示 guest `IDUnit` 能扫描到 0x35，但冻结 ATECC 驱动在每条命令前执行
`wakeup()`：向 **I2C 地址 0x00 写 1 字节 0x00 wake token**，再读 0x35。旧模型
只绑定 0x35，wake 事务与后续命令都失败（CRC mismatch）。本轮按冻结驱动与
ATECC608A wake 语义实现最小合法路径：

| 根因 | 修复 |
| --- | --- |
| 0x00 地址 wake 事务未被 ACK/未与命令帧区分 | QEMU I2C broadcast 把 wake token 送到 Unit 从机；模型把 `0x00`（wake）、`0x01`（Sleep）、`0x02`（Idle）当作单字节控制写 ACK，不进入命令帧 |
| 驱动在「命令写」与「响应读」之间又发一次 wake token，旧模型每次 START_SEND 清空命令缓冲 | 命令帧只在下一帧的 `0x03` command word 到达时重置，跨 wake 保留 |
| 响应 CRC 与冻结驱动 `_at_crc` 算法不一致（旧为反射右移形式） | 改为 `_at_crc` 的精确算法（每字节 LSB-first、CRC bit15 比较、左移、poly 0x8005） |
| READ/SHA/NONCE/GEN_KEY 响应长度/模式未按驱动区分 | READ 返回 4B config-zone serial fixture；SHA mode 0/1 返回 ACK 状态、mode 2 返回摘要 fixture；NONCE pass-through 返回 ACK；GEN_KEY 返回 64B 公钥 fixture |
| 无 serial/wake 观测 | QOM 新增 `serial-hex`/`wake-count`/`idle-count`/`sleep-count`/`read-commands`/`tx-bytes`/`last-command-hex` |

补丁：`patches/qemu-m5stack-peripherals/0156-unit-id-atecc-wake.patch`
（sha256 `c8e88bd4…`，base canonical 35 层链至 `0154`，36th layer after 0120）。

## 会话结果

| 项 | 值 |
| --- | --- |
| Device Service | 独立 `127.0.0.1:8802`、独立 state/token、host-image；`8787` 与占用 `8799`/`8801` 的并行服务未触碰 |
| QEMU 源码状态 | canonical 35 层链至 `0154` + `0156` |
| 运行时二进制 SHA-256（签名） | `aec121a0…` |
| 参考固件 | cores3 `uiflow2.bin`（`1324f12d…`） |
| 会话 | 1 个可见 session，guest 内运行冻结 `unit/id.py` + `driver/atecc608b_tngtls/atecc.py`；先 ZIP 后 `purge=0` |

guest 输出与 QOM fixture **完全一致**（固定非敏感测试向量）：

| 命令/API | guest 结果 | QOM fixture |
| --- | --- | --- |
| `get_revision_number()` | `0x260` | `revision=0x0260` |
| `get_serial_number()` | `101112131415161718`（READ 0x00/0x02/0x03） | `serial-hex=101112131415161718` |
| `get_sha256_hash("M5STACK-ATECC-TEST")` | `aabbccdd0102030405060708090a0b0c0d0e0f101112131415161718191a1b1c` | SHA digest fixture |
| `get_generate_key(0)`（PUBLIC） | `3031…6f`（64B） | GEN_KEY public-key fixture |
| `randint(0,100)` | 20（在 0..100 范围内） | RANDOM fixture（32B，`1011…2f`） |

计数：`wake-count=28`、`idle-count=10`、`read-commands=3`、`transactions=57`。
`randint` 的**精确整数映射**未断言：冻结固件的整数变换与公共源码公式不同，
只断言公开范围语义；原始 RANDOM fixture 字节是固定非秘密向量。

## 复现

```bash
rm -rf .work/native-lock-source/qemu/build
cd .work/native-lock-source/qemu && ./configure ... && ninja -j10 qemu-system-xtensa
cp build/qemu-system-xtensa ../../M5StopWatch-QEMU/build/qemu/build/
xattr -c ../../M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa
codesign --force --sign - ../../M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa
M5_SERVICE_FLASH_MODE=host-image \
M5_QEMU_XTENSA="$PWD/.work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa" \
M5_QEMU_XTENSA_ROM_DIR="$PWD/.work/M5StopWatch-QEMU/build/qemu/pc-bios" \
  PYTHONPATH=platform/tools python3.12 platform/tools/serve.py 8802 \
  --bind 127.0.0.1 --state-dir .work/unit-id-service-8802 \
  --api-token "$(cat .work/unit-id-service-8802.token)"
export M5_SERVICE_API_TOKEN="$(cat .work/unit-id-service-8802.token)"
PYTHONPATH=platform/tools python3.12 tests/units/run_batch6b_cases.py \
  --api-url http://127.0.0.1:8802 --case unit-id --out-dir .work/unit-id-evidence
```

## 未覆盖与边界

- 所有真实密码学：ECDSA/AES-GCM/Trust&GO 证书链、key-slot 锁定/权限、10Kb
  EEPROM、生产密钥/证书均 `NOT RUN`/树内不存在；响应全部是固定非秘密测试向量。
- ATECC608A 的 Sleep/Idle 状态机只实现为单字节 ACK 与计数；general-call 内容
  语义、wake 时序（tWHI 等）、物理安全（防篡改/侧信道）`NOT RUN`。
- 只覆盖 cores3 + 记录固件 SHA + 记录 QEMU 二进制 SHA，不转授其他主机/固件。

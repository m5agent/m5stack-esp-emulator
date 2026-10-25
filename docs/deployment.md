# 部署与运行时资产

最近核对：`2026-10-25`

## 结论

`.work/` 不随 Git 仓库发布，这是预期行为，不是 clone 缺文件。它是本机的
构建、工具链和运行时缓存，`.gitignore` 从第一版就排除了整个目录。完整
运行时的常见规模是数十 GiB，以实际 checkout 和市场/设备组合为准，包含
QEMU 构建树、ESP-IDF、Python 依赖、ROM/eFuse、参考固件和其他生成文件；
其中一部分是平台相关二进制或第三方资产，不适合也不能作为普通源码提交。

部署前先确认目标模式：

| 模式 | 可用能力 | 必需资产 | 启动方式 |
| --- | --- | --- | --- |
| 目录/只读 API | 设备目录、`GET /api/v1/devices`、OpenAPI、静态文档 | 仓库源码、Python 3 | `./start.sh` |
| QEMU 设备会话 | lease、烧录、串口、画面、输入、QOM、外设测试 | 源码、Python 3、完整 `.work/`、参考固件 | 准备运行时后运行 `./start.sh` |

只 clone 仓库属于第一种模式。设备目录仍会返回登记设备（当前数量见
[自动项目快照](project-snapshot.md)），但缺少运行时的 QEMU 设备
`backend_ready` 和 `creatable` 会是 `false`；创建会话会返回
`503 backend_not_ready`。

## 为什么不能提交 `.work/`

- 目录通常有数十 GiB，复制和升级都不适合走 Git。
- QEMU、`esp-emu` 和 Python 扩展与操作系统及 CPU 架构相关。
- QEMU、ROM/eFuse、Espressif 工具链、参考固件和生成镜像有各自的许可及
  再分发边界。
- 本地 `.work/` 可能包含调试版本、临时二进制或不可复现的中间产物。

公开仓库只发布源码、补丁、设备契约和可复现的测试入口。不要为了让 clone
“看起来完整”而提交 `.work/`。

## 只部署目录页

目标机只需要 Python 3：

```bash
git clone https://github.com/m5agent/m5stack-esp-emulator.git
cd m5stack-esp-emulator
python3 platform/tools/serve.py 8787
```

以下请求应返回 `200`：

```bash
curl -fsS http://127.0.0.1:8787/health
curl -fsS http://127.0.0.1:8787/platform/web/
curl -fsS http://127.0.0.1:8787/api/v1/devices
```

这个模式不执行固件，也不需要 `.work/`、ROM、eFuse 或参考固件。

## 部署 QEMU 设备服务

当前仓库还没有一个已签入的 `bootstrap` 脚本可以从空目录自动重建全部
运行时。部署必须使用下面两种受控路径之一，不能假设 upstream
`M5StopWatch-QEMU` 的通用 release 已包含本仓库的全部板型和外设补丁。

网络隔离和 pcap 还需要目标机具备 QEMU `filter-dump`，Linux worker 还需要
创建 private network namespace 的系统权限，以及 `iproute2`、`nftables`
和 `CAP_NET_ADMIN`/`CAP_SYS_ADMIN`。外部 IPv4 allowlist 要求
`net.ipv4.ip_forward=1`，外部 IPv6 allowlist 还要求
`net.ipv6.conf.all.forwarding=1`；每个 session 会创建临时 IPv4/IPv6
veth 路由和 `inet` NAT table，并在停止/失败时清理。依赖或规则安装失败会
fail-closed，不能用宿主网络继续启动。模块和证据入口见
[代码与验证入口地图](code-map.md)。

### 方案 A：恢复匹配的运行时包

从可信构建机准备一个与目标主机操作系统、CPU 架构和仓库 commit 匹配的
运行时包，保持本仓库的相对路径不变。至少检查：

```text
.work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa
.work/M5StopWatch-QEMU/build/qemu/pc-bios/
.work/M5StopWatch-QEMU/build/qemu-c6/build/qemu-system-riscv32
.work/M5StopWatch-QEMU/build/qemu-c6/pc-bios/
.work/bin/esp-emu
.work/py/
```

Tab5、网络和扩展测试还需要设备矩阵声明的 `esp-emu`、P4 ROM/eFuse、
`.work/esp-emu-versions/0.50.0/` 和 `.work/roms/`。参考固件位于
`platform/.cache/firmware/<device>/`，可通过
`python3 platform/tools/fetch_firmware.py <device>` 单独准备。

运维上建议把 `.work/` 做成版本化 runtime image 或归档，并记录生成它的
仓库 commit、主机架构、补丁清单、校验和及测试结果。不要直接把某台开发机
的 macOS arm64 目录复制到 Linux x86_64 主机。

当前提供一个已验证的 macOS arm64 起步包：

- Release：<https://github.com/m5agent/m5stack-esp-emulator/releases/tag/runtime-macos-arm64-2026.10.25>
- Asset：`m5stack-esp-emulator-runtime-macos-arm64-2026.10.25.tar.gz`
- SHA256：`735464198c5f7f3ffa930307c0e4cedb973ac48934b73d0092a3a4659831c7a9`
- Source commit：`10df26ece0b605a3a8bb36a3661b53494fdae9a0`
- 运行要求：macOS arm64 + Python 3.13

从仓库根目录安装：

```bash
curl -fL \
  -o /tmp/m5stack-esp-emulator-runtime-macos-arm64-2026.10.25.tar.gz \
  https://github.com/m5agent/m5stack-esp-emulator/releases/download/runtime-macos-arm64-2026.10.25/m5stack-esp-emulator-runtime-macos-arm64-2026.10.25.tar.gz
shasum -a 256 /tmp/m5stack-esp-emulator-runtime-macos-arm64-2026.10.25.tar.gz
tar -xzf /tmp/m5stack-esp-emulator-runtime-macos-arm64-2026.10.25.tar.gz \
  --strip-components=1
PYTHONPATH="$PWD/.work/py${PYTHONPATH:+:$PYTHONPATH}" \
M5_CORE2_RADIO_QEMU="$PWD/.work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa" \
python3 platform/tools/serve.py 8787
```

该包包含 xtensa/riscv32 QEMU、必要 ROM、`esp-emu 0.50.0`、Python 3.13
依赖和 runtime manifest，不包含 M5Stack 参考固件。参考固件仍按设备使用
`fetch_firmware.py` 获取，或通过 `/api/v1/artifacts` 上传匹配镜像。

这不是 clean-room 源码重建，也不覆盖 Linux/Windows。它解决的是“第三方
拿到当前 commit 后无法直接启动 QEMU 后端”的可执行运行时缺口；源码重建路径
仍见方案 B。

Device Service 默认使用设备矩阵登记的 QEMU 可执行路径。Linux worker 或
容器中需要替换同一 commit 重新构建的二进制时，可设置：

| 环境变量 | 后端 |
| --- | --- |
| `M5_QEMU_XTENSA` | `qemu-esp32s3` 与 `qemu-esp32lx6` |
| `M5_QEMU_RISCV32` | `qemu-esp32c6` |

值可以是绝对路径，也可以是相对仓库根目录的路径。该覆盖只替换 QEMU
可执行文件，不替代匹配的 `pc-bios`、ROM/eFuse、参考固件或 target smoke
test；主机架构不匹配时仍必须拒绝启动。worker-local namespace fixture 会在
`--qemu-path` 时自动设置 `M5_QEMU_XTENSA`。

### 方案 B：从固定源码和补丁重建

重建需要：

- Espressif QEMU 的固定 tag/commit 和 `patches/` 下适用于该 checkout 的
  补丁序列；
- `M5StopWatch-QEMU` 的构建脚本与 ROM/eFuse 资产；
- S3、C6 和 P4 对应的 `esp-emu` 版本；
- esptool、littlefs-python、Bumble 等 `.work/py` 依赖；
- 每台设备的参考 UIFlow2 固件。

不同补丁有明确的基线和顺序，见
`patches/qemu-m5stack-peripherals/README.md` 和各子目录 README。重建后必须
保留完整构建证据，并在目标架构上跑设备级 smoke test。当前缺少这条路径的
一键脚本，因此不要把“已经 clone”当成“已经具备运行 QEMU 的条件”。

## 验证

服务启动后检查设备是否可创建：

```bash
curl -fsS 'http://127.0.0.1:8787/api/v1/devices?include_unsupported=1'
```

对目标设备确认：

```json
{
  "backend_ready": true,
  "creatable": true,
  "reference_available": true,
  "missing_runtime_files": []
}
```

最后创建一次真实 lease，并确认状态能从 provisioning 进入 running：

```bash
curl -sS -H 'Content-Type: application/json' \
  -d '{"device_id":"sticks3","ttl_seconds":60}' \
  http://127.0.0.1:8787/api/v1/sessions
```

## 常见错误

| 错误 | 含义 | 处理 |
| --- | --- | --- |
| `503 backend_not_ready` | QEMU/esp-emu 后端文件缺失 | 查看响应的 `missing` 和本文运行时清单 |
| `409 reference_firmware_missing` | 后端存在，但参考固件未缓存 | 运行 `fetch_firmware.py <device>` 或上传匹配固件 |
| 会话启动后立即退出 | 后端或固件不匹配 | 检查 session 日志、串口、固件芯片/板型及目标架构 |

只读目录部署没有运行时文件时仍可正常使用。若页面能打开但会话总是
`503`，应把它归类为“QEMU 运行时未 provision”，而不是 Git 仓库损坏。

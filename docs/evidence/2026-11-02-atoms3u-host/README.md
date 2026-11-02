# AtomS3U（K125）虚拟主机接入（限定验证）

日期：`2026-11-02`。范围：把视觉库存中仅有外壳的 AtomS3U 接入为独立
原生 QEMU 主机，并记录**虚拟设备**证据；物理硬件、RF、光学与声学
`NOT RUN`。

## 结论

- 新增机器 `m5atoms3u`（独立板级，不是 AtomS3 Lite 别名）。
- 官方 UIFlow2 `v2.5.4`（firmware `2099000000000000005`，SHA-256
  `7b8742931a2f88015a3419ba7aee22dfa56abd2c17c742426289a890f715ce1a`，
  8,384,512 bytes）在同一 guest 内启动到 Python 探针并输出：

  ```
  ATOMS3U_BOOT_FLAG
  ATOMS3U_MAIN_START
  ATOMS3U_M5_BEGIN_OK
  ATOMS3U_BOARD 138
  ATOMS3U_RGB 0x204060
  ```

- 启动日志里 `i2c.master: this port has not been initialized` 出现在探针
  之前；AtomS3U 没有板载 IMU，这是固件探测未命中后的信息性日志，未阻止
  `M5.begin()`、板级识别和 RGB 写入。
- QOM 侧同一会话观测：`/machine/onboard_io` 的 `led-frames=4`、
  `/machine/rmt0` 的 `tx-completions=4`、`tx-symbols=96`、`tx-errors=0`，
  说明 RGB 帧经过真实 RMT/GPIO 矩阵路径，而不是 host 端直写。
- GPIO41 按键经 QMP `input-send-event` 注入后 `/machine/onboard_io` 的
  `pressed` 由 `false` 变 `true` 再回 `false`，`input-events=1`。

## 复现

```bash
# 1) 下载官方固件到本地缓存
python3 platform/tools/fetch_firmware.py --firmware-id 2099000000000000005 --chip-id 0x0009

# 2) 运行设备矩阵中的 console case（本机自建 QEMU 见下）
PYTHONPATH=platform/tools python3 tests/uiflow2/run_device_matrix.py \
  --device atoms3u --flash-transport direct --out-dir /tmp/atoms3u-matrix
```

运行产物（不入 Git）：镜像 SHA-256
`f25500c3b8c5cfa130084c669e7542653f4fe4e383dec384b2e849fd4090d0c3`，
串口 `/tmp/atoms3u-matrix/atoms3u/serial.log`。

## 运行时来源

本机自建运行时：`espressif/qemu` commit
`40edccac415693c5130f91c01d84176ae6008566`，按
`scripts/qemu-wasm-build/sources.lock.json` 的原生层顺序（到 `0109`）应用
补丁，再叠加本目录 `patches/qemu-m5stack-peripherals/0110-atoms3u-board.patch`。
构建产物 `qemu-system-xtensa` SHA-256
`6d9af027e2f744208fc2503128f1772f436d7ca7358f9e53be597bc76800f39d`。

`run_device_matrix.py` 的 console 模式新增 `serial_index`：
NanoC6 仍用第三路（UART2），AtomS3U 显式使用第一路（UART0）。

## 未覆盖

- IR GPIO12 发送/接收数据面未验证；只有引脚归属的官方证据。
- SPM1423 PDM 麦克风没有控制器级模型，guest 读取保持不可用，不返回合成 PCM。
- Grove(G2/G1) 的 Unit 数据面未验证；本目录只登记了接线入口。
- USB Type-A/CDC 控制台、任意第三方固件、物理光学/声学与电气行为
  `NOT RUN`。
- 该结果不能转让给 AtomS3、AtomS3 Lite 或其它 S3 主机。

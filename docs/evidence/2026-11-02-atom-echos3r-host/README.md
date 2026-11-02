# Atom VoiceS3R（C126-ECHO）虚拟主机接入（限定验证）

日期：`2026-11-02`。范围：把视觉库存中仅有外壳的 Atom VoiceS3R 接入为独立
原生 QEMU 主机，并记录**虚拟设备**证据；物理声学、光学与电气 `NOT RUN`。

## 结论

- 新增机器 `m5atomvoices3r`：AtomS3R 控制器（128×128 GC9107、BMI270 +
  BMM150、ES8311、GPIO41 按键）加 Atomic Voice Base 的板级身份；
  功放使能 GPIO18 与 Voice Base IR GPIO47 只作为普通 GPIO 写入，没有
  声学/IR 模型。
- 官方 UIFlow2 `v2.5.4`（firmware `1897200000000000775`，SHA-256
  `9348083af8a30e23bd832822eb81c8af86de8ef0e3f683fbc6c801d78bd6cd7b`，
  8,384,512 bytes）在同一 guest 内输出：

  ```
  VOICES3R_BOOT_FLAG
  VOICES3R_MAIN_START
  VOICES3R_M5_BEGIN_OK
  VOICES3R_BOARD 145
  VOICES3R_SPEAKER_RUNNING 1
  VOICES3R_STATUS ok
  VOICES3R_AUDIO_WINDOW_DONE
  ```

- 原厂 `Speaker.begin()` / `Speaker.tone(440, 900)` 经真实 I2S1 TX DMA
  进入 `M5SW_I2S_PCM_FILE` 捕获：`53,248` bytes、`52,293` 个非零字节，
  SHA-256 `7dccc5267cb862382178ef6526951e27350307ef605028ef3819a196ccd30c3b`。
  这是 I2S 控制器/DMA 数据面证据，不是声学测量。

## 复现

```bash
python3 platform/tools/fetch_firmware.py --firmware-id 1897200000000000775 --chip-id 0x0009
PYTHONPATH=platform/tools python3 tests/uiflow2/run_device_matrix.py \
  --device atom-echos3r --flash-transport direct --out-dir /tmp/echos3r-matrix
```

case 的 `env` 固定 `M5SW_I2S_DMA_IRQ=1` 与
`M5SW_I2S_PCM_FILE=/tmp/m5-atom-echos3r-speaker.pcm`；测试镜像 SHA-256
`079a72e36eae2f2a33541d683d3a65a65c0dfb8c8de109e8926478871fa631bc`。

## 运行时来源

`espressif/qemu` commit `40edccac415693c5130f91c01d84176ae6008566`，
按 `scripts/qemu-wasm-build/sources.lock.json` 的原生层顺序（到 `0109`），
叠加 `0110-atoms3u-board.patch`、`0111-atom-voices3r-board.patch` 后构建。
本次构建产物 `qemu-system-xtensa` SHA-256
`492e7e809a7600b0dcdbeb46eb8893e2a0958da288366e70d9b12e0efd9f4ffd`。

## 未覆盖

- NS4150B 功放使能 GPIO18 没有模拟/声学模型；`Speaker.isRunning()` 与
  PCM 数据面不等于扬声器实际发声。
- Voice Base IR GPIO47、MEMS 麦克风采集、Grove(G2/G1) Unit 数据面未验证。
- USB CDC 控制台、任意第三方固件、物理声学/光学/电气 `NOT RUN`。
- 该结果不转授 AtomS3R、AtomS3 或其它 S3 主机。

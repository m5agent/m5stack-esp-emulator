# 2026-10-28：StopWatch / StickS3 / Core2 UIFlow2 音频数据面

## 范围

本轮在同一独立 Device Service 上复测三台 M5Burner UIFlow2 `v2.5.3`
虚拟设备，并同时运行六个会话：

- 每台一个 `M5.Mic.record` + `M5.Mic.recordWavFile` 会话；
- 每台一个 `M5.Speaker.playWav` → `M5.Speaker.playWavFile` 会话。

音频修复轮的 QEMU runtime SHA256：

`feb143e4c4f8140a8946356db39968a606861fb4b40b86f7bb50ea85603f5da2`

该 runtime 包含 `0054-i2s-rx-consume-transferred-pcm` 和本轮新增
`0062-esp32s3-i2s-continuous-dma-completion`。全部结果是
**virtual-device validation**；physical hardware、声压、音色和声学行为均为
`NOT RUN`。

后续 Core2 触控条/PWR 修复又生成最终 runtime
`03d74d53ff8187c4f0a3b22d34c4e898bdd93b61cfc98432dbbeecd1beb12419`；
三设备 Mic、Speaker 和 raw 路径已在该最终 runtime 上重新绑定，见下文
“最终 runtime rebind”。

| 设备 | 基础镜像 SHA256 |
| --- | --- |
| StopWatch | `ef5e81b6da17ba04a0356b3bde782e9f0f8f93b217701a4414a52a8d8d8532c0` |
| StickS3 | `c45d4514e21d94a6c069185e08f05851c75b4747d354c1423decdefa625e1dd3` |
| Core2 | `b228c0e2d877e77a8a352e917ed84f4da8ea92d15b25e28f431a2999620fe3c4` |

## 并发 Mic 结果

输入是同源生成的一秒 440 Hz、16 kHz、mono s16le PCM，32,000 bytes，
SHA256 `7bf26780838b452847af12b4bb1c1eb56b303132f46659e8c913a3a01a5a6e9b`。
三台都在同一会话中先执行 `record`、再执行 `recordWavFile`；两个输出分别做
独立频谱 oracle。

| 设备 | `record` | `recordWavFile` | 录音状态 | 最终 firmware SHA256 |
| --- | --- | --- | --- | --- |
| StopWatch | 440 Hz，PASS | 440 Hz，PASS | `1 → 0` | `5c76d34572258d6397208ca428bd3b53054d0daebd822985d0d6ec04a98f4b0f` |
| StickS3 | 440 Hz，PASS | 440 Hz，PASS | `1 → 0` | `f78f686a0aa1f90d5dd592599553571924a654f03b144dc5c81b518d9ea43d51` |
| Core2 | 440 Hz，PASS | 428 Hz，PASS（2.73%） | `1 → 0` | `c6a50034d80e8ebfb19d289ddc898603b94a4a8d19bc9a15f4f4dc0a0d08f751` |

WAV 均为合法 mono s16 16 kHz、32,044 bytes。PCM SHA256：

- StopWatch `record`: `7a23d57602e88d68b36534e7c25b91ff86ae104b11383d3b496ffac28a629138`
- StopWatch `recordWavFile`: `99d837c382cbc41820b9263f44a1da00a35f8f715ad8994eca809b560aa7de4c`
- StickS3 `record`: `5fd1fae259da3bcf789c869e406c391de314aa93ca5d240217a9c41bae5294ce`
- StickS3 `recordWavFile`: `84be9cc307df53ae3dcfe733262cc57af63f1f94f930869e27573dde35c10ab4`
- Core2 `record`: `532345661f416e8925d0f750821f9432357008bc3e49b45a50aa7a772cde1824`
- Core2 `recordWavFile`: `03c3683c4f17777e7db75da564e28c28a6f96697c3abc4795d5099c702cb02c7`

会话：

- StopWatch `c5f441347ae041bfa70c2177c1434001`
- StickS3 `11e237d06eea4a8c83367126ea1ee793`
- Core2 `322f4481bc774cd6aff759f6a07ac859`

## 并发 Speaker 结果

每台在同一个会话中先调用 `playWav(wav)`，再调用
`playWavFile("/flash/speaker-path.wav")`。两者均到达 guest marker，
停止前 evidence ZIP 保留 PCM；频谱按板级原生输出格式独立解码。

| 设备 | 原生输出格式 | 主频 | PCM SHA256 | 会话 |
| --- | --- | ---: | --- | --- |
| StopWatch | 44.1 kHz stereo | 662.146 Hz（0.33%） | `3443b3c9cb4c78650fa3ece3d4ea94a7757887461d216cd36de09847c0eea4ac` | `35a85c14a68f40a6ab99d7eb900c8a3e` |
| StickS3 | 22.05 kHz stereo | 659.454 Hz（0.08%） | `de53f36ab99b44eb12ade57c5b20965f8843ce87af489408ed7e839dfbc57863` | `001442fe3ff948358c1709b7b7880804` |
| Core2 | 48 kHz mono | 662.109 Hz（0.32%） | `0321cb2f469209b9b389a37aca5d4ad9ffd64c4677c5c6f66174476e3e949e04` | `944b4c38699247ea8ada318b6930f18c` |

`playRaw` 也分别在同一最终 runtime 上通过三台 660 Hz 频谱检查：

| 设备 | 主频 | PCM SHA256 | 会话 |
| --- | ---: | --- | --- |
| StopWatch | 662.146 Hz | `372a37dec5a59d5dd5f5d777ec20ae1256cabd0dcc048a4f11d603f3a35e68cd` | `9f0eb2edfd894c23b646839027800098` |
| StickS3 | 659.454 Hz | `6c55ef5fae863dca6dc88a175a3bcc36b21355d5a0ced486f058da80d32f3721` | `012fc01efa344f2cb97b866a7700bc16` |
| Core2 | 662.109 Hz | `3308f6d81f564911c5e893ae0b645770e1561f3e5759c30fc26470731b21f93c` | `50f21a07e6374c7289b6630b90aef7dd` |

## 修复的边界

修复前的 ESP32-S3 I2S 模型在 `TX_START + 2 s` 或 128 个描述符后停止
DMA completion。StopWatch/StickS3 的一秒 `playWavFile` 因此阻塞；当时
1、2、4 个 512-byte 分块能完成。trace 显示 guest 已开始排入第 16 个分块，
而 QEMU 在约第 65 个 1024-byte DMA completion 后停止推进。

`0062` 只把 completion lifetime 与 evidence capture 窗口拆开：TX 仍使能时
持续完成 DMA；PCM 捕获仍受 4 MiB 上限约束。最终六会话并发复测中，
Mic 与 Speaker 两类数据面均完成，未出现先前阻塞。

## 回归检查

- `platform/tests/test_s3_i2s_continuous_dma_patch.py`：实际 C callback
  在捕获窗口结束和 128 个描述符之后仍完成 DMA；pre-fix control 失败。
- `0054` 的 RX cursor oracle：只消费 descriptor 实际接收的字节。
- `platform/tests/test_plain_qemu_audio.py`：五个 plain-QEMU profile
  使用 session-owned fixture；未准入设备和 unified runtime 不继承。
- 所有 session 都请求 evidence ZIP 后 `purge=0` 停止，并核验 runtime PID
  消失。

## 最终 runtime rebind

`03d74d53ff8187c4f0a3b22d34c4e898bdd93b61cfc98432dbbeecd1beb12419`
包含 `0062` 和修正后的 `0063`。三台 Mic、`playWav → playWavFile` 和
`playRaw` 再次通过：

| 设备 | Mic `record` | Mic WAV | Speaker WAV/file | Speaker raw |
| --- | ---: | ---: | ---: | ---: |
| StopWatch | 440.070 Hz | 440.088 Hz | 662.146 Hz | 662.146 Hz |
| StickS3 | 440.070 Hz | 440.088 Hz | 659.454 Hz | 659.454 Hz |
| Core2 | 443.829 Hz | 443.758 Hz | 662.109 Hz | 662.109 Hz |

最终 runtime 首次六会话并发仍使用旧的固定 60 秒 guest READY 预算；
StopWatch Mic 在 QEMU 启动前超时。runner 随后新增显式
`--ready-timeout`，以 180 秒预算重新并发六个会话，Mic 与 Speaker
共 `6/6` 一次完成。三台 raw 会话另行并发，全部通过。

Core2 PDM WAV 是非对称强裁剪信号。第一次并发结果被旧
`verify_mic_recording.py` 的无窗矩形 DFT 报为 395 Hz；同一 WAV 的归一化
自相关给出 443.79 Hz（0.86%），第二个单会话样本为 443.76 Hz
（0.85%）。旧 oracle 的粗频点随相位变化落到 395/425 Hz，属于测试算法
误判。oracle 已改为围绕 fixture 频率有界的归一化自相关和抛物线插值，
并加入裁剪波形的平台回归测试。

最终 session：

- StopWatch Mic `fec206f66cc94a51933ee037a7ac4020`
- StickS3 Mic `ba03bd36d5634e4f89aa9f16dbdea7b8`
- Core2 Mic `cebd923e9ab3461384a406b190cf4e2e`
- StopWatch WAV/file `88096bee0697459683cbc6f02e60783d`
- StickS3 WAV/file `2f9bdcfd751c4871b856e3678365421c`
- Core2 WAV/file `361c5a01e7b543f882df9d7e53d63e2a`
- StopWatch raw `d57ca131e2d24a6793925fa5a5c5b857`
- StickS3 raw `37ef6c12dfd04c4eb54e7df24998421e`
- Core2 raw `134f0df29b6d4a31bde7ffd4d24863b7`

## 边界

- 本轮不证明物理扬声器、麦克风灵敏度、声压、频响、失真、回声、功耗或
  真机驱动差异。
- Core2 WAV 最终自相关偏差约 0.86%，但不能用裁剪 PCM 的频谱解释物理声学
  精度；PMIC/PDM 时钟和真机声学仍需单独验证。
- `M5.Speaker.playWav` 的 Python 返回值按固件是 `None`，完成由 guest
  marker、同一 session PCM 和独立频谱共同判定。

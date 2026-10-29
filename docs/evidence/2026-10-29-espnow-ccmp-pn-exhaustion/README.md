# 2026-10-29：ESP-NOW CCMP PN 耗尽 fail-closed 与 rekey

## 范围

`0083-esp32-espnow-ccmp-pn-exhaustion.patch` 禁止 48-bit AES-CCMP transmit
PN 在耗尽后回绕到 zero。测试通过显式 seed 接近 PN 上限，正常 guest TX
继续走 controller DMA 和 external bridge；耗尽后的后续帧在 bridge 内
fail-closed。

同一 LMK 的重复安装不得清除 PN/replay 状态；只有 peer metadata 或
LMK 实际变化时，才允许该 slot 从 PN 0 重新开始。全部结果为
**virtual-device validation**。

## PN 语义

- CCMP PN 上限：`0xffffffffffff`；
- 新 key 首次使用前可从测试 seed 初始化；
- seed 在第一次 TX 后 consumed，后续重装相同 key 不再重新应用；
- `counter >= max` 时 drop，不编码 zero/重复 PN；
- key entry 必须等 metadata、16-byte LMK 和 valid bit 全部完成后才可切换；
- 相同 metadata/LMK 不 reset TX PN 或 replay；
- metadata 或 LMK 变化时，该 slot 新 PN 从 zero 开始，并清 source-peer
  replay state。

| 项目 | SHA256 |
| --- | --- |
| QEMU runtime | `1f3bb7dbbf4b2b32f29e065c02dbe20f08188518c01bd39ec5eb00c724574262` |
| `0083` patch | `3e9d54b16b0ec3429347bb9d36efe96755935e2cff3d045cf3af3b0b82adcfa9` |
| runner | `1105cf71e09c3ba2ae69f77fdcdba2a53eea6ba1dfb09cf3ad608e32f513d9db` |

## 正控与负控

StopWatch↔StickS3 先完成 encrypted barrier，再发送 128 个 burn frame
越过 PN 上限。随后安装新 LMK：

| role | TX/RX | key ready | PN exhaustion | replay drop | post payload |
| --- | ---: | ---: | ---: | ---: | ---: |
| A StopWatch | 524/392 | 2 | 65 | 0 | 164 |
| B StickS3 | 522/394 | 2 | 65 | 0 | 163 |

second lane 只把相同 LMK 重新调用 `mod_peer`。key 仍为有效，
`guest_key_ready=1`，但 PN/ replay 状态没有被重置：

| role | TX/RX | PN exhaustion | replay drop | post payload |
| --- | ---: | ---: | ---: | ---: |
| A StopWatch | 430/64 | 183 | 0 | `0` |
| B StickS3 | 430/64 | 183 | 0 | `0` |

该负控证明“只重写相同 key”不能恢复已经耗尽的 PN；runner 对 post 0
payload、非零 exhaustion 和零 replay drop 做强断言。

## 回归

最终 QEMU 上重新执行：

- shared-LMK 三 guest fabric：PASS；
- pairwise-LMK 三 guest fabric：PASS；
- B/A cross-wire negative：只有 A↔B 归零，PASS；
- direct guest-key pair：之前已通过，0083 不改变正常 PN 路径。

上述 PN 正负控与三组 fabric 回归共 13 个 session，全部
`purge=0`、terminal `stopped`、runtime PID gone、history retained。

## 检查

- ESP-NOW controller/patch contracts：`51/51 PASS`；
- QEMU build PASS；
- patch forward/current-source/reverse PASS；
- full platform 与 CI 在里程碑提交后执行。

## 未覆盖

`RUNTIME-06` 仍为 `PARTIAL`：

- loss/retry；
- channel/rate；
- bit-exact controller；
- RF/antenna、电气时序和 physical hardware。

## 复现入口

```bash
export M5_CORE2_RADIO_QEMU="$PWD/.work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa"
PYTHONPATH=.work/py python3 platform/tools/serve.py 8811 \
  --bind 127.0.0.1 \
  --state-dir /tmp/m5-espnow-pn-state \
  --api-token-file /tmp/m5-espnow-token

PYTHONPATH=.work/py python3 tests/uiflow2/api_sweep/run_espnow_pair.py \
  --api http://127.0.0.1:8811 \
  --token-file /tmp/m5-espnow-token \
  --scenario guest-key-pn-rekey \
  --left-device stopwatch \
  --right-device sticks3 \
  --out-dir /tmp/m5-espnow-pn-rekey
```

same-LMK 负控将 `--scenario` 改为 `guest-key-pn-stale-rekey`。

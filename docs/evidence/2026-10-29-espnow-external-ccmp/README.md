# 2026-10-29：ESP-NOW 外部 peer 的 key-bound AES-CCMP

## 范围

本轮在 `0076` 的 independent-guest external peer bridge 上增加
`0077-esp32-espnow-external-ccmp.patch`。两个 controller 使用显式提供的
PMK/LMK fixture，在 bridge 边界执行 AES-128-CCMP 加密和 MIC 验证；
payload 仍从 guest 经正常 TX DMA 发出，并在认证成功后经正常 RX DMA 注入。

全部结果为 **virtual-device validation**。物理 hardware、RF、antenna、
channel/rate、电气、timing、bit-exact controller 和 production fabric 均为
`NOT RUN`。

| 项目 | SHA256 |
| --- | --- |
| QEMU runtime | `5340171ca484ce7ee3b13a0538a35c5f22fcd3a2ff726fa7a902424ff4d7d179` |
| `0077-esp32-espnow-external-ccmp.patch` | `4a0aa4fa4d92ddf00d02e62136c4bc881b4a5b6e73edeb78a835feb94a74e095` |
| `tests/uiflow2/api_sweep/run_espnow_pair.py` | `8c1530688da51bd4a3d7c5730af90462fd92282128c0ad9bf4b7bdbc191f96d0` |
| `platform/tools/device_service.py` | `f83d05ec87745211244d37045ee13eb876e71691e786e1eae6aa6a4681779c69` |

## 实现边界

- PMK/LMK 由 trusted-local `runtime_env` fixture 提供给 controller bridge；
  guest 仍执行原厂 `set_pmk`、`add_peer(..., lmk=..., encrypt=True)` 路径，
  但本轮不证明 guest key-state 已被 controller 读取或持久化。
- controller 状态只保存 PMK 和 AES-128-ECB wrapped LMK，不保存 plaintext
  LMK；每次 TX/RX 临时 unwrap，并在使用后清零。
- TX 移除 closed driver 的 hardware CCMP envelope，再以 bridge LMK、新 PN 和
  8-byte MIC 加密 action body。
- RX 在 guest DMA 前验证 CCMP/MIC；失败路径直接 `continue`，不调用
  `Esp32_sendFrame`，因此不会到达 guest callback。
- `wrong-lmk` 是负控，两个方向均应 `EXPECTED_DROP` 且 `rx_packets=0`。
- `wrong-pmk` 但两端 LMK 相同时仍应通信：PMK 只保护各自保存的 LMK，
  不是 on-wire pairwise key。
- `runtime_env` 中的 PMK/LMK 在 API snapshot 和持久化 session JSON 中显示
  为 `<redacted>`。生成的 guest probe 源码仍按测试设计包含固定 test keys，
  只保留在 ignored `.work/`，不进入仓库证据。

## 结果

| 场景 | 设备 | firmware SHA256 | bridge TX/RX | peer payload | 预期 | 结果 | evidence SHA256 |
| --- | --- | --- | ---: | ---: | --- | --- | --- |
| plaintext | StopWatch | `45bc4d347687820a9ceb91f6e97f3de448274ffc2ae1a44d64e87754bd4fd261` | 58/58 | 57 | PASS | PASS | `be7489793d8422de2f17322fff99f875e932ed22afb1538a07c3699b0c3959fe` |
| plaintext | StickS3 | `852720f8a4aa7fa4a39525b0bb5d40562ab30de180684b1a0039db17ca88d49b` | 58/58 | 58 | PASS | PASS | `d66925ca62534d549a8b71d82cca650c960f802dfb72bc992938a6c35c06d56b` |
| encrypted | StopWatch | `b6baab9fa89d706a1e97da9302306c19f6f3f45abf171fa3c4dcab5e35dddb08` | 58/58 | 58 | PASS | PASS | `17ff82f231cf5405f6a8f0dfcb206e0bfdf01ebfc5dee7fb5a9e5ea939e4e7f0` |
| encrypted | StickS3 | `a36fdff4efaee90b1b9bc1eed265b660d7e009b2fd391552a0d8205ed508ee6c` | 58/58 | 57 | PASS | PASS | `469e54a18640beac1cffc019c07d328be66621a93207da298946fc9fddee6b24` |
| wrong-lmk | StopWatch | `b6baab9fa89d706a1e97da9302306c19f6f3f45abf171fa3c4dcab5e35dddb08` | 40/40 | 0 | DROP | EXPECTED_DROP | `8a00bd53388f5bae30a399f1d62aeb3b00165491bdf33d4f2b36e32cf82e104c` |
| wrong-lmk | StickS3 | `8851f381e8f3a40a759b1d4fee037887563d6c0bde48ac5d92b90e1f36ae06bf` | 40/40 | 0 | DROP | EXPECTED_DROP | `b901839ac11c8339aa72684290177ff393066d0cb51d091cf5222de06b5ff501` |
| wrong-pmk, same LMK | StopWatch | `b6baab9fa89d706a1e97da9302306c19f6f3f45abf171fa3c4dcab5e35dddb08` | 58/58 | 58 | PASS | PASS | `dbdf59585755f06116c37a684baa86bc8b4e8332ee107b9c776ef179172e4be1` |
| wrong-pmk, same LMK | StickS3 | `4cd2afe265c7d16fe028e50b43eef7d8d8dac7d74b7b6fdf86b57deb28cecba9` | 58/58 | 57 | PASS | PASS | `2a03c32bd7729d29dc48bf7518ab5ff632e0559ac5edcffd9b6addef1583100a` |
| encrypted | Core2 | `b39ced5db5e6f5896baac4b2d59fc5a7d809d10798a2adafa0db461811238750` | 44/31 | 15 | PASS | PASS | `404fdfc24a63c7d6a3085a9c2db3d314fdb369aba88a80c2b98fe02063409167` |
| encrypted | StopWatch | `bb9999e9f822854b6929ce4357cfb7b9a07ab6488e5e638239348b9f476258b7` | 48/44 | 44 | PASS | PASS | `0afe6c0b1eddd5dd15cfccd10824d54de354dcf64d4804be242b37c4d1a43407` |
| wrong-lmk | Core2 | `b39ced5db5e6f5896baac4b2d59fc5a7d809d10798a2adafa0db461811238750` | 40/24 | 0 | DROP | EXPECTED_DROP | `28a2bb66b23b6533a7fc9b4fbeb4064211838df763cd495fd96f1ea88c8e0c31` |
| wrong-lmk | StopWatch | `e499e27ccf1021a73782958d56995dbeb9bb33aa4f7f6960ac277f3859cf6164` | 40/40 | 0 | DROP | EXPECTED_DROP | `35f2aa3c7e7de9bb629f4803e6d651a1926a25ec1c57a0a4bd58f309e8cf5e14` |

十二轮 session 全部在不同场景中使用独立 session，terminal state 为
`stopped`，`runtime_pid_gone=true`，停止使用 `purge=0` 并保留 history。
bridge TX/RX 在 `wrong-lmk` 中仍大于零，说明数据帧确实到达 peer；
`rx_packets=0` 来自认证失败后的 controller 侧 drop，而不是桥接未运行。

## 失败控制与未关闭

最初把 guest protected envelope 原样跨 controller 搬运时，即使两侧 LMK
不同仍出现双向 PASS，证明该路径没有真正执行外部 key-bound CCMP。这个结果
被拒绝，并促成 `0077` 的 TX 去 envelope、RX MIC 验证和 drop-before-DMA 路径。

`RUNTIME-06` 仍为 `PARTIAL`，因为本轮没有关闭：

- guest `set_pmk`/`add_peer` key-state 进入 controller 的完整传播；
- peer add/update/delete、replay protection 和 key rotation；
- loss/retry、双 peer 以上 fabric、channel/rate 与 bit-exact controller；
- RF、antenna、AP coexistence、电气、timing 和 physical hardware。

## 复现入口

```bash
export M5_CORE2_RADIO_QEMU="$PWD/.work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa"
PYTHONPATH=.work/py python3 platform/tools/serve.py 8811 \
  --bind 127.0.0.1 \
  --state-dir /tmp/m5-espnow-ccmp-state \
  --api-token-file /tmp/m5-espnow-token

PYTHONPATH=.work/py python3 tests/uiflow2/api_sweep/run_espnow_pair.py \
  --api http://127.0.0.1:8811 \
  --token-file /tmp/m5-espnow-token \
  --scenario encrypted \
  --left-device stopwatch --right-device sticks3 \
  --out-dir /tmp/m5-espnow-encrypted

PYTHONPATH=.work/py python3 tests/uiflow2/api_sweep/run_espnow_pair.py \
  --api http://127.0.0.1:8811 \
  --token-file /tmp/m5-espnow-token \
  --scenario wrong-lmk \
  --left-device core2 --right-device stopwatch \
  --out-dir /tmp/m5-espnow-wrong-lmk
```

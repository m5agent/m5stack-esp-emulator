# 2026-10-28：QRCode.setText 与 TLS epoch 三设备候选固件验证

## 范围

本轮把已有 `0014-widgets-qrcode-text` 与 `0010-mbedtls-epoch` 源码修正
分别增量链接到 StopWatch、StickS3 和 Core2 的匹配 build，再通过独立可见
Device Service session 执行。全部结果为 **virtual-device validation**；
物理硬件、RF、TLS 公网 PKI 和真机证书存储均为 `NOT RUN`。

QEMU runtime SHA256 为
`21b7e34cc96560b4c8185131791008ae49fb1c6975a8428e4e344188a8236394`。
增量候选只替换 application partition；每个 build receipt 均确认
`outside_application_unchanged=true`、原始源码与 cached library 未变。

## QRCode.setText

stock/preimage 在同一 `Widgets.QRCode.setText` 程序后仍解码旧
`UIFLOW2-API`；`0014` 候选解码更新后的 `UPDATED-API`。状态调用本身为
`PENDING_FRAME`，最终结论只看独立 QR decoder 的画面 oracle。

| 设备 | preimage SHA256 | 候选 base SHA256 | preimage | 候选 |
| --- | --- | --- | --- | --- |
| StopWatch | `790184d2d52c55e0b201727485d9c9c1fe184e6beae8637538097de24386b5d0` | `a8e69c2ed39a06d7112713a708bdd2b2c854bc6b0fd3f83407c5023ffcdaebfe` | `ORACLE_MISMATCH` | `FRAME_PASS` |
| StickS3 | `20b783596e397c5a2931e02a74178c83d14b17af963278259b82a609d3c33b95` | `a036205decdc090d576306bfc147fc6dc7124e07f5d864957f927efb12ae970b` | `ORACLE_MISMATCH` | `FRAME_PASS` |
| Core2 | `f3d37e56477b42741bb0a97095ec49a05a62e43475bab278cde130f909446e4e` | `42669acc0e04c4da45e8009d0bac70dc67d725acebf91b413a043c22abd2f932` | `ORACLE_MISMATCH` | `FRAME_PASS` |

三台候选的 compiled source SHA256 均为
`8f1fcf750218311405b996f5eee389fd3e42e59d28d8e85151d7c8addaf68888`，
补丁 SHA256 为
`939750d881194639b1eb7888d0848da570c31863ea85aad68345f1d2b897dd8b`。

## TLS epoch

preimage 在 2026 RTC 和 owned CA/client certificate（有效期
2020-01-01 至 2035-01-01）上均得到两个
`The certificate validity has expired` ERROR 与三个配置 `STATE_PASS`。
`0010` 候选三台均通过 `5/5`：

- `ssl.SSLContext.wrap_socket`
- `ssl.SSLContext`
- `ssl.SSLContext.load_verify_locations`
- `ssl.SSLContext.load_cert_chain`
- `ssl.wrap_socket`

| 设备 | preimage SHA256 | TLS 候选 base SHA256 | preimage | 候选 |
| --- | --- | --- | --- | --- |
| StopWatch | `790184d2d52c55e0b201727485d9c9c1fe184e6beae8637538097de24386b5d0` | `edcd9a392f1ff5e5741c8331ae41ea18b915ae50b2ff54c173110c65c532e6a6` | `2 ERROR + 3 STATE_PASS` | `5 PASS` |
| StickS3 | `373092e77e273d580ff7f31d52931778f4aa7a23d04bed285af395bc357077a6` | `2e8386057fab9d384489651a544e30ce4edaf86586e1f4ce7f588469439af6aa` | `2 ERROR + 3 STATE_PASS` | `5 PASS` |
| Core2 | `f3d37e56477b42741bb0a97095ec49a05a62e43475bab278cde130f909446e4e` | `204def8c601c29b7fa4af83b767c3fd8ced9c6b12815a709c450fb5b80a2e2c6` | `2 ERROR + 3 STATE_PASS` | `5 PASS` |

每台候选均完成两次独立的 TLS HTTP GET `/tls-authenticated`，使用 TLSv1.2，
服务端在握手后验证客户端证书。每次运行生成新的临时证书/key；证书 hash
按设备记录在 `summary.json`，私钥和原始连接材料未入库。

## 构建边界

- StopWatch/Core2 的 QR 和 TLS 候选使用各自 `hciuart` cached build。
- StickS3 TLS 使用 `unified` build；其 `uart.c.obj` 已包含当前 native UART
  REPL，避免临时重编译 transport object 造成重复 UART interrupt 分配。
- `build_rawbuf_candidate.py` 现在解析真实源码路径；
  `build_tls_candidate.py` 支持显式 build directory、flash size 和额外
  transport source。
- `run_guest.py` / `run_protocols.py` 新增 `native` UART bootstrap。对
  native-REPL base 不再执行 `os.dupterm(UART(0))`，避免
  `ESP_ERR_INVALID_STATE`。
- `0010` manifest 已从旧 release commit `3a86d8f6…` 重绑到当前
  `db526ecc…`。`main.c` 的另一处 `m5things` 启动变化与本 patch hunk 无关；
candidate postimage 和 patch SHA 分别重新核对。

这些是 incremental relink，`cold_build=false`，不表示独立冷构建，也不替换
设备目录默认参考固件或原厂冻结镜像。

## 复现入口

```bash
# QRCode：三台各一次 preimage 与一次 0014 candidate
python3 tests/uiflow2/api_sweep/build_rawbuf_candidate.py \
  --build-root .work/api-sweep-20261028/candidate-existing-fixes/tool-root \
  --cached-build <matching-build> --base-image <preimage> \
  --manifest patches/uiflow2-api/0014-widgets-qrcode-text.json \
  --flash-size <flash-size> --out-dir <candidate-output>

# TLS：显式匹配 build、flash 与 native transport source
python3 tests/uiflow2/api_sweep/build_tls_candidate.py \
  --build-root .work/api-sweep-20261028/candidate-existing-fixes/tool-root \
  --build-dir <matching-build> --base-image <preimage> \
  --flash-size <flash-size> --out-dir <candidate-output>

python3 tests/uiflow2/api_sweep/run_protocols.py --execute \
  --api http://127.0.0.1:8788 --group tls --device <device> \
  --base-image <device>=<candidate> \
  --expected-base-sha256 <device>=<candidate-sha> \
  --uart-repl-bootstrap native --out-dir <run-output>
```

原始 serial、frame、pcap、peer log、ZIP 和临时证书留在 ignored `.work`；
源码仓库只保留精简 hash、计数和复现命令。所有 session 先获取 evidence，
再以 `purge=0` 停止；没有执行物理烧录。

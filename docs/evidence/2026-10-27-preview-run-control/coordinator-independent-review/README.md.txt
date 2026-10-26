# Preview coordinator 独立宿主审计

日期：2026-10-27。类别为 **HOST_ONLY_NOT_GUEST**；无QEMU、固件运行、UART设备、
物理硬件或8787服务调用。这里不构成虚拟设备或硬件功能验收。

`sources/` 冻结独审开始时的 coordinator、HTTP facade 和 inert fixture；
`source-manifest.json` 记录SHA256。`repro.py` 使用冻结fixture和真实SQLite ledger，
其中按键/续租探针额外调用真实 `DeviceSession.validate_input/inject/renew` 宿主方法，
在QMP/持久化边界以显式阻塞或记录替身截取，既不连接设备也不生成模拟guest值。

运行方式：

```sh
/opt/miniconda3/bin/python3.12 .work/preview-coordinator-independent-review-20261027/repro.py --source snapshot
/opt/miniconda3/bin/python3.12 .work/preview-coordinator-independent-review-20261027/repro.py --source current
```

`review-probes-snapshot.json` 的8项 `bug_observed=true`，
`review-probes-current.json` 的8项均为false且无probe_error，证明如下负控被修复：

| 边界 | 独审开始时的可复现问题 | 当前负控结果 |
| --- | --- | --- |
| close held release | 释放输入失败使stop永不到达，VM保持running | session stopped，Preview closed，stop一次 |
| invalid key down | 无key请求先写held，400后毒化后续Run | 400、held为空、后续Run running |
| uppercase DOWN | 后端规范化为keydown，coordinator漏记release | old execution依次keydown/keyup |
| pending renew | Preview显示1h，会话仍30s | bind后会话对齐3600s |
| concurrent renew | 出站短租期与ledger长租期交错 | 真实renew持久化暂停下两侧租期一致 |
| expired input | 未经worker轮询可向过期Preview写输入 | 409，实际调用0 |
| shutdown input | shutdown后仍向旧active写输入 | 503，实际调用0 |
| duplicate Idempotency-Key | 两个独立头被first-wins接受并创建Preview | loopback400，无Preview创建 |

报告中SHA标识调用时的磁盘源文件，不是所有依赖或已加载Python字节的attestation。
current报告是一次精确检查点，后续产品改动需要重新运行，不自动继承结果。

另在独立review后接手修复了retention语义损坏P2：新增负控在旧helper产生47个
子例失败；修复后专属34 tests通过。覆盖retained/managed必需根、content-addressed
ID/SHA一致性、完整binding、递归provenance、ledger/disk identity一致性以及SHA根
对应metadata和artifact保留。普通live旧空身份保持兼容；损坏时同时阻断缓存与历史
删除。该helper已由另一位agent独立复审通过，原P2及合法SHA但ID/SHA不一致变体
均关闭；报告见 `../preview-retention-independent-review-20261027/report.md` 和
`fixed-verification.json`。其独立联合验证为34 retention +13 input +33 coordinator
共80 tests通过，helper SHA与 `owned-files-freeze.json` 一致。

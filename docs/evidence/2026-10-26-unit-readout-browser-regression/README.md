# Unit 实时读数：浏览器回归证据

2026-10-26，四项当前产品源browser回归全部通过。本批只证明浏览器/fixture/离线
语义，**未运行新的固件、QEMU、Device Service session或物理硬件**，不能代替
同session的guest/controller功能验证。

| 回归 | 结果与范围 | 证据 |
| --- | --- | --- |
| Model shell | PASS；14主机+27 Unit；frame/input/output/lifecycle/fallback | [report](regression/model/report.json) |
| Unit panel | PASS；27 schema、22项检查、1440/1024/768/390 | [report](regression/panel/report.json) |
| Web bridge | PASS；31 POST、12可信pointer事件；DOM/HTTP与capture contract | [report](regression/bridge/contract-report.json) |
| Session mount | PASS；440×420→320×420；detached-owned mount/dispose | [report](regression/mount/report.json) |

执行前冻结26个命名integration/test/schema源文件，并计算202个vendor asset的
完整hash inventory；四项结束后复核无漂移。另两个Python文件只作为Node bridge
的hash-cohort metadata，并未由本次测试执行；它们的suite-local hash早于全部
actions，归档时副本匹配该hash，单列reconciliation，不倒填为batch预冻结。

candidate/保留promote前shadow候选的原manifest/patch/源/设计、最后15项检查与
12张图；其promoted=false是当时的历史状态。四源hash与当前产品源一致；四项新
回归运行在promote后的产品源，两层证据分别保留。独立语义contract 17/17 PASS，
P2七个核心方法逐字连续，M5Stack Web Design token audit 0问题。

**readout placement PASS，不是整个场景视觉PASS。** ENV/Relay/nested各四档共
12张PNG已逐张查看：完整16px数值位于画布外rail，卡片不盖宿主display/control，
实际LCD鼠标touch仍收到start/end。nested原装配中三个housing仍互叠，属于
UNIT-HOST-15 OPEN；本批未改线缆/几何。12项readout不升级机械/LED/实体屏幕状态。

- [汇总](summary.json)
- [执行前source freeze](source-freeze.json)
- [suite metadata reconciliation](suite-source-reconciliation.json)
- [读数placement视觉复核](candidate/visual-review.json)
- [候选设计与边界](candidate/DESIGN.md)
- [最终候选manifest](candidate/manifest.json)
- [独立17项语义contract](independent/annotation-contract.json)
- [P2连续性](candidate/p2-continuity.json)
- [历史迭代摘要](iterations.md)
- [公共脱敏provenance](public-redaction-provenance.json)

四个同名platform/tests入口可从仓库根目录重跑到新的输出目录，均使用独立
ephemeral fixture server，不依赖8787。历史candidate/browser-only.mjs重放时需
恢复candidate目录到仓库.work下；注入/回放数据不能当作新guest执行。

公共副本脱敏日志与token audit元数据中的个人绝对仓库路径，并更新公共candidate
manifest的该audit hash；变化逐项见provenance，.work和candidate原件不变。
SHA256SUMS覆盖本目录全部文件（自身除外），未复制固件/ROM等二进制。

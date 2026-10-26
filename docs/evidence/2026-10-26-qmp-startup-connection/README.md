# QMP 启动连接归属修复与证据

2026-10-26：候选已合入，gen8 使用同一冻结 Xtensa runtime `a8fe15db…`。
本目录确认 host 控制面源码修复和离线回归；gen8 的真实可见会话补证仍在进行中，
不在此提前授予新的 Unit、全27、跨主机或真机 PASS。当前服务来源见
[generation8 receipt](../unit-service-generation8-20261026.json)。

## 历史 A/B 保持原件

旧 service baseline `3138b1ff…` 与锁修复候选 `8c956c90…` 的源码、补丁、同一套
正常 unittest、A/B 结果和两次历史失败片段均逐字复制自已冻结的脱敏归档。
`normal-baseline-regression.json` 为 **3 PASS / 2 FAIL**，
`normal-candidate-regression.json` 为 **5/5 PASS**；原件未按合入后的结果改写。
[review-summary.md](review-summary.md) 保留当时的只读分析和具体日志/源码行。
它描述的是候选阶段，后续状态以本页和 [promotion.json](promotion.json) 为准。

确定复现的源码竞态符合 Atom 首次 boot 与 Limit R4 的历史现象，但历史没有逐
attempt 的 connect/greeting 日志，不能声称完整重演当时线程顺序。两次历史
FAIL 保持 FAIL。它们已能执行 guest、截图与 QOM，却在启动线程重复创建 QMP
连接时收到“socket did not appear”；这个文案也会覆盖握手 TimeoutError。

修复只在 `_launch()` 建立 QMP 的区段取得与 API 相同的 `self._lock`，在锁内
检查 `_qmp is None` 并复用早期 frame/units 请求的连接。启动60秒、命令2秒和
真实错误传播不变，未放宽控制器或固件的成功条件。

## 合入后的 socket 清理补充

root 将正常5项测试纳入 `platform/tests` 后，真实 AF_UNIX busy-peer 用例暴露
失败握手未关闭 socket 的 ResourceWarning。`QMP.__init__` 现对 connect、
greeting 或 capabilities 的异常关闭新建 socket，再重新抛出原异常。合入后的
测试还保留失败 socket 对象并断言每个 descriptor 的 `fileno() == -1`。
该补充不改写原候选 service 文件；变动位于其导入的 QMP helper 和对应测试。

本次归档独立重跑：

```sh
PYTHONPATH=platform/tools:platform/tests python3.12 -W error::ResourceWarning \
  -m unittest discover -s platform/tests -p test_device_service_qmp_startup.py -v
```

**5/5 PASS**，日志在 [promoted-warning-strict.log](promoted-warning-strict.log)。
这些测试仅使用临时 host fixture、受控进程/QMP peer 和 AF_UNIX 传输，不启动
QEMU、不调用8787、不执行固件。

| 合入源码 | SHA-256 | 快照 |
| --- | --- | --- |
| `platform/tools/device_service.py` | `8c956c90a486f6537c712a9489618b8fc7efd024f25b9ddac06da4091056d516` | [原候选](source/device_service.candidate.py) |
| `tests/uiflow2/run_profile_ui_test.py` | `d8819cb73b7bace9df55e65bbc293d7ed27f01466eaabbb1fab14b4923714557` | [QMP helper](promoted-source/tests/uiflow2/run_profile_ui_test.py.txt) |
| `platform/tests/test_device_service_qmp_startup.py` | `9519aeec9fc0bc110a119f143dc0abb4874656e3af0545979b303cfb499a3506` | [合入测试](promoted-source/platform/tests/test_device_service_qmp_startup.py.txt) |

## Panel 生命周期与验证边界

桥接层另修复了真实 Panel 的输入等待：必须同时满足 SessionVisual/UnitPanel
为 running、QOM available、目标 DOM 控件 enabled，才发送普通输入、trusted
touch 或 double-click。booting 时已有 QOM 并不代表控件可操作。离线合约已
验证31个真实 HTTP POST、12个 trusted pointer event，Python provenance9项
通过；[完整合约证据](../2026-10-26-unit-web-readiness-regression/README.md)
明确其未执行固件。产品 Panel 本身没有为测试绕过禁用状态。

gen8 当前补跑真实会话，用于验证修复后的 Web/guest 路径；host9 尚未启用。
普通 host9 不强制首次画面为 flashing；独立服务启动用例再验证真实
flashing→running 与持续 QMP/frame 读取。后续结果另追加，不覆盖本目录历史。

原始 A/B 文件由 [archive-manifest.json](archive-manifest.json) 索引；该文件保持
原件，只覆盖复制来的21件。新增合入说明和快照及原件一起由
`promotion-manifest.json` 记录全部文件的 size/SHA。归档只保留脱敏文本源码与
诊断，不含 firmware、ROM、Flash、eFuse 二进制或凭据。历史 helper 脚本是当时
repo 布局下使用的源码快照，不宣称脱离仓库后可独立运行。

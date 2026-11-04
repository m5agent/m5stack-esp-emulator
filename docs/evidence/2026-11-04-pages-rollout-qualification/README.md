# Pages发布资格：正式云端与新本地失败

日期与最近核对：2026-11-04。执行层级：**virtual-device validation**。
当前结果 **FAIL_RELEASE_QUALIFICATION**，既有公开站点未被本轮替换。
精确身份及原报告byte/SHA见[summary.json](summary.json)；JSON逐字来自
[已发布固定提交](https://github.com/m5agent/agent-work-logs/blob/04b04a2225c4a233ef95ca2ea05e325de75a6f76/records/esp-emulator/2026-11-04-uiflow-browser-workbench/followups/2026-11-04-pr165-release-qualification-failures/evidence/summary.json)，9,907字节，SHA256
55ed3817e18b45b3feed54af12a6c101680781c693faaf77f1be7bd484a84df0。
本次文档维护未新增guest、构建、重试或发布。

## 三条独立路径

| 路径 | 实际结果 | 不能继承的结论 |
| --- | --- | --- |
| regular41799916700 attempt2 | sourcebuild/export/host控制通过；首Matrix600000ms未app-ready，4UI检查/零program，1FAIL/59NOT RUN | build/export成功不等于应用ready；最后五CDP关闭不证明正常QMP |
| 本机CfT152/M4控制 | 单Matrix完整case58项、11program和reset通过；normal0/两阶段5CDP | 不是58个case，不关闭hosted PV失败，不确定Chrome/host/C根因 |
| fresh MAIN23d/prod-prefix桌面完整计划 | 17completed=16PASS+Lite1FAIL、43NOT RUN；48项后硬reset新boot PIF | 旧V6/R8 PASS不授新导出资格，oneInsn不保证reset稳定 |

MAIN23d38d8dbe91488185dc53eb4cd47dee687df019与已验c3db源码树相同。
正式runtime manifest9c317e4d…和本机合法fa6b5604…保持不同producer身份；
五个runtime资产相同（含96ea WASM）不等于manifest相同，没有复制manifest伪装云端产物。

新export manifest为685e134cbaa09bf44edf45218843d387b26cf9e775b75cdf21b8ce3024539e7d，
用fa6/96资产。Lite精确Flash为
5c06f621bd765980f8ac274760b5648df58f3828d647f9d13acf77fb4d9601e8，
原8f9控制脚本不变，divisor1/无icount，实际TCG参数one-insn-per-tb=on。
代码执行后的硬reset在Core1 PC403864c3/EXCVADDR6002306c触发PIF；
不能与早先多指令首次boot失败混为同一个执行阶段。

Lite该次normal-QMP0、零forced/fallback、五pthread归零、六CDP-before-context关闭；
held-iframe未捕获。AtomS3R peer63项正常drain与两阶段六CDP另有证据。
正式hosted失败未建立normal QMP/disposal，仅有最后五CDP关闭，不能混写。

## 当前范围与关闭要求

此前2026-11-04[V6/R8全19本地60例通过](../2026-11-04-browser-uiflow-all19-acceptance/README.md)
保持原日期/固件/runtime身份，不被本轮失败覆盖，也不能转授新export发布资格。
[RUNTIME-09](../../runtime-model-gap-register.md)仍OPEN，现包括精确oneInsn下的reset复现。
已映射INT_CLR普通读的实际region/TLB/TB/IRQ事务原因尚未闭合；
诊断片段、另一环境或另一执行策略的通过均不等于C根因修复。

release promotion、prepared-preview部署及HTTPS40/DOM验收均NOT RUN。
保留原FAIL，取得同异常路径修复与回归后，再完成同候选导出的完整门禁和线上验收；
不通过改固件/时钟、放宽断言、跳过reset或转授另一设备PASS收口。

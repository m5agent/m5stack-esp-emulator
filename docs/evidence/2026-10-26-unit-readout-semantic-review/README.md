# Unit 读数语义独立审核

2026-10-26。最终候选的 **17项 Annotation 语义契约与23项 P2恢复契约，合计40项离线PASS**；5种隔离源码变异均触发预期FAIL，从而通过反例检测。这里只证明离线契约，不包含浏览器、固件、QEMU或物理硬件执行。

[初始问题与修复映射](findings-and-resolution.json)保留四类问题：注释异常污染成功输入ACK；有限但越界读数；非冻结inventory与非guest-QOM来源被显示；Thermal fixture readiness和双来源控制寄存器的标签误判。原初查报告与方向审核分别保留在initial/，没有覆盖失败尝试或回填旧源码。初查中未建立旧live画面前置状态的empty-payload探索项不作为验收证据。

[正例17项](positive/annotation-contract.json)核对真实字段、类型/范围/enum/default、outer与Unit双层来源、冻结定义、Thermal双来源标签、pending输入、terminal/persisted、adapter透传、成功ACK异常隔离、一次补偿及无轮询回声、nested清理和dispose。[P2回归23项](positive/p2-recovery-contract.json)继续覆盖原前端恢复边界。测试抽取实际纯函数、Panel及adapter执行，没有重写一份同算法oracle，也不需要Three运行时或新依赖。

[5项负控制](negative/summary.json)在最终冻结源的独立副本中，分别移除范围、Unit来源、冻结契约守卫，把Thermal readiness错标固件输出，或取消注释异常隔离。negative/各目录保留预期FAIL报告及执行用源码快照；expected failure表示测试成功识别缺陷，不表示最终产品失败。

[promotion receipt](promotion/receipt.json)、[最终候选manifest](promotion/final-candidate-manifest.json)和补丁与当前四源逐字节一致；[审核记录](validation.json)保留对应SHA、全部copy provenance及路径脱敏说明。40项结果来自已记录的final candidate/隔离合并执行，其源字节已与promoted产品独立比对；没有把root另一次复跑计为这里新增执行。

在仓库根目录复验当前产品：

```sh
node platform/tests/test_unit_annotation_contract.mjs
node platform/tests/test_frontend_recovery.mjs
```

源码快照位于sources/，均以.txt保存。历史固定字节复验时，把sources/下全部快照复制到新的临时目录，保留platform/相对路径并去掉末尾.txt，然后运行其中归档的测试；catalog与测试源也一并冻结，不从未来的仓库版本补读。负控制可将对应三份sources/platform/web/*.js.txt复制到新的临时源目录，恢复.js文件名，再把该目录作为第一个位置参数传给test_unit_annotation_contract.mjs；应以退出码1并出现各报告注明的具体失败用例结束。

原始负控stack中的绝对workspace路径替换为`<workspace>`；原报告内部保留，公开前后SHA分别记录。所有结果与观察值未改写。本目录不授予其它主机、Unit、完整场景视觉、RF/电气/声学或硬件结论；nested housing装配互叠仍为独立开放边界。

# AIFlow实时编程/预览 API 只读审查

日期：2026-10-26。状态：`REVIEW_COMPLETE_IMPLEMENTATION_PENDING`。
仿真器基线 `0a6a9a2a4201f49464afb6cd6e36c321d3305cb6`；AIFlow SDK只读审查
期间从3f0eb383推进到b4994060，最终源文件哈希与行引用重新核对，详见来源收据。
外部agent-work-logs按用户要求 `SKIPPED_BY_USER`。

审查现有HTTP/OpenAPI/服务/Web及AIFlow调用链，未修改API行为、SDK或部署。
[仿真器审查](architecture-review.md.txt)、[AIFlow消费者审查](aiflow-consumer-review.md.txt)
及[当前AIFlow源收据](aiflow-source-receipt.json)为原字节运输副本；Markdown仅改后缀。
当前结论与实施门禁见[评估计划](../../plans/2026-10-26-aiflow-live-preview-api.md)。

[实测时序分析](observed-session-latency.json)只读取前批24个真实source API会话的
原evidence ZIP manifest.timeline：创建到探针READY为14.428–21.341秒，中位
16.984秒；创建到booting为12.073–18.821秒，booting到running为1.982–2.838秒。
全部flash transport为esp-emu-esptool。每条样本绑定原ZIP路径/SHA；这是该批
串行、具体探针/主机/运行时的观察，非AIFlow完整链路或首像素时延/容量/SLA。

[取消竞态复现](cancel-race-reproduction.json)使用实际DeviceSession生命周期方法，
通过Event阻塞prepare_flash；stop先返回stopped后，旧_provision仍调用一次mock
launch、变running且重新出现Flash。对照未取消正常完成。mock仅控制host调度与
资源边界，没有API、QEMU、guest或硬件执行，不提供外设PASS。生产文件
SHA093e4738efa6b505b1505e5b635249b9ac992583ff587791e16011d29f3b80a8前后不变。

原[复现脚本](reproduce_cancel_race.py.txt)应在固定基线的工作树还原为
`.work/aiflow-api-architecture-review-20261026/sandbox/reproduce_cancel_race.py`
后运行；它只支持原路径结构，会写自有sandbox并禁止socket/子进程。后续修复
不应为了通过此历史负控重新引入旧行为。此包不包含源码部署/流传输修复或新SLA。

`copy-provenance.json`记录复制来源、SHA和原大小；顶层`SHA256SUMS`校验存放字节。

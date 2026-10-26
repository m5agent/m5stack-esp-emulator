# 新 vendor 3681 两条真实 E2E 的只读独审

2026-10-26。**总状态 PARTIAL**：Uniform 在数据/材质/完整画布范围 PASS；Scroll 的原驱动串口、控制器 API、应用 PNG、实际组件材质和清理 PASS，但该批没有独立逐 leaf raw QOM，不能满足该项完整门禁。

- vendor固定为 `3681a6482aff96501d44659ba5a1603246f1fe1f`；两份原报告的24项源码并集均与当前字节一致，执行探针均包含结束前 source gate。
- service精确generation32、runtime `b8de32a39be06162ae8ce8529b218370038936059dba067b9a7109a470e067d2`。三个独立session逐一核PID/固件/nonce及真实串口，没有把不同session拼成一台设备的执行。
- 汇总9次execution、60个ZIP成员全部路径/CRC/大小/SHA、17份fresh UART窗口、86张保存PNG核验。独立只读GET确认各session停止历史/最后帧、Flash释放；三个原PID kill0均不存在。最终health查询仍gen32、active_sessions=0。
- Uniform：8次同VM程序、14灯实际挂载/known/材质、56次阶段灯断言、20个完整browser canvas与20个直接renderer、480个Box3角投影、I2C/RMT逐leaf raw QOM、409不产生第五execution、22次实际503与恢复均通过。503前缀为HUB10/RGB7，实际全集HUB12/RGB10；不能把前缀当总数。rmt-rgb/B两次帧采样SHA不同但execution/revision相同，保留分次采样边界。
- **HUB组Encoder被8Encoder部分遮挡；Encoder光学可读性 NOT ACCEPTED。** 完整canvas与14灯材质断言不代表14灯全部同时无遮挡，也不证明每颗灯的物理通道位置。前端unknown中性外观不是电气off测量。
- Scroll：一个execution、四次输入、五个fresh串口/控制器/应用帧阶段，1600ms零echo；实际画布中CoreS3与Scroll完整，红PRESSED和绿RELEASED/-2画面可见。截图下方卡片读出被裁到边界，不宣称全页可读性；该批不是多程序替换测试。
- Scroll的ZIP `qom/snapshot.json` 只有 `soc` 以前节点并含 `__truncated__`，没有units；报告没有另存独立逐leaf raw QOM响应。`/units` 的 guest-qom 读回是已有控制器证据，不能冒充第二份独立raw样本。不用旧批次QOM补齐本批。

机器总报告为 `review.json`，分项为 `uniform-review.json`、`scroll-review.json`。`review-uniform.py`、`review-scroll.py` 只解析保存字节、调用host-only冻结validator/负控和只读history/frame GET；没有启动新guest/browser，没有修改源码、文档或原始证据。所有结论仅属虚拟设备；硬件NOT RUN，轴角/位置标定、RGB队列/slot/burst、TIM回绕、bootloader/持久化均未升级。

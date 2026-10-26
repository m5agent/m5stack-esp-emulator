# AIFlow 预览契约细化与 Unit 客户端响应隔离

日期：2026-10-26。基线为 `99e3e22c` 上的本块修改。
外部 agent-work-logs 按用户要求 `SKIPPED_BY_USER`。

## 范围

本块只修改 Unit panel 的异步响应/装配所有权及其浏览器回归，细化
[AIFlow 预览方案](../../plans/2026-10-26-aiflow-live-preview-api.md)。
Preview/Revision/Run、SSE 分发、共享帧缓存、快速 Flash 准备和同 guest 热部署
仍未实现。本块没有新增 guest、8787 功能执行、QEMU controller 或硬件测试。
上一块实际会话取消与 PIR 交互的独立证据见
[生命周期修复](../2026-10-26-session-cancellation-f309/README.md)。

## 客户端行为与验证

独立 session epoch 隔离旧会话成功、失败和初始化结果；input epoch 在操作
入队/结束时前进，拒绝早于操作确认的 GET 全量快照。普通旧队列不发送到新
session；必要 momentary release 只向原 session 发送，不能写回新面板。
跨 session 清除旧装配所有权，按新会话有效定义重新挂载；同 shell 晚到的旧
attachment 不回收新 owner。读数始终来自 API 真实响应，不由本地输入补输出。

`browser/panel/report.json` 是最终完整浏览器 fixture 合同；`browser/negative/`
为旧产品源码与同一新测试的确定性失败，首个失败是 GET 晚于 POST 返回后回滚
状态。受控 Promise gate 决定响应顺序，未用 sleep 选择竞态。annotation、audio
和 bridge 的最终报告另存，均为离线/browser fixture，firmware execution 为
`NOT RUN`，不能充当 Unit guest 或物理行为 PASS。

本地 epoch 不建立多客户端控制器快照的全序；保守丢弃后依靠下一次 fresh GET
收敛。服务端控制 ownership、run 标签及原子采样仍属于后续 Preview 契约。
最终完整平台测试及四生成检查见 `verification/`；前期文档 snapshot 过期、
新增证据索引漏项及派生文件写入重叠的失败原件保留，不与最终整轮拼接计数。

## 消费者与来源

`aiflow-consumer-readonly.json` 记录 AIFlow HEAD `947d182b` 与当时并行脏工作树
十份相关文件前后稳定 SHA。它只证明观察到的源码路径，不代表部署状态；未读
运行配置/凭据，也未修改 AIFlow。新增 device-data snapshot/SSE 可复用展示模式，
代码 checkpoint、不可变文件下载和 virtual target 仍需补齐。

`copy-provenance.json` 记录原字节副本，source 中的文本快照只增加运输后缀；
`SHA256SUMS` 覆盖存储字节。敏感信息候选审计见 `archive-audit.json`。
桥接报告以 `web-report.zip!web-report.json` 无损保存；冗余本地长截图仅保留来源
与哈希，清单见 `omitted-local-screenshots.json`，不改原报告或截图字节。

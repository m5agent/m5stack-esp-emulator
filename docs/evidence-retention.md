# 源码交付与历史证据

日期：`2026-10-27`

源码分支保留功能实现、官方协议依据、必要的小型测试 fixture、精简验证结论、
固件及运行时哈希和复现命令。新增 Unit 工作的原始 ZIP、逐帧图像、浏览器 trace、
完整请求响应、Flash/源码副本和临时构建日志不随源码交付。

## 历史结果的读取方式

此前 Unit 运行记录保留在
[固定历史提交](https://github.com/m5agent/m5stack-esp-emulator/tree/a37342f61c05964c060719a6e35c2d568c828e84/docs/evidence)。
本次精简分支从主线重建，历史大提交不是本分支的祖先。文档中的外部 evidence
链接固定到该提交；普通检出无需下载这些归档，也不依赖本机 `.work`。

`platform/units/runtime-profiles.json` 中的历史记录明确包含：

- `evidence_storage=external` 和固定的 `evidence_commit`、`archive_url`；
- `validation_scope=historical-exact-runtime`；
- 原设备、固件 SHA、运行时 SHA、报告/归档 SHA，以及适用范围。

摘要仅保留 session ID 的 SHA256，不保存原 session ID、PID 或 worker generation；
完整原始身份只在外部归档中交叉审计，不能把摘要当作原始报告字节。

这些值是历史结论索引。`PASS` 只属于记录中的准确设备、固件和运行时；不能
继承给当前构建、其它主机或物理设备。普通 CI 校验索引结构、能力契约与离线
正负控，不把外部报告缺失转换为运行验证通过。

需要重新审计原报告、ZIP、串口/帧和 source provenance 时，先独立取得完整
历史材料，再运行显式验证入口：

```bash
python3 tests/units/verify_historical_runtime_evidence.py \
  --evidence-root /path/to/complete-historical-checkout
python3 tests/units/verify_historical_tool_provenance.py \
  --source-repo /path/to/complete-historical-checkout
```

缺失附件、source blob 或哈希不符必须失败。下载或保存归档本身不等于重新执行
固件。重新运行功能测试仍按 Device Service 的可见 session 流程，单次采集所需
串口、最后帧、输入/状态和相关数据面摘要；完整矩阵只在项目约定的里程碑运行。

## 本次 Unit 交付边界

同 VM UART REPL、完整文件包与字节码依赖、Preview/checkpoint/Run、取消和
Web 消费者的实现保留。各 Unit 的 `implemented`、`partial`、`planned` 和
固件/主机准入仍以 registry 和[项目当前状态](project-status.md)为准。

最终 `0047` 冷 pad/软 I2C 修复的历史运行时为
`faee96da9f041583a6003a26523fa5378a88a4bc8f01b15492922076abf73096`。
它有针对性 controller/设备回归记录；新的四主机 FlashLight API/Preview、
mounted Web 及独立完整矩阵仍为 `NOT RUN`。旧 `3f1617` 完整矩阵中的 Core2
IMU 失败保持 `OPEN`。历史平台测试通过不等于本次干净检出通过；本次检出验证
单独记录在[清理计划](plans/2026-10-27-source-pr-cleanup.md)。

## 后续取证预算

优先保存一份机器可读总结：输入及版本、准确固件/运行时哈希、检查结果、
失败原因和复现入口。只有能解释结论或失败的少量串口片段、关键帧或小 fixture
才进入源码库。完整归档按需作为独立 CI artifact 或外部附件保存，设置保留期；
不再次在源码历史中复制逐次响应、连续帧和完整源码快照。

源码 PR 新增 Git blob 总预算为 150 MiB，单文件上限 10 MiB；新增
`docs/evidence` 仅允许小型总结，每份上限 64 KiB、合计上限 1 MiB。
门禁覆盖分支中的新增历史对象，不能先提交大附件再删除来绕过体积限制。

公开前检查主机绝对路径、私网端点和凭据；协议 fixture 所需的测试网段应明确
其语义。外部归档仍适用原有审查门禁，链接不扩大历史结论，也不追授硬件 PASS。

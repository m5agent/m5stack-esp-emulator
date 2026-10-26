# Buzzer once：原版负控与显式 custom guest

2026-10-26，CoreS3 / QEMU 虚拟设备证据。runtime SHA256：`a8fe15dbe7299c5be4b52eeac68a6d0012578950d267287630760bf8bec7d047`。硬件、声压、频谱和物理波形均 NOT RUN。

| 固件路径 | 最终 firmware SHA256 | 结果 |
| --- | --- | --- |
| 原版 reference app + 原官方 Unit wrapper | `d06e243cb5575daacd43cdfe02fe0c45d5ccdd1aa25988b17566696370f8b911` | **FAIL**：TIMER_DONE/manual 前未观察到自动零；0/1/2/once 四阶段 |
| 显式 callback arity adapter custom guest | `1be665305135da208b078dd079c6837558cce5ddc4eefbde4eff902080d2b880` | **PASS（该 custom SHA）**：六阶段，timer-zero 在 TIMER_DONE/manual 前由实际 QOM 观察 |
| natural diagnostic custom guest | `f679d481358af9209847a851d4178986479e2012df7a95f7964f27a567fc2e6e` | DIAGNOSTIC_COMPLETED；原始 once 先观察3500ms，随后独立手动诊断 |
| trace diagnostic custom guest | `68bfd5801f6497440c0164a3c606e0c1cd9a798ffaabfaf752b4f3fc96e3ab09` | DIAGNOSTIC_COMPLETED；后台 scheduler-loop TypeError 被直接转到同 UART 并 re-raise |

builder 先打印 flat LittleFS 阶段 SHA，再打印含 package 的最终 SHA；本表、report、ZIP 和 prepared 使用最终 SHA。归档不含 BIN/ELF/ROM。

原版与 custom 共用同一 reference base（SHA `1324f12d3ddd5392f47a9eff537f9ce0b01a8e6e36d829b6bd22cdf82d2c1264`）及 runtime。默认未传 flag 和显式 False 的离线 prepare 都逐字节保持原版 d06e image。显式 `--buzzer-callback-arity-patch --case buzzer` 仅改 generated BuzzerUnit wrapper，接受可选 timer 参数后调用原 frozen `Haptic._cb()`；原 vendor wrapper SHA `a64cd1e918c92b97f3b0cd8c2e451416d0abfda7cd83aaef18883869f2e5c0c3` 不变，frozen Haptic/SoftTimer 和 QEMU 未改。上传固件默认语义未被替换。

原 IO 曾在 TIMER_DONE 后等待零，可能把随后 turn_off 的零当作 timer 证据。当前严格门禁在实际 QOM 两侧抓 serial，要求同 once anchor、完整前缀、真实数值零及2000±40Hz，且两侧均未出现 TIMER_DONE/后续 Buzzer 事件。原版在该门禁明确失败；旧 controller PASS 不能证明自动定时归零，也不能升级为本次 PASS。

natural：timer.dead 在到期前后 False→True，QOM仍约50%；后续 async sentinel不执行，实际 bound callback(timer_arg) 和 detached scheduler.update(original callback) 都 TypeError，no-arg callback能经真实写路径使 QOM为零。这是同固件路径的关联证据。trace 另一个 SHA 直接捕获后台同一签名 TypeError；其入口日志会改变线程时序，因此与 natural 独立列示。`scheduler._run=True` 只是属性，不能视为线程存活。

**Getter 差异仍 OPEN。** 实际 diagnostic guest PWM.duty_u16 getter 全程0，而同 session QOM 按50/25/0变化。固定 QEMU 源码写 shadow/observer 有实现，DUTY/DUTY_R read缺失；官方 MicroPython→IDF→S3 LL getter读取 DUTY_R bits18:0再右移4，与该症状相符。尚未采集实际 BIN getter 的动态 MMIO 地址，不能由源码推断直接结案。实际 app_desc 是 IDF v5.5.5-dirty，50e README/CI却写v5.5.4；归档官方clean v5.5.5参照不等于该dirty构建的完整源码绑定。见 getter-investigation。

`original/` 和 `custom/` 保留 report、其 artifact_sha256 白名单、原 evidence ZIP 和 probe source。`diagnostic-natural/`、`diagnostic-trace/` 保留 result、serial、ZIP、frames、history/health、prepared/source hashes 和实际 observation 对应的 units/serial原HTTP bodies。两者完整 http-index 保留；**其他原HTTP body未归档**，具体保留索引与省略文件见 http-retention.json，不宣称HTTP全量归档。

四份 ZIP 均通过白名单成员、内部manifest大小/SHA、CRC、PNG解码和隐私扫描，逐字节复制，原ZIP SHA未改。所有 raw .work 输入只读。少量 supporting review JSON 的本机runtime路径被替换为占位符，其 input/archived SHA及变更计数在 archive-manifest.json；运行report/ZIP/HTTP bodies保持原字节。未归档凭据、私网端点、MAC、私有绝对路径、二进制固件或缓存。SHA256SUMS覆盖目录内除自身外的全部文件。

上游 README 以 `getter-investigation/uiflow-50e4407-README.md.txt` 保存源码快照；其中相对链接按上游仓库目录解释，原文字节和SHA不变。此次后缀格式修正前的 SHA256SUMS 原字节（SHA `d80c56b255cceaa85c10f59c1dd0959c5f5ced8a43e82a6c7a978410610db4cf`）、原 archive-manifest 及修正记录保留在 metadata-history，均标为历史元数据。

独立复核重放 custom 的6阶段 fresh GET/body/DOM值、原始 serial前缀hash与timer窗口、direct PID/runtime/firmware/worker绑定；原版负控仍为FAIL。Python adapter16+annotation35共51/51离线PASS，真实LittleFS默认image连续性已测。截图和 guest/HTTP观察不是原子 LCD/DOM 采样；此记录不授其他 firmware SHA、board、controller、RF或硬件结论。

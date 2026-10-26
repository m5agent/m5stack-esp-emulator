# 三主机 Unit source API 验证证据

AtomS3R / StickS3 / StopWatch × PIR、DualButton、Limit、Key、RGB、Fan、RS485、HUB，共 24 个明确的 virtual-device source API 路径。Fan3 与其余21例分批执行，每批准确 source HEAD 见 machine-summary.json；源码依赖字节保持相同，runtime 均绑定 d1ba。

batches/fan-r1 和 batches/rest-r1 保留原 HTTP、caller、source pin、PID/worker、UART/QOM、产品 DOM/HTTP、ZIP-before-stop、native frame 和 history/Flash/idle 清理证据。harness 保留作者 freeze、61项自检及全部作者尝试；review/authoring 保留114项独审，review/live 保留独立实际证据和24张 native PNG 的逐张审阅。失败尝试保留，不计入24 PASS。

源码作者阶段的旧 runtime 默认值、离线 PENDING 与历史失败均为原始过程证据，不继承为实际 PASS。每文件来源和 SHA 见 copy-provenance.json。除本 README 外，捕获的 Markdown 改名 .md.txt，内容字节不变，映射见 transport-paths.json。verification 保存 root 实际命令输出、工具调用的事后准确转录与同步 receipt；不把转录称为 OS exec trace。

为避免新增拷贝 MAC literal，只精确省略 network_fabric.py 与 ble_probe.py 两个间接依赖的 source-snapshot 复制件；原件不动，也不清洗字节。全部 caller/driver/真实 HTTP/ZIP/serial 均保留。因此本包不声称 source closure 全量字节入包。omitted-source-snapshots.json 保留每份省略的来源、SHA/size、原 freeze/嵌套 SHA 条目、固定 cba Git blob oid 和 git-show reference。两处属于静态虚拟 fixture，不是执行采集；需要源码复查时，从固定仓内 commit 用 git show 读取并核对 SHA256/size/Git blob oid。独立 audit 对这些条目验证 hash/reference，一律承认没有源码字节。

24 张 native PNG 已逐张目视；字符均在捕获框内，但 AtomS3R、StickS3、StopWatch 的 HUB 均为 numeric-token continuity PARTIAL / 排版待改善：长数值跨行拆开，StickS3 另有 eCO2 整数拆行。其余21张捕获图的数字 token 连续。该3项 layout issue 在 native-visual-final24.json、machine-summary.json 和 audit-report.json 明列；controller/UART/QOM functional24 PASS 独立成立。最终视觉分类取代旧增量 receipt 过宽的 READABLE 标签；旧文件原样保留。可读性只适用于实际捕获 PNG；不代表连续全帧保真。原 IR/Buzzer 风险、ADC fixture/oracle、其它 Unit/拓扑、共享 runtime 完整回归以及硬件、电气、声学结果均不由本包关闭。

独立离线复核：`python3 audit_archive.py --repo-root <repo>`。默认只读，不调用 API/guest/子进程。

RS485 的37字节 UART1 二进制 fixture 原样保留：仅三主机 evidence.zip 与各自准确 HTTP response ZIP 中的 serial1.log 共6份，实际 SHA256 为 `da4787a28a6eb88dbd2a6cd43c82b2bcf075dc57b1ad9a1ef3ce237df228c12f`。载荷严格等于原 probe/oracle 的 initial + echo-prefix + incoming，含 NUL/DEL/0xff；不清洗或删除。audit 绑定精确 locator、SHA、长度、原始 fixture 源码哈希，并继续扫描 ASCII 凭据；其它非 UTF-8/NUL 载荷仍拒绝。

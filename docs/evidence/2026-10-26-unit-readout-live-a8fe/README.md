# CoreS3 ENV III / Relay 实时读数：同 guest 证据

2026-10-26，两个实际 Device Service 会话均通过。执行使用 generation 9 和
Xtensa SHA `a8fe15dbe7299c5be4b52eeac68a6d0012578950d267287630760bf8bec7d047`；
本页只描述 CoreS3 的 ENV III 与 Relay，不扩大为 12 款读数或其他主机通过。
全部属于 virtual-device validation，物理硬件为 `NOT RUN`。

| Unit | 同 guest 结果 | 固件 SHA |
| --- | --- | --- |
| ENV III | 两个新输入向量都经实际产品控件、六次单字段 POST、QOM 和原驱动读回；第二向量从新的 serial offset 545 核对 | `8f1aa047a82ec2553de01508683f101130a72071a0b9e0ead62a5739ec24290f` |
| Relay | 原 guest 自动输出两态；浏览器零输入 POST，读数分别为 false / true | `67a68945395da60b604e45209b46e5b38071a464edab86044193321b09444600` |

ENV 两向量为 `31.5 °C / 67 %RH / 98765 Pa` 和
`18.75 °C / 45.5 %RH / 103200 Pa`。实际 readout DOM、UnitPanel 与捕获的
HTTP/QOM 字段精确对应。真实文字双击通过 elementFromPoint/actionability
命中读数，没有额外 mutation；两例均在实际 stop 后确认 live fields 为 0。

每例保持同 session/firmware、direct PID→runtime SHA、worker generation、
串口、native frame、冻结 Unit contract 和停止前 ZIP 绑定。停止采用
`purge=0`，历史保留、可变 Flash 释放；独立实时复核两例均 stopped、active 0。
ENV 外层 16 项、Relay 外层 17 项检查与各自 6 项 controller 检查通过。

- [逐例汇总](summary.json)、[ENV report](env-iii/report.json)、[Relay report](relay/report.json)
- [独立只读审核](independent-review.json)：330 项断言、28 artifact 引用、
  两 ZIP 共 20 成员 CRC/hash、两嵌入帧、全部 16 张磁盘 PNG 均已核对。
- [执行前源冻结](source-freeze.json)：26 命名源的 before/after SHA 与 .txt
  快照。四个新增相关 Web 资产在首次导航前另实取 HTTP 200 并验证 body SHA；
  其他源是本地冻结来源，不声称全部经 HTTP 单独证明。
- [辅助源连续性](auxiliary-source-reconciliation.json)：共享打包器还放入
  `rtc_probe.py`，不在原 26 个命名源冻结中。归档时从两份实际固件重新取出，
  与当前源及 .txt 副本逐字节匹配；生成 probe 没有导入它。这里明确是
  archive-time continuity，不倒填为执行前的完整依赖冻结。
- [白名单归档来源](archive-provenance.json)：复制报告引用工件及六份生成 probe
  源码；排除两个 full-flash BIN 与 bytecode，原始工件未修改、未脱敏重写。
- [当前产品检查](verification/summary.json)：完整平台 544 项、文档契约 39 项、
  读数 17 项、前端恢复 23 项与四项生成校验；检查日志的路径脱敏单独记录，
  不改变上面的原始执行工件。

读数数值、来源标签和 rail placement 在这两个场景通过，六张小图清楚呈现
两向量、两输出态和两个 terminal。整页构图保持 `PARTIAL`：ENV 历史卡片和
terminal 整页仍有 sticky header 遮挡标题边缘，不能称整页视觉验收。
各通道分别抓取，Relay framebuffer 与瞬时 DOM 可处于相反的自动切换阶段；
本批没有证明同一瞬间 LCD/DOM/控制器的原子一致性。

HUB housing 叠放、未确认的机械/LED 绑定、其他 host/Unit 与物理等价仍开放。
12 款 anchor/展示与离线语义证据分别见浏览器、语义归档，不继承为 12 个
实际 guest session。SHA256SUMS 覆盖本目录全部文件，自身除外。

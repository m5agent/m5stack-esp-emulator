# UIFlow2 同 guest 实时程序执行

日期：2026-10-26。结果：**virtual-device validation PASS**；hardware validation **NOT RUN**。
范围：仅 AtomS3R / `runtime=qemu` / 本次固件和运行时。不是 AIFlow 已接入、其它主机、RF 或物理设备结论。

## 固定身份与实际路径

- Session：`e586758b5d0e4934bb3bb8789da0a487`；同一 QEMU PID：`18464`。
- 初始化固件 SHA256：`f9880647d39c65b8619c55981a6ef9e271ea6f4a198ca68c506f360efc4ba9c6`。
- 实际运行时 SHA256：`d1ba0063f80f6f8bdeeaa831f0d16ce4004ff3692a2d0587663e121bb93f45ff`，使用 macOS proc_pidpath 核验实际进程。
- 服务实际加载源码与归档文件哈希逐一相等，见 [provenance.json](provenance.json) 与 `sources/`。
- 首次仅 compose/准备一次带 UART0 + os.dupterm/RX IRQ 的 UIFlow2 boot.py，并通过 8787 Device Service 创建可见 session；之后五次 `/program` 均经同一实际 UART FIFO/raw-paste/guest MicroPython，未重刷、重建 guest 或 soft reset。

## 验证与边界

1. 有限程序在 VM 内保存随机 sys.path 诊断标记并执行完成。
2. 程序 A 使用固件自带 PIRUnit((1,2))；冻结接线 white=GPIO1、yellow=GPIO2。motion 初始 false，依次 true/false/true，每次用新的串口 offset 确认 guest 的 1/0/1；保留 QOM 读回与屏幕。
3. 中断无限循环 A，程序 B 保留同 VM 诊断标记、改变屏幕与程序标签；实际两帧内容不同，见 [A](frame-a.png) / [B](frame-b.png)。
4. 再下发故意的语法错误，guest 返回 failed；随后修复程序完成，原 VM 标记仍存在。两段旧无限循环均在 raw prompt 同步后记录 interruption_confirmed。
5. 固件 SHA、PID 不变，串口只有一次 ROM/REPL bootstrap。每次执行独立 revision/source SHA；[evidence.zip](evidence.zip) 在停止前取得，完整检查 25 个成员的大小和 SHA256。停止 `purge=0` 后历史保留、Flash 已释放。

本次五个 HTTP 提交到执行标记确认用时分别为 0.215, 0.319, 0.328, 0.190, 0.208 秒。
这是小样本、单机、已启动 VM 的程序确认时间，包含 START/DONE/ERROR，**不是首帧延迟、AIFlow全链路、P95或SLA**。
详细请求耗时见 [http.json](http.json)，源码、状态和检查见 [report.json](report.json)。

使用 interrupt-only 清理；不保证 native 模块、IRQ、timer、线程归零。guest 原生阻塞或自行改UART/dupterm可令下次提交失败；没有静默重刷或重启降级。多文件同步、二进制 .mpy、Run Always 写回、Preview/SSE/帧生产者和其他主机仍不在本结果内。服务重连输出缺口保守标 unknown；该分支和stop/purge竞争由宿主测试覆盖，不继承为本次guest故障注入PASS。

## 重放

先启动本仓 Device Service 8787，使用已记录的 QEMU 二进制与 runtime assets，然后执行：

```bash
PYTHONPATH=platform/tools:tests/units:.work/py312 /opt/miniconda3/bin/python3.12 -B \
  tests/units/run_live_program.py \
  --api http://127.0.0.1:8787 \
  --expected-runtime-sha256 d1ba0063f80f6f8bdeeaa831f0d16ce4004ff3692a2d0587663e121bb93f45ff \
  --out-dir /tmp/m5-live-program-replay
```

该脚本只通过 Device Service 启动功能测试；不会直接启动 QEMU。正式调用采用部署的认证配置。
早期 .work 探针中的 builtins 属性持久性假设与 PIR yellow/white 接线错误已在测试fixture修正，未据其超时声称运行时缺陷。最终程序nonce使用 sys.path 的内存列表且 PIR 遵循 white 信号；保留的故意 SyntaxError 是恢复测试输入。

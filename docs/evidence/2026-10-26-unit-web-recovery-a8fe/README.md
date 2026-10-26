# 前端异步回退与松开请求故障恢复

2026-10-26，单个可见 CoreS3 Button session 的实际产品页面专项 **PASS**。
这份运行使用原 Button 驱动与既有 probe，不修改固件行为；firmware SHA 为
`8f2614cc852f5eaca4f72b824d499d27cbe5914edc6ef5b8b1b3c239b6fdbdf1`，
直接 PID executable SHA 为
`a8fe15dbe7299c5be4b52eeac68a6d0012578950d267287630760bf8bec7d047`，
worker generation 9。Session `70b0beb8577d4c499869c6a1ad350efb` 在停止前取得
ZIP，`purge=0` 保留历史并释放 mutable Flash，结束时 active sessions 为 0。

浏览器先延迟实际、未改写的 CoreS3 模型模块 HTTP 响应及随后列表刷新，调用
产品实际的 3D→2D 生命周期方法，随后交付晚到模型。真实 framebuffer 保留，
前后 frame SHA 一致；再恢复 3D，实际模型与 Unit 重新挂载。这个阶段用受控
传输时序与生命周期调用验证恢复，不宣称用户点击触发了四预览预算的自然降级。

之后通过可信鼠标事件按住 Button，guest 串口出现 `UNIT_BUTTON 0`。
真实松开时只丢弃第一次 `pressed:false` POST，并暂缓随后补偿请求以取得故障
观测：实际 `/units` 的 live controller 仍为 `pressed=true`、input-level=false。
恢复传输后，不添加新用户手势，产品自动补偿一次；controller 变为 released，
guest 串口出现 `UNIT_BUTTON 1`。再执行普通手势验证仍只有 down/up 两次 POST。
全程成功 POST 顺序为 true、false、true、false；另有一次明确中止的 false，
轮询不产生回声请求。故障注入不替换任何输入响应、QOM 数据或 guest 读值。

23 个命名源在执行前快照，包含产品、packager、服务、checker 与本次 runner；
浏览器报告的六个本地源 SHA 逐项匹配；其中实际 HTTP 交付的 sessions 模块和
延迟模型模块 body 也逐字验证，其余四个源未另做 HTTP body 指纹验证。
全部命名源在执行后保持相同；freeze 的执行前顺序依据冻结 runner，不是独立
时间戳证明。运行前后
PID/firmware/worker 及 binary hash 相同；ZIP 的全部 10 个成员、CRC、完整 hash
tree、running 状态、session/firmware/PID/worker 身份与 PNG 均已核对。
此清单是明确的工具来源边界，不声称封闭整个 Python/浏览器依赖树。

本次只关闭已复现的前端恢复问题，不扩展其它主机、Unit 或物理行为结论。
补偿只用于本客户端曾持有的 momentary 输入，每次松开意图最多自动补发一次；
同一输入的多客户端仲裁尚无服务端 ownership 协议。确定性错误、terminal、
dispose、重按和数组其它位保护见[离线故障回归](../2026-10-26-frontend-recovery-regression/README.md)。
物理硬件 **NOT RUN**，共享控制器未变，未重跑全矩阵。

- [运行结果](result.json)、[实际 HTTP/DOM 与故障观测](browser/report.json)
- [保留的 2D 帧](browser/stale-load-2d.png)、[原生帧](frame.png)
- [恢复页面上下文](browser/recovered-page.png)：长页面包含历史卡片，不作为整页视觉验收
- [执行前 source freeze](source-freeze.json)、[公共归档逐字节核验](validation.json)
- [独立只读审核](independent-review.json)：136项运行、来源及归档断言
- [停止前 evidence ZIP](evidence.zip)、[guest 串口](serial.txt)

复验命令（需要本机已启动且无活动会话的 Device Service）：

```sh
M5_PYTHON_DEPS="$PWD/.work/py312" \
PYTHONPATH="platform/tools:tests/units:$PWD/.work/py312" \
python3.12 tests/units/run_web_recovery.py \
  --out-dir .work/unit-web-recovery-new-run \
  --expected-runtime-sha256 a8fe15dbe7299c5be4b52eeac68a6d0012578950d267287630760bf8bec7d047
```

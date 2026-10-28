# 2026-10-28：Python Display.drawPixel framebuffer transaction 修复

## 范围

本轮重新定位 StopWatch `M5.Display.drawPixel` 不显示的根因。此前判断为
CO5300 单像素/偶数窗口限制；同源 trace 和 framebuffer code path 表明真正问题
在 Python binding：`gfx_drawPixel()` 直接调用 `drawPixel()`，没有执行
`startWrite()/endWrite()`。StopWatch 使用 framebuffer-backed panel，只有
`endWrite()` 的 auto-display 路径才会把 dirty range 刷到 CO5300。

全部结果为 **virtual-device validation**；物理硬件为 `NOT RUN`。

## 修复

`0024-display-draw-pixel-transaction` 在 Python `drawPixel` 外层增加嵌套安全的
`startWrite()/endWrite()`：

- 没有用户事务时，调用结束立即触发 framebuffer flush；
- 用户在 Python 中已显式 `startWrite()` 时，内部事务只增加嵌套计数，不会提前
  flush；用户 matching `endWrite()` 仍负责最终提交。

该修复不修改 CO5300 偶数窗口约束，也不伪造 framebuffer 值。framebuffer 的
`display()` 会把 dirty range 扩展到偶数边界，并从真实 framebuffer 保留相邻
像素。

## 结果

测试程序先做一个显式事务批次，再执行两个 standalone `drawPixel`。oracle 同时
检查红/绿事务像素、青/白 standalone 像素，以及 odd/even 相邻背景像素。

| 设备 | preimage | candidate | 结果 |
| --- | --- | --- | --- |
| StopWatch | `790184d2…b5d0` | `e13f7217…58ba` | preimage `FAIL`；候选 `FRAME_PASS` |
| StickS3 | `20b78359…3b95` | `2a20c3cf…ccb1` | 候选 `FRAME_PASS` |
| Core2 | `f3d37e56…e4e` | `6ab3b5c7…c826` | 候选 `FRAME_PASS` |

StopWatch candidate 实际像素：

- `(76,146)` → `(57,186,205)`，目标 `(56,184,200)`
- `(77,147)` → `(246,246,255)`，目标 `(243,247,248)`
- `(80,150)` → `(255,0,0)`
- `(81,151)` → `(0,255,0)`
- `(77,146)`、`(76,147)` 保持背景 `(8,16,16)`，目标 `(11,16,20)`

三台候选 frame SHA256：

| 设备 | frame SHA256 |
| --- | --- |
| StopWatch | `d458f64975504addf6531ed6c2fb38223693cd1db4f661d52d77cd3f38b1c974` |
| StickS3 | `2696612fa2c1b4ccc866e9a22e76119ba157e6e1dd51fbc5b8e3df36becc3858` |
| Core2 | `dd42971e4a2effb5866cebc65fc533399f8b31e8a57ce6389cf4461ca56849b3` |

## 证据身份

补丁 SHA256：
`18d55fc29f92bc701e6a9019aebe10d147e662488bbb8276198fc769589895e3`

compiled source SHA256：
`d66d11b7748cf80714f59a0c7943aa2c4bbb15488acedd9d7df69af64e8fbca9`

所有候选 base 均绑定 QEMU runtime
`21b7e34cc96560b4c8185131791008ae49fb1c6975a8428e4e344188a8236394`，
receipt 均确认 `outside_application_unchanged=true`、原始 source/library 未变。

## 复现

```bash
python3 tests/uiflow2/api_sweep/build_rawbuf_candidate.py \
  --build-root .work/api-sweep-20261028/candidate-existing-fixes/tool-root \
  --cached-build <matching-build> --base-image <preimage> \
  --manifest patches/uiflow2-api/0024-display-draw-pixel-transaction.json \
  --flash-size <flash-size> --out-dir <candidate>

python3 tests/uiflow2/api_sweep/run_guest.py \
  --api http://127.0.0.1:8788 --device <device> --runtime qemu \
  --source tests/uiflow2/api_sweep/probe_draw_pixel_transaction.py \
  --done-marker DRAW_PIXEL_TRANSACTION_DONE \
  --base-image <candidate>/candidate-full-flash.bin \
  --expected-base-sha256 <candidate-sha> --program-transport uart-repl \
  --out-dir <run>

PYTHONPATH=tests/uiflow2/api_sweep:.work/py \
python3 tests/uiflow2/api_sweep/analyze_draw_pixel_transaction.py \
  --run-dir <run> --out <run>/analysis.json
```

该修复是 incremental application relink，不是冷构建；物理屏幕、功耗和长期
framebuffer DMA soak 未验证。

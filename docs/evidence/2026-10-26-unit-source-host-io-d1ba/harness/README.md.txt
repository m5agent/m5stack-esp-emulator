# 三主机原 IO 源码 API harness

本目录只交付离线作者结果。AtomS3R、StickS3、StopWatch × PIR、DualButton、
Limit、Key、RGB、Fan、RS485、HUB，共 **8 种 / 24 组合**。实际 controller、
API、guest、浏览器和硬件均为 `NOT RUN`；离线自检不能替代运行验收。

范围由实际 registry 和 `prepare_host_io.resource_preflight` 确认。Angle / Light
六组合有 `adc_fixture_application_mismatch`；StopWatch 两组合另有
`adc_oracle_unit_mismatch`（white11 是 ADC2，原 oracle 固定 ADC1）。这不表示
Light 的 raw / digital 数据面整体不支持。原 IR / Buzzer 虽准入，但本轮显式排除，
历史风险和旧 BIN 批次结果不变，也不继承 custom wrapper 的 PASS。

`run_source_host_io.py` 逐字复制正式 `host_io_probe` 的五个 Python 文件、完整
原 `io_probe/io_drivers` 的十三个 Python 文件，再用正式 `config_bytes`
生成一份配置；每请求共十九个 caller `.py`。IR/Buzzer 两个 patch flag 均为
False。原 IO 初始化、负控、主循环、时序、官方 driver manifest 均受正式
`protocol_audit` 验证；不调用原 BIN prepare/builder，也不上传 BIN。

原 `Observations`、完整 `validate_io`、`validate_evidence` 直接调用，保留正式
host Montserrat12/native canvas/layout 和实际 BMI270 I2C1 读前后检查。RGB
继续要求 full → short negative → full、真实 RMT threshold/refill/completion；
RGB/Fan 是 output-only，必须零正向输入 POST。HUB 保留 ENV/NCIR/TVOC
三个独立 leaf driver、输入和 I2C 计数，HUB 本身没有 slave address。

每次 prepare 重读实际 base、SHA 和 partition table，明确 UART0=43/44、
external I2C0 与 internal I2C1 分离，以及 RS485 使用 UART1。原驱动和 guest
均不改写；这里只使用正式显示脚手架，字体/像素合同不等于可读性验收。

默认和 `--prepare-only` 会在 hard-deny 下准备：禁止 socket/HTTP、子进程、
浏览器、Client 构造和旧 BIN runner。`--check` 只离线回放已有证据；
只有 root 显式 `--execute` 才能执行 source API 和真实产品 Web bridge。

```sh
M5_PYTHON_DEPS=.work/py312 PYTHONPATH=.work/py312 \
  /opt/miniconda3/bin/python3.12 -B \
  .work/unit-source-host-io-20261026/run_source_host_io.py \
  --prepare-only \
  --out-dir .work/unit-source-host-io-20261026/authoring-next
```

当前作者默认 runtime 为旧 `29d8…d28d`，**只是可替换默认值**，不强锁它。
新 `0038` runtime 的真实 SHA、worker generation 和最终 source commit 由
root 在运行时核实并传入。此交付不冻结最终运行 source context。

root 执行前完成当前代码同步，确认真实 HEAD、runtime、generation、服务空闲，
然后在全新 output 中 fresh prepare + execute。不要复用作者 selfcheck 的目录。
下方三个任务变量应先填为 root 当时核实的值；脚本不会 fetch，也不会把传入
commit 当作自己证明了 fetch。

```sh
M5_UNIT_WEB_BRIDGE=1 M5_PYTHON_DEPS=.work/py312 PYTHONPATH=.work/py312 \
  /opt/miniconda3/bin/python3.12 -B \
  .work/unit-source-host-io-20261026/run_source_host_io.py \
  --execute --source-context-commit "${UNIT_HOST_IO_SOURCE_COMMIT}" \
  --expected-runtime-sha256 "${UNIT_HOST_IO_RUNTIME_SHA}" \
  --expected-worker-generation "${UNIT_HOST_IO_WORKER_GENERATION}" \
  --out-dir .work/unit-source-host-io-20261026/live-fresh-next
```

可重复 `--device` / `--case` 先跑子集。所有 API mutation 只允许源码 compose、
可见 lease、原 Unit input 和 `DELETE ?purge=0`；拒绝 artifact / merged / alternate
firmware intake。用 caller canonical CAS 的 `uiflow_source_sha256` 固定 session，
并核对返回 source metadata 的每文件、host base/VFS、composer ABI/config、
preservation 和真实 direct PID executable SHA、worker identity/generation。

每个正向输入保存真实 pre-input UART、QOM 和时间界；实时 wait 同时要求原 predicate
在新 suffix 内满足。离线回放再校验 guest 观测不跨入下一输入的 UART 上界，并调用
正式 `positive_input_binding`，逐字段核实真实产品 DOM action/POST；already-equal
no-op 需要真实 pre-input QOM。RS485 过大 FIFO 输入仍走原 API negative。

回放绑定每份 serial/QOM/state/frame/source compose/session metadata 的原始 HTTP
字节，并核对产品 DOM 与 browser HTTP。evidence ZIP 必须在 stop 前获取，原 ZIP
oracle 和 source/PID/worker/Unit contract 绑定不变。stop 必须留下 history、source
和 native frame，释放完整 mutable Flash，owned PID 退出、worker lease 结束且 health
回到零 active sessions。清理失败会停止后续 batch。运行帧、ZIP 帧、history 帧是
独立采样，不宣称原子同帧。可读性需要 root 另看实际 PNG。

源文件内容或清单、HEAD、Python/LittleFS ABI/文件、Node/Chromium executable、
Chrome bundle version 或 Playwright package 内容发生变化，必须重新 prepare。
执行中也不会把变化写入已准备 caller，而是拒绝继续使用失配的 freeze。

```sh
M5_PYTHON_DEPS=.work/py312 PYTHONPATH=.work/py312 \
  /opt/miniconda3/bin/python3.12 -B \
  .work/unit-source-host-io-20261026/run_source_host_io.py \
  --check --out-dir .work/unit-source-host-io-20261026/live-fresh-next
```

`offline_selfcheck.py` 验证全 24 请求、完整原协议/驱动、禁止执行、source/toolchain/
commit 漂移、runtime 参数化、caller 改动拒绝、旧 marker + 新无关字节拒绝、
下一输入上界拒绝。它不构造 fake Client，不运行 guest；synthetic UART 字符串只
测试 predicate/cursor 辅助函数，不生成 runtime PASS。

```sh
M5_PYTHON_DEPS=.work/py312 PYTHONPATH=.work/py312 \
  /opt/miniconda3/bin/python3.12 -B \
  .work/unit-source-host-io-20261026/offline_selfcheck.py \
  --out-dir .work/unit-source-host-io-20261026/selfcheck-next
```

`source_api_common.py` 仅逐字取用已审 source harness 的 hash/JSON/save/time、
透明 HTTP recorder 和 PID-exit helper；没有 CoreS3 base/profile 常量或执行函数。
具体来源见 `common-origin.json`。作者文件与最终自检位置见 `authoring-ready.json`。
早期 `selfcheck-r1` 保留了误用系统 Python 与 cp313 extension 不兼容的失败现场；
后续一律使用现有 conda Python3.12 + `.work/py312`，没有安装或更改环境。

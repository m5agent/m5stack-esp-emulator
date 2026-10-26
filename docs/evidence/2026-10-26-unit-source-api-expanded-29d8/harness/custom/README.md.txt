# CoreS3 IR / Buzzer：显式 custom 源码 API 验收

此目录是默认 IO9 harness 的独立 fork；默认仅 `ir` 与 `buzzer` 两例，始终输出 custom flavor。准备和检查默认离线。此交付没有启动 API、浏览器、QEMU 或 guest，没有生成或上传 BIN；运行结果仍是 **NOT RUN**。

实际入口是 `run_custom_io.py`，共享模块是此目录的 `source_api_common.py`。交付冻结文件见 `HARNESS_SHA256SUMS` / `delivery-freeze.json`。`customize_harness.py` 与 `custom_helpers.inc` 是准备过程草稿，不是执行或重建入口。

## 来源与变更边界

- 原探针 `tests/units/io_probe` 中 17 个 Python 文件逐字复制，增加原配置格式的 `probe_config.py`，每例共 18 个 caller 文件。12 个官方 driver 均对 manifest SHA 检查，只有本例目标 driver 的 caller 副本允许变化。
- 直接使用仓库 `prepare_host_io.custom_driver` / `strict_patch` 纯 helper。没有调用旧 `prepare`、`prepare_one`、镜像 builder 或 subprocess patch。
- IR 仅应用 `patches/uiflow2-unit-ir/0001-root-native-receive-callback.patch`；`IR_CALLBACK_ROOT_PATCH = True`。原 guest 启用 GC、注册后强制 collect，并保留 raw16 TX、独立 native packed NEC8 TX、有效 RX、坏 leader、repeat、重装接收全部原断言。
- Buzzer 仅应用 `patches/uiflow2-unit-buzzer/0001-accept-soft-timer-callback.patch`；完整保留 PWM 三阶段、once、原 `buzzer_timer_zero()`、TIMER_DONE、turn_off 原断言。自动归零必须由实际 HTTP 的串口→QOM→串口顺序重放，并通过原 `buzzer_timer_window()`；手动 OFF 无法补过。
- 每例保留原 driver、forward patch、reverse patch、还原字节与 SHA。反向使用同一零 fuzz parser，必须逐字恢复固定官方 SHA；仓库原 driver 与默认 IO9 harness SHA 不变。
- 原 `Observations`、`validate_io`、`validate_evidence`、`attachments`、`buzzer_timer_window` 全部直接调用，函数源码 SHA 冻结校验。记录器增加 fresh UART 和原始 HTTP 支撑，不缩短 timeout、不改原谓词。

只允许下列 flavor；checker 会拒绝原 flavor、原 driver 字节冒充 custom、缺 custom flag 或来源/hash 不一致：

| Case | Flavor | Caller source CAS |
| --- | --- | --- |
| IR | `custom-guest-ir-callback-root-patch` | `4851d70cb840e40dfecb8b2f6b403d4287df6a3e40330975e7568169450cb1bf` |
| Buzzer | `custom-guest-buzzer-callback-arity-patch` | `4e2395b6c8dc1447964bf1156ecea24e0fe7939cf2a8832a7a77d4c813a4a85c` |

这两个结果只能是 custom caller driver 的虚拟设备结果。原 published wrapper 继续由原 runner 独立执行、保留其 FAIL / REVIEW_REQUIRED，不能继承本目录的结果。

## Root 独占执行

从 integration worktree 根目录运行；每次使用不存在的新 output。当前冻结 runtime SHA 为 `29d8f6ecdc83f4cbd2ca013291b05bc9ef44fb438a115b0ca97f7b5d46d8d28d`，默认 worker generation 11。若 root 明确重启了 worker，应显式传正确的 `--expected-worker-generation`，不能跳过匹配。

```sh
M5_UNIT_WEB_BRIDGE=1 M5_PYTHON_DEPS=.work/py312 PYTHONPATH=.work/py312 \
  /opt/miniconda3/bin/python3.12 -B \
  .work/unit-source-custom-io-20261026/run_custom_io.py \
  --flavor custom --execute \
  --out-dir .work/unit-source-custom-io-20261026/live-custom2-r1
```

仅显式 `--execute` 会连接 loopback Device Service。源码通过 `POST /api/v1/firmware/uiflow`，session 必须携带相同 caller CAS 的 `uiflow_source_sha256`。禁止所有 binary intake 路径。每例独立可见 session、真实 product DOM/Web HTTP/控制器数据面、直接 PID/executable SHA/worker generation、ZIP 内 source 与 frozen Unit contract 绑定。先请求 ZIP，再 `DELETE ?purge=0`；执行时验证 owned PID 消失、Flash 释放、history/frame 保留和 service/worker 都 idle。

Buzzer 是 output-only：没有 guest 输入对应的 Web POST，要求真实 running DOM / HTTP readback。IR 四次输入必须按顺序有真实 Web POST。硬件验证为 NOT RUN。

失败也执行 retained-stop 清理；清理失败立即停止后续例。脚本最终重放失败会把 batch-result 改为 FAIL，并返回非零，不留下成功批次标签。

## 离线检查

现成 `prepared-r1` 和 `self-check-r2` 均只离线准备。自检硬拦截 HTTP/socket、进程、旧 prepare、builder、Client 和 BIN/ELF 写入；22 个负控涵盖 flavor/source/patch/zero-fuzz、binary intake、原 natural-zero 谓词及 HTTP 顺序解析。API/process/builder/legacy prepare/BIN 计数均为 0。

```sh
M5_PYTHON_DEPS=.work/py312 PYTHONPATH=.work/py312 \
  /opt/miniconda3/bin/python3.12 -B \
  .work/unit-source-custom-io-20261026/run_custom_io.py \
  --check-prepared --out-dir .work/unit-source-custom-io-20261026/prepared-r1
```

新的完整 deny 自检使用新的目录，例如 `--self-check --out-dir .work/unit-source-custom-io-20261026/self-check-r3`。terminal live 批次可以 `--check --out-dir <live-directory>` 只读重放；不能给未结束批次运行 checker。

离线重放不重新观察 OS PID：它复核执行时的 direct-PID 记录与 backed stop/history/worker-idle 响应。物理声学、红外光学、距离、功率、电气或真实硬件效果均不由此建立。

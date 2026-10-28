# 2026-10-28：ESP32 TIMG WDTFEED 写保护语义修复

## 范围

本轮修正 classic ESP32 Timer Group watchdog 的 `WDTFEED` 语义。官方向量来自
ESP-IDF v4.4.8：

- `wdt_hal_feed()` 对 MWDT 直接调用 `mwdt_ll_feed()`；
- `mwdt_ll_feed()` 只写 `TIMG_WDTFEED`；
- `wdt_hal_write_protect_disable()` 只用于配置写入，不是 feed 的前置条件。

旧 QEMU 把 `A_TIMG_WDTFEED` 整个分支放在
`!esp32_timg_wdt_protected()` 条件内，导致已锁定的 watchdog 丢弃合法
feed。新补丁只把 feed 路径移出保护条件，配置寄存器仍要求
`TIMG_WDT_WKEY_VALUE`。

全部结果为 **virtual-device validation**；物理 watchdog、复位电平和真机
时序为 `NOT RUN`。

## 修复

补丁：
[`0069-esp32-timg-wdt-feed-unprotected.patch`](../../../patches/qemu-m5stack-peripherals/0069-esp32-timg-wdt-feed-unprotected.patch)

SHA256：

`53b6557f0db174d8b0a280f354fbba42152f8c2918edfaf27b71de65c9cd04a8`

新 QEMU SHA256：

`78555183d53318fc25bc8413300e928d35bbbc1305f9d9648e97a73d34ce63b1`

C 合同：
[`test_esp32_timg_wdt_feed_patch.py`](../../../platform/tests/test_esp32_timg_wdt_feed_patch.py)

合同从补丁 postimage 提取真实 `A_TIMG_WDTFEED` 分支，在受保护状态执行：
feed 计数、stage/count 重置入口和 trace 数据均必须发生；配置写保护仍由原
分支断言保留。

## Core2 legacy 复测

同一公开 legacy Core2 镜像：

`4d2d648bd8707a1789d540366015a1b90dc816b66a04163048626ea29e333ed4`

在 `runtime=qemu-wifi`、TCG `shift=5`、TIMG trace 开启的 60 秒窗口：

- TG0 stage-0 timeout `7.252822559 s`，中断仍被 mask；
- TG0 stage-1 timeout `17.252822560 s`，首个 system reset
  `17.252907520 s`；
- TG1 在 reset 前完成 `14,993` feeds，最大间隔 `5.181212 ms`；
- reset 前 Serial 仍只有 MicroPython banner，没有 REPL；
- frame 为 `320x240`、`373` bytes，只有 `49` nonblack pixels，不能称为
  启动 UI。

该结果证明 0069 不会单独解决 `RUNTIME-03`：本样本的可见 feed 发生在
解锁窗口内，protected-feed 语义修复属于通用模型正确性，不是 startup UI
完成证据。此前约 5.9/15.9 秒结果继续作为 fixture/runtime 对照保留。

## 回归与边界

- `test_esp32_timg_wdt_feed_patch.py`：C 合同通过；
- `git apply --reverse --check`：通过；
- QEMU incremental rebuild：通过；
- 现有 WDT mask、stage/timeout 和 `INT_RAW & INT_ENA` 逻辑未改动。

`RUNTIME-03` 仍为 `OPEN`：原厂 startup UI、setup/REPL 和正常 WDT 下的
稳定应用运行仍未达到验收。物理硬件和 watchdog 电气行为为 `NOT RUN`。

## 复现

```bash
PYTHONPATH=platform/tools .work/issue-review-venv/bin/python3.12 \
  -m unittest discover -s platform/tests \
  -p 'test_esp32_timg_wdt_feed_patch.py'

ninja -C .work/M5StopWatch-QEMU/build/qemu/build \
  qemu-system-xtensa

PYTHONPATH=platform/tools \
  .work/issue-review-venv/bin/python3.12 \
  tests/firmware/core2_handoff_trace/run_wdt_liveness.py \
  --image .work/runtime03-original-vfs-probe/image.bin \
  --expected-image-sha256 4d2d648bd8707a1789d540366015a1b90dc816b66a04163048626ea29e333ed4 \
  --qemu .work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa \
  --attempts 1 --observe-seconds 60 --trace-sample 1000000 \
  --runtime qemu-wifi --out-dir <new-output-dir>
```

同一新 QEMU 上的 Core2 UIFlow2 `core2-peripherals` Device Service 回归也
PASS：`6612` nonblack pixels，绿色成功标记，TG0/TG1 feed 语义修复未破坏
UIFlow2 的 touch/RTC/PWR 路径。

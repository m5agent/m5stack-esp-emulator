# Buzzer SoftTimer callback 参数适配

这是显式 opt-in 的 custom guest 补丁，只应用到生成镜像中的
`io_drivers/buzzer.py` 副本。仓内固定官方驱动、base firmware 的 frozen
Haptic/SoftTimer 和 QEMU 均不修改，默认准备出的原版镜像保持相同 SHA。

官方 UIFlow2 commit `50e440780492aa847378c7d3477ab912f7063bac` 中，
`Haptic._cb(self)` 不接收 timer，而 `SoftTimerScheduler.update()` 调用
`tim.callback(tim)`。CoreS3 实际 frozen 模块也复现相同 TypeError：原始
`once(2000, 50, 2000)` 到期后控制器仍保持约 50%。独立 instrumented
诊断镜像直接记录了后台线程异常及退出；它与未插桩镜像是不同 SHA，结果分别保留。

补丁让 Buzzer 包装类接受可选 timer 参数，再无参调用原 Haptic callback。
原 guest 的 PWM 三阶段、once、定时等待和 turn_off 均不变。新断言必须在
`TIMER_DONE` 和任何后续手动输出之前，使用串口前后包围的实际 QOM 读回证明
2000 Hz / 0%；后续 `turn_off()` 不能给自动定时补 PASS。

```sh
python3.12 tests/units/run_io_cases.py --case buzzer --prepare-only \
  --buzzer-callback-arity-patch --out-dir .work/buzzer-custom-prepared
python3.12 tests/units/run_annotation_cases.py --case buzzer \
  --buzzer-callback-arity-patch --execute \
  --expected-runtime-sha256 <required-qemu-sha256> \
  --out-dir .work/buzzer-custom-readout
```

执行结果的 flavor 必须为 `custom-guest-buzzer-callback-arity-patch`，不能
升级原发布固件为 PASS。新的固件版本和不同 Haptic 实现需要重新验证。
实际证据和 getter 读回差异见
[主机问题记录](../../docs/unit-integration-host-issues.md)和
[专项证据](../../docs/evidence/2026-10-26-unit-buzzer-once-a8fe/README.md)。

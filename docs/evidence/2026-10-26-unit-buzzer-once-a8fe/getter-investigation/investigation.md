# Buzzer PWM getter 与 QOM 差异：只读调查

当前证据支持一个独立的 QEMU LEDC 读回缺口：写通路有 duty shadow 和 QOM observer，而读通路没有返回 DUTY/DUTY_R。它与 guest getter 始终 0、host QOM 按写入变化的症状相符。实际固件具体读取 DUTY_R 的动态 MMIO 路径尚未抓取，仍保留源码与二进制绑定界限。这个差异不能用来给原 once 自动归零补 PASS。

## 实际运行

输入记录为 `.work/buzzer-once-live-20261026-natural-r1`，custom natural SHA `f679d481358af9209847a851d4178986479e2012df7a95f7964f27a567fc2e6e`，runtime SHA `a8fe15dbe7299c5be4b52eeac68a6d0012578950d267287630760bf8bec7d047`。

- 29 条关联 natural-once 观察均为 guest getter `0`、QOM `49.98779296875%`；timer.dead 先 False 后 True。
- manual-haptic-before/after 的 21 条关联观察为 getter `0`、QOM `24.98779296875%`。
- direct no-arg callback 之后的 13 条关联观察为 getter `0`、QOM `0%`。
- 实际 bound callback(timer_arg) 与 detached scheduler.update(original callback) 都产生 TypeError；no-arg callback 返回并由 QOM 观察到零。

这些 serial/QOM HTTP 抓取不是原子快照。过渡处 latest_state 仍属旧阶段而 QOM 已属新写入；`observed-phase-summary.json` 保留全部分组，不能用过渡行制造阶段内结论。上述 natural 窗口和稳定手动阶段没有该混值问题。

## 固定官方源码链

UIFlow exact `50e440780492aa847378c7d3477ab912f7063bac` 的 root Git tree 将 MicroPython gitlink 固定为 `78ff170de9e32c79db6e64d3e33d2bd60002bdcd`。该 commit 的 `ports/esp32/machine_pwm.c:290-297` 使用 `ledc_get_duty(mode, channel) << (16 - resolution)`，因此 getter 不是请求 duty 的缓存。

实际 base 的 ESP app header 位于 `0x10000`，经过 header/magic/segment 验证的 app_desc 位于 `0x10020`，显示 V2.5.3、build Sep 23 2026、IDF `v5.5.5-dirty`。50e 的 README/CI 则写 v5.5.4。因此不能把 README 的 SDK 版本当成该 BIN 的实际 SDK，也不能把 upstream clean tag 当成 dirty 构建的完整源码证明。

作为版本对应的官方参照，ESP-IDF v5.5.5 annotated tag 已 peel 到 commit `b774170ff46c393eeb5e495ea37936038d3f4f4f`：

1. `components/esp_driver_ledc/src/ledc.c:1080-1087`：ledc_get_duty → ledc_hal_get_duty。
2. `components/hal/ledc_hal_iram.c:34-36`：HAL → ledc_ll_get_duty。
3. `components/hal/esp32s3/include/hal/ledc_ll.h:347-349`：读取 `channel[channel_num].duty_rd.duty_read >> 4`。
4. S3 `ledc_struct.h:56-62` 和 `ledc_reg.h:113-120`：DUTY_R 是 RO bits18:0；channel n 寄存器地址为 `0x60019000 + 0x14*n + 0x10`。
5. LL set_duty_int_part 在 `ledc_ll.h:332-334` 将整数 duty 左移 4 写 DUTY（同 channel 的 +0x08），读回读取 +0x10。

所有下载的 commit、URL、HTTP status、SHA 均保存在 `fetch-batch*.json`。一次 reg_base 旧路径 404 原样保留；成功文件来自其实际 register/soc 路径。

## 固定 QEMU 源码事实

`.work/unit-runtime-source-core2-compat/qemu/hw/misc/esp32_ledc.c`：

- `esp32_ledc_read:22-62` 初始化 `r=0`，只处理 timer、global conf、channel conf0；无 DUTY(+8)、DUTY_R(+0x10)、CONF1(+0x0c) 读分支。
- `esp32_ledc_write:126-147` 处理 duty 写入并保存 `channel_duty_reg`，随后 `ledc_observe` 将 shadow 交给 `m5_unit_pwm_observe`。
- `m5_unit_gpio.c:185-198` 由该 shadow 计算频率/占空比并更新 QOM。这是 setter/observer 方向，与 guest getter 的 MMIO read 方向不同。
- S3 board 显式设 `esp32s3-layout=true`；S3 channel 采用 0x14 stride，从 0x00 开始。缺少的读取不是简单混淆 ESP32 classic 的 LS channel +0xA0 偏移。

## 假设优先级与最小实验

1. **最强候选：DUTY_R 读取未实现。** 源码缺口已确定；实际 BIN getter 的动态地址仍待验证。下一次独立 custom diagnostic session 保留同 base/runtime，在稳定 0/25/50/0 duty 阶段打印 PWM repr/getter，并只读 `machine.mem32` 的全部 8 个 channel CONF0、DUTY、CONF1、DUTY_R 及 timer config，持续保存同 session QOM。该 runtime 连 DUTY 的 guest read 也缺失，预期 raw DUTY 与 DUTY_R 都是 0，而 QOM 非零；这只能证读回缺口一致性，不能证明物理 PWM 波形。
2. **实际 dirty SDK / PWM 编译实现与 clean source有差异。** 想把候选升级为实际读取地址证据，在父代理拥有的新可见 session 中，用原 a8fe runtime 的调试符号/现有 MMIO trace 记录 getter 窗口进入 `esp32_ledc_read` 的地址；或取得 app ELF/map，核对应函数的反汇编。先验证 binary 符号/trace 能力，避免为诊断立即改 QEMU。
3. **channel/布局或寄存器更新语义有其他缺口。** 同样用 8-channel raw MMIO 与实际访问地址消除索引假设。未来若实现读回，回归应覆盖 channel 0/7、S3 与 classic 不同布局、duty update/disable 和量化；不能仅在 Python getter 层返回 requested duty，也不能从 shadow 直接推导 fade/锁存/物理行为已正确。

本次只写调查目录，未改 QEMU/patch/product，未访问 Device Service、启动 session、运行 QEMU 或固件。

# UNIT-HOST-37 控制器组合 C 证据 r1

2026-10-27：**C 逻辑 PASS；共享 CoreS3 runtime 回归 FAIL，当前候选未接受。**

本目录固定的是修复共享回归之前的控制器验证阶段。后续修复必须另建证据，不能覆盖这里的原始源码、结果或旧失败。

## 验证范围

- 整翻译单元方式直接包含真实 GPIO、AW3641/其他 GPIO Unit、RTC pad aux 源码及真实头文件。仅 QEMU 时钟、QOM、IRQ、MemoryRegion 等宿主运行设施使用 shim；40 个独立进程场景通过。该方式使用已有 QEMU 生成配置及宿主 glib，原始编译命令含私密宿主路径，因此不归档命令和警告正文；只保留其指纹及分类。
- 标准 C 方式从固定 QEMU 提交 `40edccac415693c5130f91c01d84176ae6008566` 的原始空 GPIO stub/header 出发，按 bootstrap 的完整补丁顺序严格重放涉及的六个源文件；原样抽取 GPIO 连续控制器/MMIO/reset/IOMUX/init、AW3641 整个模型及 aux 源码。40 个场景全部通过，使用 `-Wall -Wextra -Werror` 编译，无需现成 `.work`、QEMU 配置、glib 或联网。
- 两种方式都保留同一冷路径在旧真实 GPIO/AW 源码上的失败：500001ns 时仍未知，`low=-1 reset_at=-1 edges=0 rising=0`。旧板级源码把 IOMUX 注册为 unimplemented region；旧路径没有伪造新 IOMUX API。原 stdout/stderr 原字节保留。
- 原始六个源文件 SHA 与独立的 fresh final 完整源码重放逐文件相同。这里保留原文件及其原 SHA，所有归档文件另有独立 manifest 校验。

关键场景包括冷 route→ENABLE→IOMUX 无假边沿、500000/500001ns 边界、同值写和等价 bit10 配置、OUT_INV/OEN_INV 真实边沿、15 类来源 writer、直接及 MMIO open-drain、Flash/Torch 高电平来源往返、未知期间低历史隔离、延迟 reset callback、普通 GPIO reset 保留 RTC mux/hold、恢复后的完整新低区间、旧 Flash timeout fencing 及生命周期清理。

## 当前未接受原因

父任务的窄共享回归发现 CoreS3 两条既有路径的初始画面空白，外设 probe 输出 `CORES3_POWER -2 0 1`；Core2 AXP 旧路径通过。该失败尚未由本阶段解决，摘要见 `shared-runtime-regression.json`。C 组合通过不能替代这一共享运行路径的验收。

本任务没有调用 Device API、运行新 Unit guest/Web、重启服务、构建完整 runtime、部署或操作物理硬件。纳秒阈值来自模型内虚拟时钟，不能解释为硅片、电气、光学或真实设备测量。

## 独立复验

```sh
python3 verify.py
python3 verify.py --run
```

默认逐文件验证 SHA、长度、原源码指纹、原始输出指纹及保留失败。`--run` 仅编译本目录的标准 C 程序，重跑 40 个候选逻辑场景和旧源码失败负控，不启动 QEMU 或 guest。

仓库永久测试入口是 `platform/tests/test_unit_flashlight_cold_pad_patch.py` 和其 C fixture；本目录保存只读副本。初期 harness 的 alternate-layout getter 错误假设及 portable 输出目录命名冲突均只修正了测试，未改模型算法；原失败继续保留于内部工作证据，分类记录在 `source-provenance.json`。

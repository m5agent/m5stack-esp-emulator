# Unit 首批控制器运行证据

日期：2026-10-26。类别：`virtual-device validation`。整批 `UNIT-01` 仍进行中。

本目录保存 CoreS3 上 Button、Relay、ENV III 的 Device Service 执行结果。
固件、会话、探针、串口、画面和 ZIP 的 SHA256 在各型号 `result.json`；
汇总及实际使用的 QEMU/ROM/工具指纹在
[`tests/units/evidence-2026-10-26-service-first3.json`](../../../tests/units/evidence-2026-10-26-service-first3.json)。

三款均在同一 guest 内执行官方 UIFlow2 驱动：Button 接收四次按放并读取真实
GPIO，Relay 产生交替输出并读回模型电平，ENV III 经 SHT30 CRC 和 QMP6988
校准补偿得到注入温湿压。每份证据包含非空应用 PNG、运行态 QOM、停止前
取得的 ZIP，以及 `purge=0` 后可读的 session 历史。ZIP 内保留冻结的 Unit
schema/映射和来源 hash；不含固件、ROM 或运行时可执行文件。

基础固件为官方 CoreS3 UIFlow2 v2.5.3，SHA256
`1324f12d3ddd5392f47a9eff537f9ce0b01a8e6e36d829b6bd22cdf82d2c1264`。
实际执行的是各自写入 probe 后的镜像，不能把基础固件 hash 当作 probe hash。
QEMU 为 `732d137bf03acd2cadbe686d182f4ea737bb41193f61b48caaa59a5630794c1f`。

复现：先按 [`QEMU bootstrap`](../../../patches/qemu-unit-runtime/README.md)
准备运行时，再启动 8787 的 Device Service，并执行：

```sh
M5_PYTHON_DEPS="$PWD/.work/py312" PYTHONPATH="$PWD/.work/py312" \
  /opt/miniconda3/bin/python3.12 tests/units/run_service_cases.py \
  --case all --out-dir /tmp/m5-unit-first3
```

解释器和依赖目录是本次主机配置，其他环境应使用兼容的 Python 3.10+ 与
littlefs-python/esptool。probe 显式写 UART0，避免把 USB CDC 的 `print`
控制台误当成服务串口。最早的超时和无 Unit 对照保留在本机临时证据中，
未被改写成 Unit PASS。

本结果没有覆盖其余 Unit、其他主机、Web 全链路、加入 Unit 后的完整回归矩阵
或物理硬件；这些门禁仍为 `NOT RUN` 或进行中。其他分组的结果单独归档。

同日追加的独立分组证据：

- [七款 I2C sensors 汇总](../2026-10-26-unit-sensors-service/aggregate.json)：
  官方驱动、两次同会话输入变化、负向协议检查、Thermal 两原始子页扰动、
  串口、画面、总线计数、取证及保留历史；独立无 fixture 负向另记。
- [Button 实际浏览器联动](../2026-10-26-unit-service-browser/report.json)：
  产品 Sessions 页 DOM 按放进入同 guest，真实 QOM 与外壳行程读回，
  WebGL 降级/恢复、无输入回声和持久化取证。
- [Key 实际浏览器输出](../2026-10-26-unit-key-service-browser/report.json)：
  同 guest 的 RMT LED 输出经过 QOM 显示到外壳单灯，保留真实按放与画面。
- [控制类结果目录](../2026-10-26-unit-controls-service/)：各型号独立报告；
  `rfid2-attempt1` 是探针访问官方 UID 类缺失字段的失败探索，不能计为 PASS；
  `joystick-v11-settled` 保存可读稳定帧的补充运行。

这些分组不能互相拼接成另一个固件 SHA 或另一主机的整机 PASS；完整批次、
机械绑定缺口与共享控制器回归以当前状态和 `UNIT-01` 验收为准。

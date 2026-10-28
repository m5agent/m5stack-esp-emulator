# 2026-10-29：Core2 legacy SSI command issuer PC

## 结论

新增 `0073-esp32-ssi-command-pc.patch`，在 `0072` 的
command-length、per-command gap 和 transition 表上增加有界稀疏
`command / CPU / transaction-issuer PC` 表及 overflow 计数。该表只在
显式 freeze 时输出，不修改 SPI 数据、调度、watchdog 或 accelerator。

同一 public `UIFlow_Core2 v1.15.4` SHA 的 80 秒 WDT-off 控制记录
`105,161` transactions；command/CPU/PC 表总数同样为 `105,161`，
overflow 为 `0`。主要请求绑定为：

- `0x05` RDSR 共 `49,972` 次，其中 `49,961` 次来自
  `0x4006222c`（CPU1 `49,200`、CPU0 `761`）；
- `0xBB/64` Fast Read 共 `49,783` 次，其中 `49,452` 次来自
  `0x40093b57`（CPU1 `49,027`、CPU0 `425`）。

`0x4006222c` 不在应用 ELF segment 中；在 Espressif IDF v5.5.4 的 ESP32
ROM linker symbols 中，它位于
`esp_rom_spiflash_read_user_cmd=0x400621b0` 与
`esp_rom_spiflash_read_status=0x4006226c` 之间，因此只能称为 ROM
status/read-command 区间的 issuer PC。

`0x40093b57` 位于 normalized BIN 的应用 segment 5：

- load address `0x400924d8`；
- length `0x1187c`；
- file offset `0x50728c`。

该 PC 落在 segment 内 offset `0x167f`，附近是一段带多次 `memw` 和
20-byte copy 的 IRAM 路径。没有 matching legacy ELF/MAP 时不能把这段
地址命名成精确函数；原始 PC 也可能落在一条指令内部，因此本证据只做
BIN-bound 区域绑定。

`RUNTIME-03` 仍为 `OPEN`。本轮没有证明 pre-BOARD/APIKEY 的缺失
controller/DMA/IRQ 语义，也没有完成 startup UI、setup/REPL 或非空
应用帧。

## Command issuer PC

| Command | Issuer | Count |
| --- | --- | ---: |
| `0x05` | CPU1 `0x4006222c` | `49,200` |
| `0x05` | CPU0 `0x4006222c` | `761` |
| `0x05` | CPU1 `0x40062226` | `9` |
| `0x05` | CPU0 `0x40062291` | `2` |
| `0xBB` | CPU1 `0x40093b57` | `49,027` |
| `0xBB` | CPU0 `0x40093b57` | `425` |
| `0xBB` | CPU0 `0x40093b07` | `322` |
| `0xBB` | CPU1 `0x40093b54` | `9` |

两行高频绑定分别覆盖当前 `0x05` 的 `99.978%` 和 `0xBB` 的
`99.335%`。稀疏表 overflow 为 `0`，command PC 总数与 controller
transaction 数一致。

## 同 artifact WDT 控制

冻结后的 QEMU 副本随后用于 normal-WDT 控制，两个结果的 runtime SHA256
均为 `e2efbc675799eac10faaf789fcde2f9b07a09a9f532a08c9277f95426cf41866`。

normal-WDT：

- TG0 stage-0：`7.253606494 s`；
- TG0 stage-1：`17.253606494 s`；
- first reset：`17.253607230 s`；
- reset 前 TG1 feed：`14,998`；
- TG1 最大 feed interval：`3.926687 ms`；
- reset 前最后 feed 距 reset：`0.813376 ms`；
- TG1 timeout：`0`；
- classification：`BOOTLOADER_TG0_STAGE1_RESET_WITH_TG1_LIVE`。

serial 仍包含 MicroPython banner，但没有 REPL prompt；frame 仍不是
应用完成证据。`0073` instrumentation 没有改变 reset 边界。

## 并发 runner 修正

三设备并发复测期间观察到 `run_wdt_liveness.py` 的
`free_port() -> Popen(serve.py)` 存在端口竞态：一条控制因本地服务未持有
预期状态目录而丢失原始 stderr。`run_wdt_liveness.py` 和
`run_pause_sweep.py` 现在支持显式 `--service-port`，并发诊断可以预先
分配端口；默认自动探测行为保持不变。首轮缺文件控制只保留为失败控制，
未进入结论。

## 身份

| 项目 | 值 |
| --- | --- |
| Firmware | `UIFlow_Core2 v1.15.4` |
| Firmware SHA256 | `4d2d648bd8707a1789d540366015a1b90dc816b66a04163048626ea29e333ed4` |
| QEMU SHA256 | `e2efbc675799eac10faaf789fcde2f9b07a09a9f532a08c9277f95426cf41866` |
| 0073 patch SHA256 | `3655b5b3b22bc7df0b745d1205b0a19619075871b51e1b4472c9f37775710f1e` |
| WDT-off evidence SHA256 | `8ba94ec22a9cc29d70e4ebd162e842f9dd25dd417abb56729d3cee63a81cedc9` |
| WDT evidence SHA256 | `2e0c91824956dd8e4316b0402dfd357bc27f7a3b92e2f4511bfd0f31d247c5ae` |
| WDT-off stderr SHA256 | `c766bbd7f903a38a0516655d7418ad470a475e89a606b65cae0ce29426cb677d` |
| WDT stderr SHA256 | `8895f76e50636b61bcdc791174251301c4f84b3c290ff1407cef660654e6439b` |
| Hardware validation | `NOT RUN` |

全部为 virtual-device validation；物理 Flash/cache、RF、电气、实时性能和
真机行为均未验证。

## 边界与下一步

- `0x4006222c` / `0x40093b57` 是同一 BIN 上的 issuer PC，不是从其他
  UIFlow2 ELF 猜出的函数名；
- normal-WDT first reset 仍早于 BOARD/APIKEY，不能把 WDT-off 的
  `CORE2_LEGACY_ORIGINAL_BOOT_DONE` 当成 normal-WDT 启动成功；
- 下一项应结合 transaction-bound PC、IRQ delivery、cache/MMU 状态和
  matching legacy source/ELF/MAP，判断这条 `0xBB/64 -> 0x05/1` 路径为何
  在 normal-WDT 下消耗超预算；
- 扩大 timeout、关闭 WDT、accelerator override 和 host-side bypass 都不是
  产品修复。

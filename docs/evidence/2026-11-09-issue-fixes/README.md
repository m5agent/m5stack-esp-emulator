# 2026-11-09 开放问题修复

基线 `dd2eb35d2e6a909992268089ddc37e27970d4a92`。目录资料核对为静态验证。原生用例使用同一报告中的 QEMU `27df1b40de946c694b8c193ad850668118eea8656f0308e6e77b322f0b2c695e`，分别记录实际固件与运行结果。

| 问题 | 修复与范围 |
| --- | --- |
| [#178](https://github.com/m5agent/m5stack-esp-emulator/issues/178) | 已确认的 ROM stub 上传 `0107` 或串流中断触发一次有界重试。Atom Lite 首次实际失败，倍率 8 重试读回一致并完成 guest 验证。Core2、StickC 与独立服务冷烧录同样通过。 |
| [#190](https://github.com/m5agent/m5stack-esp-emulator/issues/190) | NanoC6 `C125`、Dial `51 × 51 × 32.3 mm`、AtomS3R-CAM `24 × 24 × 13.5 mm`。生成设备档案与目录来源一致。 |
| [#191](https://github.com/m5agent/m5stack-esp-emulator/issues/191) | Joystick2 `U024-V2`，ENV-Pro 仍为 `U169`。更新 TimerPWR、Step16、DoF6、CardKB2 公开驱动来源和 ADC v1.1 已更正的资料。保留 ENV 精度差异及独立运行边界。 |
| [#192](https://github.com/m5agent/m5stack-esp-emulator/issues/192) | StackChan 和 Core2 AXP192 在原 settle 后先等待探针就绪再按现有帧判据等待基线，轮询窗口 10 秒。保留原像素、串口和 after 判据。最终两例首轮通过。 |
| [#193](https://github.com/m5agent/m5stack-esp-emulator/issues/193) | 3 个 Unit runner 输出实际执行身份。19 个定向用例 PASS / VERIFIED，错误 SHA 负控 FAIL。每次运行保留历史和证据 ZIP。 |

官方产品规格见 [NanoC6](https://docs.m5stack.com/en/core/NanoC6)、[Dial](https://docs.m5stack.com/en/core/Dial)、[AtomS3R-CAM](https://docs.m5stack.com/en/core/AtomS3R-CAM)、[Joystick2](https://docs.m5stack.com/en/unit/Unit_Joystick2) 和 [ADC v1.1](https://docs.m5stack.com/en/unit/Unit_ADC_v1.1)。公开 UIFlow2 驱动核对固定在 [f20d5a00](https://github.com/m5stack/uiflow-micropython/tree/f20d5a00e8c9106aae1d944f3d6f1128839f59cb)，目录条目列出对应驱动与文档。

- [目录来源与静态核对](catalog-summary.json)
- [Classic 烧录失败、恢复与运行验证](classic-flash-summary.json)
- [StackChan 与 Core2 帧观察对照](peripheral-readiness-summary.json)
- [三组 Unit 的运行时身份和失败负控](unit-runtime-summary.json)

旧版两项帧用例在负载 10.06–18.44 时复现黑帧。最终代码在负载 6.73–8.68 下通过两例。高负载启动条件在最后一轮未达到，完整的两轮 68 项高负载矩阵仍待验收。Classic 的重复高负载稳定性继续保留在 backlog。

[#188](https://github.com/m5agent/m5stack-esp-emulator/issues/188) 本轮复核上游最新正式版本仍为 [esp-emu 0.51.0](https://github.com/espressif/esp-emulator/releases/tag/v0.51.0)。其既有 DSI PHY 阻塞仍列在 backlog，未重新运行官方 Tab5 镜像。

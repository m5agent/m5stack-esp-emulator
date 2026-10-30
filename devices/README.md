# 设备档案与运行时登记

本目录保存设备的硬件档案、固件来源和运行时登记。当前型号、后端及未完成项
统一查看[自动项目快照](../docs/project-snapshot.md)和
[项目当前状态](../docs/project-status.md)；逐次验证见[证据台账](../docs/validation-ledger.md)。

## 登记来源

| 文件 | 职责 |
| --- | --- |
| [`catalog.source.json`](catalog.source.json) | 可编辑的设备源清单：型号/修订、SoC、内存、接线、固件来源、状态与 blocker |
| [`catalog.json`](catalog.json) | 供页面使用的生成目录 |
| [`platform/qemu/profiles.json`](../platform/qemu/profiles.json) | 原生后端、machine/profile 与运行时要求 |
| [`platform/peripherals/catalog.json`](../platform/peripherals/catalog.json) | 外设组件、数据面、设备本地覆盖与完成度契约 |
| [`platform/web/qemu-browser-profiles.json`](../platform/web/qemu-browser-profiles.json) | 浏览器执行的逐设备准入和固件配置 |

原生后端登记、浏览器准入和三维外壳是不同范围。浏览器运行还需匹配构建中的
machine/profile、固件与该设备的执行证据；只有外壳的型号可以浏览模型，
不能因此获得固件兼容性。Tab5 的 P4 路径与 CardputerZero 的 Linux 后端
分别验收，不继承其它 ESP32 型号的结果。

## 目录导航

| 目录 | 档案分组 |
| --- | --- |
| [`esp32-s3/`](esp32-s3/) | ESP32-S3 主控 |
| [`esp32-c6/`](esp32-c6/) | ESP32-C6 主控 |
| [`esp32-lx6/`](esp32-lx6/) | 经典 ESP32 / LX6 主控 |
| [`esp32-p4/`](esp32-p4/) | ESP32-P4 主控 |
| [`linux-arm64/`](linux-arm64/) | 独立 Linux ARM64 设备 |

每个设备子目录的 `device.json`、`firmware.json` 和 `README.md` 来自源清单。
`index.html` 指向该设备入口；设备专用补充说明放在 `README.extra.md`，生成时
会合并到设备 README。此根索引为维护导航，不由目录生成器重写。

`reference-ready`、`headless-ready` 等标签说明已登记的参考路径，
`backend-required` 表示使用独立固件族/后端，不能解读为后端尚未实现。
这些标签不表示所有外设、SDK 或上传固件均兼容；组件的 `partial`/`planned`
与具体 blocker 仍以外设契约和当前状态为准。

## 维护与准入

修改 `catalog.source.json` 后，从仓库根目录生成设备档案并校验跨目录契约：

```sh
python3 platform/tools/generate_catalog.py
python3 platform/tools/qemu_profiles.py --check
python3 platform/tools/peripheral_catalog.py --check
python3 platform/tools/runtime_coverage.py --check
```

生成器更新 `catalog.json` 以及各设备的 JSON、README 和入口页；profile 与外设
登记仍需按各自契约同步维护。不要直接修改生成文件来隐藏源清单的缺失。
新增设备的官方硬件依据、控制器/总线接入、设备本地探针和覆盖登记步骤见
[设备维护指南](AGENTS.md)与[外设契约](../platform/peripherals/README.md)。

兼容 UIFlow2、Arduino、ESP-IDF 或其它固件，需要逐一确认芯片、board profile、
Flash/PSRAM、分区/镜像布局、eFuse/安全配置和控制器覆盖。某个参考固件通过，
不授予同型号全部 SDK 或其它镜像相同结论。

## 验证入口

[测试总索引](../tests/README.md)区分平台契约、设备/外设回归、网络和独立后端。
显示/输入回归由 [`device_matrix.json`](../tests/uiflow2/device_matrix.json)与
[`run_device_matrix.py`](../tests/uiflow2/run_device_matrix.py)选择具体 backend、
镜像组合、虚拟烧录传输及断言；外设数据面另按设备本地 case 验证。

直接 runner 用于仓库回归开发和复现。一般固件功能测试使用可观察的独立
Device Service session；浏览器 WASM 使用其独立静态站验证路径，见
[功能测试流程](../docs/device-functional-test-workflow.md)。
所有仿真结果属于虚拟设备验证，物理 RF、功耗、声学、光学、机械和电气行为
仍需同路径硬件证据。

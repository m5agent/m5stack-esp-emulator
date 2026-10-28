# 纯浏览器执行可行性：esp-online-tester 对照

核查日期：2026-10-28。对照仓库固定在
[`3cd3db3b7202e9fc559328c7247c11134c0437f9`](https://github.com/zhuzhe1983/esp-online-tester/tree/3cd3db3b7202e9fc559328c7247c11134c0437f9)。
本仓库调查基线为 `2740fd767478a6599ce4d5533cb5d1b345730222`。

## 结论

GitHub Pages 可以托管真实固件仿真：前提是 CPU、板级控制器和输入/显示路径
已经被编译到浏览器可用的 WASM，并在浏览器中接好。不能把“本仓库当前经过
验收的主路径是 native QEMU”推成“纯网页不可行”。

对方支持的板型在浏览器 Worker 内运行 CPU 和板模型，不依赖服务端 QEMU。
它使用 `mikroverk/esp32sim` 的 MIT fork，和本仓库 vendored Apache-2.0
`esp-emu 0.49.0` 是不同项目。已有两个 WASM 文件体积相近，真正待迁移的是
板级数据面和验证范围，不是 HTML 托管方式。

## 执行链路证据

- [`wasm/Cargo.toml`](https://github.com/zhuzhe1983/esp-online-tester/blob/3cd3db3b7202e9fc559328c7247c11134c0437f9/wasm/Cargo.toml)：`esp32sim-wasm` 直接依赖本仓库的 ESP32/S3/C3/C6/P4 芯片模块与 Xtensa CPU，使用 `cdylib`。
- [`runtime.js:511`](https://github.com/zhuzhe1983/esp-online-tester/blob/3cd3db3b7202e9fc559328c7247c11134c0437f9/web/platform/runtime.js#L511)：下载 WASM，创建 Worker，经 `postMessage` 传 WASM、固件与配置。
- [`worker.js:159`](https://github.com/zhuzhe1983/esp-online-tester/blob/3cd3db3b7202e9fc559328c7247c11134c0437f9/web/wasm/worker.js#L159)：`WebAssembly.instantiate`；调用 `esp32sim_new`、`esp32sim_boot`、`esp32sim_run`。没有将这条产品 CPU 执行链交给后台 QEMU。
- [`exec.rs:233`](https://github.com/zhuzhe1983/esp-online-tester/blob/3cd3db3b7202e9fc559328c7247c11134c0437f9/xtensa-lx7/src/exec.rs#L233)：真实 PC fetch、decode、执行指令与中断处理；不只是绘制固件效果。
- [`tools/wasm-build.sh`](https://github.com/zhuzhe1983/esp-online-tester/blob/3cd3db3b7202e9fc559328c7247c11134c0437f9/tools/wasm-build.sh)：Rust `wasm32-unknown-unknown` 构建，Pages 工作流再打包公开资源。

“无需后台 QEMU”不意味着任意固件、任意外网连接、所有外设或真机行为均支持。

## 覆盖范围不能用目录数代替

固定源码的 `web/platform/catalog/products.json` 共 86 项：29 项有
`runtime.board`，对应 28 个不同 board；其余 57 项没有运行板型。
本轮从线上再次下载的目录与该固定源码逐字节相同。上述数字是目录统计，
不是 29 个整机功能 PASS；线上 CoreS3 为 unavailable，PaperS3 与 StopWatch 为 partial。

| 对照路径 | 可核查的实现与证据 | 保留边界 |
| --- | --- | --- |
| PaperS3 / C139 | `esp32s3/src/board/papers3.rs` 与 `bus/dma.rs`：GPIO/供电、GDMA i80 路由、ET047TC1 行与锁存；GT911 和 BMI270；仓库有未改官方 v0.5 固件的运行收据 | 黑白端点；RTC、TF、音频、物理电源键缺失；灰阶/联网未验证；不等于 PaperS3 UIFlow2 已通过 |
| CoreS3 | 产品目录中 `runtime.board=null`、`status=unavailable`；UIFlow2 v2.5.3 固件为 `trial`、`simulationVerified=false` | 3D 模型、固件链接和其他板的 LVGL demo 不能证明 CoreS3 可跑 |
| Unit 物理路径 | `web/platform/accessory-routing.js` 明确限定 StopWatch 下 Button/G11、RGB/G10、Angle/G11、Hub；自建 IDF fixture 有真实 GPIO/RMT 与错误接线/拔插负控 | 不是所有主机/Unit，也不是原厂 UIFlow Unit API 全兼容 |
| GPS / C6L 配件 | GPS 为逻辑 UART 注入；C6L 为 visual-only | 不能把目录或接线动画当控制器数据面 PASS |

PaperS3 历史收据见
[`factory-wasm.json`](https://github.com/zhuzhe1983/esp-online-tester/blob/3cd3db3b7202e9fc559328c7247c11134c0437f9/docs/platform/evidence/papers3/factory-wasm.json)：
固件 SHA256 `d6733a0ca378f95335fa5fba4d4d992fb1dd97c17557b20e9aebfca08ba6d624`，
WASM SHA256 `fa99bc5efd208b4e2c2d6bad7e001de3b0d4de060fa79ee6632c767438e42ff6`。
该收据来自对方仓库，本轮未重跑；本轮下载到的线上 WASM hash 已不同，不能
把历史收据写成本次线上功能验证。

## 资源体积

| 对象 | 原始字节数 | 本地 gzip 字节数 | 说明 |
| --- | ---: | ---: | --- |
| 对方线上 `wasm/esp32sim.wasm` | 4,213,748 | 1,176,777 | 完整 HTTP 200 下载并通过 WASM Module 编译检查 |
| 本仓库 `esp_emu_bg.wasm` | 4,817,720 | 2,259,061 | 已有的芯片模拟内核，不是本项目 QEMU 板级补丁的 WASM 编译版 |
| 本机最终 Xtensa QEMU | 21,892,040 | 5,464,834 | 本机特定构建样本，非浏览器可加载文件；体积不含 ROM/固件/服务 |

本地 gzip 不是站点实际网络传输量；文件体积也不是运行内存或速度。
Core2 原生配置的 TCG translation cache 上限为 128 MiB
（`platform/tools/qemu_accel.py`），不能将 native 文件大小当进程 RSS。
本轮没有同固件 CPU、峰值内存、启动时延或 FPS 对照，不能报性能倍数。

完整下载的线上 WASM SHA256：
`8ef640bf8d525c5fec9d071bf12fba43765a5de549c1fcc8f4b4772d3a1fc72a`。
本仓库 WASM SHA256：
`59590fdb5a5ce4221cbc2c1ee1949bdfc97d51210a8f79c5d6647f918df15e5c`。

3D 模型和模拟内核是两类资源。新模型库仍逐模型懒加载，完整 vendor 目录大小
不能算成用户首屏必下载量，更不能据此认定必须后端仿真。
后续本仓库新版静态导出的桌面 Chromium 冷首屏实际读取62项资源、4,521,655字节
（未压缩、不含导航HTML）；WASM/固件/API请求均为零，执行资源在点击运行后加载。
此观测不代表GitHub Pages的压缩传输量或运行峰值内存。

## 本仓库的实际缺口与建议

本仓库当前 12 款 QEMU 配置是 `native-qemu`，Tab5 是 native esp-emu，
CardputerZero 是独立 Linux。现有浏览器 worker 的帧读取只识别
`m5emu-shared-v1`；其 GPIO/UART/内存 API 没有直接接入本项目原生 QEMU 的
SPI/I2C/GDMA、Unit/QOM 和板级屏幕模型。不能把旧 native 验收直接转授 WASM。

建议把浏览器运行时设为独立、可动态准入的 backend，而非强制所有公众用户
连接服务，也非一次替换已有 QEMU：

1. 优先以 PaperS3 / StopWatch 验证 `esp32sim` 的原始固件、冷启动、画面、
   输入、错误接线负控与资源占用。PaperS3 不能误当 PaperMono。
2. 对达到验收的组合提供 Pages URL 直开；未接入的设备明确展示模型与能力边界。
3. 保留 QEMU 路径承接已验证的 CoreS3/LVGL、原 UIFlow2 Unit 与网络/证据流程。
4. 若要求浏览器覆盖同等范围，逐一移植板级控制器和验证用例。C/QEMU patch
   不能直接贴进 Rust WASM；源码许可和依赖需单独审阅。

初始调查只覆盖源码、公开历史收据、线上二进制校验及静态编译；访问对方网页
时自动化通道失败，访问尝试没有算启动 PASS。后续使用本仓库自己的 Chromium
回归取得了下面的独立证据；这不回写为对方线上站点的运行结果。

## 本仓库后续实测：独立浏览器 backend

同日从上述固定源码、Cargo.lock 和 Rust 1.99.1 构建独立 WASM；两份干净
`git archive` 和独立 Cargo target 输出相同 SHA256：
`05f020796d2611865eb570f027bd6d905a5dc19b39f827421cfcae13524bbe45`。
该 hash 与线上下载版不同，后续结果只绑定此源码构建版。ROM 使用经来源、
许可和 SHA 校验的 Espressif S3 release `20260528`，构建与导出流程见
`platform/web/vendor/esp32sim/UPSTREAM.md`。

| 当前 Chromium 实验 | 已取得结果 | 仍有边界 |
| --- | --- | --- |
| PaperS3 官方出厂 v0.5 | ROM/应用串口、540×960 控制器原始帧、GT911 触摸改变图标、暂停和停止；无仿真 API 请求 | 官方应用内容在原始竖屏 buffer 内横向显示；保持真实像素/触摸方向；无 PaperS3 3D 模型；不授 UIFlow2/灰阶/联网通过 |
| StopWatch 官方 UserDemo v0.5 | ROM/应用启动、468×466 原始帧、A+B 菜单、触摸进入应用、暂停和停止；无仿真 API 请求 | 上游控制器输出宽468，面板模型宽466；未找到可信裁剪规则，完整原始画面单独显示，3D 纹理映射待验证；关闭 JIT 避开上游 IMU 路径卡住 |

复现入口是显式 opt-in 的 `platform/tests/test_public_browser_guest.mjs`。
本轮验证和固件/帧哈希集中在[公众入口证据](evidence/2026-10-28-public-simulator/README.md)。
这些是浏览器虚拟设备结果，没有物理硬件测量，也没有覆盖其他主机、完整 Unit
协议或任意固件。未访问用户的 8787，未部署站点。

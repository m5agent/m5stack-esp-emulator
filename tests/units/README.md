# 外接 Unit 数据面验证

归属 `UNIT-01`。官方产品/驱动依据在 `docs/unit-research/official-protocols.md`，
主机接线与模型状态在 `platform/units/`。

`run_service_cases.py` 仅使用 Device Service `/api/v1` 执行固件。它生成含官方
Unit 驱动 probe 的独立镜像，上传、创建可见 session，通过模型输入和串口/
QOM/画面检验双向数据面，停止前取证并以 `purge=0` 保留历史。

`probe/` 是 guest 代码：初始按键用官方 ButtonUnit 初始化并读取 GPIO；继电器
用 RelayUnit 输出；ENV III 用 ENVUnit 驱动 SHT30/QMP6988，压力从 API 的
hPa 显式换算为 Pa。probe 的原始串口观测不等于物理硬件结果。

Python/浏览器契约测试只覆盖编排和输入/输出桥；本目录每次运行的 JSON/ZIP
才是对应固件、主机、后端和 Unit 的运行证据。新增型号需同时加入实际 guest
driver probe、读写断言和失败边界，不能仅增加设备 ACK 或 UI 选项。

`run_web_cases.py` 在既有四组 runner 上启用可选的真实产品 Web 传输。每例仍
创建一个可见 session，正向输入改由实际 sessions 页的控件触发，保留同 guest
的串口/控制器断言。数值、字符串和 JSON 数组用 fill/Tab，布尔值用 checkbox，
多键用浏览器产生的可信 touch pointer；CardKB 双击锁定用一次鼠标双击手势，
保留官方 200 ms 时间窗。没有通过 page.evaluate 调 API 或替换产品函数。

```sh
M5_UNIT_EXPECT_RUNTIME_SHA256=<required-qemu-sha256> \
  python3.12 tests/units/run_web_cases.py --case cardkb --out-dir .work/unit-web
```

每款的 `report.json` 关联 controller result/ZIP、browser动作/实际HTTP响应、DOM
输出及既有模型按钮/灯状态、证据前截图和实时 PID/executable SHA。无输入的
输出型 Unit 也在最终 `/units` GET 和证据前核对页面真实读回。缺物理绑定的
字段仍只展示面板；浏览器传输通过不等于机械/光学/电气或实物硬件验证。

输入前同时等待页面与 UnitPanel 的 session 状态为 `running`、Unit 数据
`available=true`、实际目标 DOM 控件已启用。启动中的 QOM 可用不表示控件可操作，
桥不会为等待而刷新页面或修改产品状态。`M5_UNIT_REQUIRE_FLASHING_OPEN=1`
只用于单独验证从 flashing 打开页面的生命周期；普通功能测试保持 `0`。
本机 PID 证明在 Linux 严格解析 `/proc/<pid>/exe`，macOS 读取 `ps comm` 的
绝对文件路径；不接受短进程名或相对路径。未采到的 worker 字段仍为未知。

默认 Client 仍走 REST；显式 `M5_UNIT_WEB_BRIDGE=1` 才启用桥，API/schema 负向
测试可用 `via_ui=False` 保持直接 REST。`--exclude ir` 可明确排除需单独处理的
固件路径，不把排除项计入 PASS。桥自身不创建、复位或停止额外 session。

离线传输契约：`node platform/tests/test_unit_web_bridge.mjs`。这条命令仅用
真实 UnitPanel 对 fixture HTTP server 验证多键/数组/HUB，不执行固件。

只读批次汇总使用 `check_batch_evidence.py`，选择文件必须显式列出每款 Unit 的
guest/controller、真实浏览器与桥契约证据；`--strict-direct` 要求逐 session 的
实际进程 executable SHA。它检查跨层同会话/固件/ZIP、ZIP 全成员摘要、controller
真断言、非空浏览器附件及 PNG 哈希和完整解码，不从目录中自动挑最新 PASS。
显式 custom IR guest 还需在选择文件中绑定 `expected_firmware_flavor`。

CI 执行 `test_batch_evidence.py`、`test_sensor_evidence.py`、`test_web_ui_bridge.py`
的离线故障/进程溯源对照与
`test_unit_visual_mappings.mjs` 的纯映射契约。Python 图像解码需要 Pillow；这些
检查不启动固件，不能代替 Device Service 同 guest/Web 功能测试。

`run_annotation_cases.py` 通过专用的 `platform/tests/unit_annotation_bridge.mjs`
验证画布外的实时读数：ENV 两组模拟输入必须分别被原 guest 补偿算法读到，
Relay 两个输出态来自 guest GPIO。读数文本逐字段与实际产品 HTTP/QOM 对齐，
同时核对首次导航前五个相关资产的真实 HTTP body SHA、输入 POST 数量、
真实 stop 后清值，以及同 session 的 direct PID/ZIP。默认仅打印准备状态；
执行需显式 `--execute`、空闲的本地服务、准确 runtime SHA 和新的输出目录。
读数区不是 Unit 本体新增的物理屏幕，来源与机械部件映射不能互相继承。

该工具现在支持全部十二款现有标量 rail，保留无 `--case` 时只选择 ENV/Relay
的行为。`--case all` 明确选择十二款，重复 `--case` 可指定子集；默认仍只
打印计划，不访问 API。执行时沿用 service/sensor/io 原 guest 和原断言，
保存输入前串口 offset、新鲜驱动读数、阶段后真实产品 GET 原文/hash、DOM、
停止前 ZIP 和停止后原始历史响应。源码、依赖清单及打包工具链发生变化即
判为失败，不继承旧批次结果。

```sh
python3.12 tests/units/run_annotation_cases.py --case all
python3.12 tests/units/run_annotation_cases.py --case ultrasonic-i2c --case light \
  --execute --expected-runtime-sha256 <required-qemu-sha256> \
  --out-dir .work/unit-readout-selected
```

距离和温度等 guest 结果按原驱动单位及量化容差核对，rail 则与真实控制器
数值严格相同。Heart 只检查原始 IR/red 样本，Thermal 只显示控制字和原始
fixture readiness，均不升级为心率、血氧或温度图。Buzzer 的短阶段采用
`state` 模式记录真实 HTTP/DOM 状态；最后稳态用 `full` 模式核手势零修改和
截图，不伪称每个短阶段都有图片或原子 LCD/DOM 快照。

Light 的初始 digital-level=false checkbox 是合法 no-op，因此三输入向量
实际只发五个 POST；首 POST 之前必须有同 session / external1 的真实
running/live/available guest-QOM GET，严格证明该字段为 false。缺失时间、
非法/无时区时间、其他实例、晚到 GET 或整数 0 均不能满足该初始状态检查。

Buzzer 原发布 Haptic/SoftTimer callback 参数冲突已在实际固件中复现。
`--buzzer-callback-arity-patch` 仅允许与 `--case buzzer` 单独使用，显式
生成 custom wrapper；默认仍使用原驱动，不能静默修补上传固件。原 IO
断言也已收紧为 TIMER_DONE/手动输出前的自然归零，避免后续 turn_off 造成
假阳性。适配范围和执行方法见
[`patches/uiflow2-unit-buzzer/README.md`](../../patches/uiflow2-unit-buzzer/README.md)。

AtomS3R、StickS3、StopWatch 的五款 I2C 控制类使用
`prepare_host_controls.py` 和 `run_host_control_cases.py`。前者按实际参考镜像
分区表准备独立固件，并冻结当前探针、原驱动、工具链和执行依赖；后者默认
只检查准备产物，不访问服务。两者均不依赖历史 `.work` 批次或旧 profile SHA。
显示探针保留已验证的分行布局，并在 guest 内检查实际字体和屏幕边界；离线
准备不等于固件运行或最终帧可读性通过。

```sh
python3.12 tests/units/prepare_host_controls.py --device all --case all \
  --out-dir .work/host-controls-prepared
python3.12 tests/units/run_host_control_cases.py \
  --prepared-dir .work/host-controls-prepared
python3.12 tests/units/run_host_control_cases.py \
  --prepared-dir .work/host-controls-prepared --device atoms3r --case encoder \
  --execute --expected-runtime-sha256 <required-qemu-sha256> \
  --out-dir .work/host-controls-execution
```

准备和执行输出目录必须是新目录。源码、工具链、配置或准备文件变化后需要
重新准备，不允许放宽摘要检查来复用旧镜像。显式执行仍通过可见 Device
Service session、真实浏览器输入和原 CONTROL 断言，停止前获取 ZIP，再以
`purge=0` 保留实际停止历史及最后帧。新的执行结果独立记录，不继承旧批次
PASS，也不扩展主机准入或物理硬件结论。
此入口需要 Python 3.12、Pillow、littlefs-python 和矩阵中指定的参考固件；
实际执行还需要已配置的 QEMU/ROM、Device Service 与浏览器测试依赖。

三主机的 Color、ToF、NCIR、Heart、TVOC、Ultrasonic-I2C 使用对应的
`prepare_host_sensors.py`、`run_host_sensor_cases.py` 和 `host_sensors_probe/`。
准备入口保留原官方驱动、初始化、负控与采样链，增加真实内/外 I2C、内部
BMI 和字体边界观测；离线镜像、源、工具链、配置和完整 VFS 必须一致。
执行适配使用独立 sensor 模块，保留原准备前 probe hash，另外明确绑定
恢复后的配置和实际打包字节，不覆盖原记录。

```sh
python3.12 tests/units/prepare_host_sensors.py --device all --case all \
  --out-dir .work/host-sensors-prepared
python3.12 tests/units/run_host_sensor_cases.py \
  --prepared-dir .work/host-sensors-prepared
python3.12 tests/units/run_host_sensor_cases.py \
  --prepared-dir .work/host-sensors-prepared --device all --case all \
  --execute --expected-runtime-sha256 <required-qemu-sha256> \
  --out-dir .work/host-sensors-execution
```

默认预检零 API，显式 `--execute` 必须在任何 API/bridge 操作前拒绝当前
registry 未准入的组合；此入口不修改 runtime profile。初始 18 份离线候选
的 BLOCKED 记录保留，后续显式开发接线与实际验证状态分开：ADMITTED/
NOT RUN 只代表允许测试，不能凭离线包或字体 guard 代码授予 guest/Web/
可读性 PASS。当前结果以 `docs/project-status.md` 为准。

实际正向输入逐字段绑定产品 POST、响应、时间区间与原始串口 prefix/window/full
SHA；两组观测必须在各自真实 Web 操作后的新鲜窗口内。原初始化/负控及官方
driver 断言继续执行。`test_host_sensor_execution.py` 覆盖错序、漏项、旧串口、
非有限值与单位错配。`platform/tests/_unit_host_sensor_evidence.py` 在归档后
独立复核 SENSOR/Web 契约、来源重建、完整 VFS、adapter、同会话三路帧和历史。
三次取图是不同请求，Heart 的零值暂态可能产生不同帧；每路分别绑定摘要，
不以字节相同推导原子采集。人工可读性只适用于已绑定的捕获帧。
已归档结果见[三主机传感器证据](../../docs/evidence/2026-10-26-unit-host-sensors-gen9-a8fe/README.md)。
更改主机验证元数据也会改变准备源，下一次执行必须生成新的准备目录。

三主机的 GPIO/ADC/LEDC/RMT/UART 与被动 HUB 使用
[`prepare_host_io.py`](prepare_host_io.py)、[`run_host_io_cases.py`](run_host_io_cases.py)
和 [`host_io_probe/`](host_io_probe/)。入口覆盖原 `run_io_cases.py` 的十二款：
PIR、Dual Button、Limit、Key、RGB、Angle、Light、Buzzer、Fan、IR、RS485、HUB。
Thermal 属于独立 sensor runner、原始帧 fixture 和热图路径，不在这十二款 IO
清单中，不能通过 IO 入口继承结果。

准备器按实际 reference 分区打包，核对完整 VFS 成员/字节及 VFS 外不变，
保留官方 driver、初始化、负控、输出/输入分支和原时序。guest 只增加主机
显示布局与内部 BMI270 的 before/after_init/loop 观测。执行器在私有原 runner
模块中只适配 `prepare()`，不替换 `validate_io` 或删减原断言。

此入口要求 Python 3.12 与匹配的 littlefs-python native ABI。本机现有扩展
目录为 `.work/py312`；默认 Python 3.9 或 `.work/py` 的 CPython 3.13 扩展
不能与它混用。其他环境也须匹配解释器、扩展架构和依赖；准备/预检会冻结并
复核实际解释器、native extension 与包装器的 SHA，不凭版本名视为相同工具链。

```sh
PYTHONPATH=.work/py312 python3.12 tests/units/prepare_host_io.py \
  --device all --case all --out-dir .work/host-io-prepared
PYTHONPATH=.work/py312 python3.12 tests/units/run_host_io_cases.py \
  --prepared-dir .work/host-io-prepared
PYTHONPATH=.work/py312 python3.12 tests/units/run_host_io_cases.py \
  --prepared-dir .work/host-io-prepared --device atoms3r --case pir \
  --execute --expected-runtime-sha256 <required-qemu-sha256> \
  --out-dir .work/host-io-execution
```

prepare 和默认 preflight 均不访问 API；只有显式 `--execute` 才执行固件。
当前可执行组合与 ADC 阻塞清单见[本次离线准备报告](../../.work/unit-host-io-candidate-20261026/final-preparation-report-r1.json)
和[默认预检原始输出](../../.work/unit-host-io-candidate-20261026/preflight-admitted-r1.json)，
本页不维护动态数量。ADMITTED_NOT_EXECUTED 只表示允许测试。ADC 的实际 app
字节必须匹配校准 fixture，StopWatch white11 还涉及原 ADC1 oracle 与 ADC2
通道不一致；当前执行门禁会拒绝这些组合，不删除 `read_uv` 断言，也不因此
把 Light 的 raw/digital 数据面判为不支持。

源码、来源清单、Web 资产、补丁、工具链、配置或准备文件变化后，都须用新目录
重新 prepare。每次执行前要求 exact current sources 和完整准备产物一致，
执行中继续检查来源与工具链；不通过摘要 allowlist 复用旧包。`--execute`
在任何 API/bridge 操作前拒绝未准入或存在具体 blocker 的组合。

默认 IR/Buzzer 保留原发布 driver：IR callback 的 GC 生命周期与原包装载荷、
Buzzer timer callback 参数及自然归零属于已知风险，不能继承其他主机的 FAIL
或用后续手动关闭冒充自然归零。显式 custom 只在准备时指定
`--case ir --ir-callback-root-patch` 或
`--case buzzer --buzzer-callback-arity-patch`，并使用独立的新目录、固件 SHA 和
`firmware_flavor`；执行器沿用该准备记录，不静默修改 vendor、native 或 QEMU。

多代理协作时由 root 统一独占当前 Device Service API 和 session 生命周期；
其他代理只处理离线准备或已有工件，不自行发 API、启动 session 或直接 QEMU。
实际执行保留同 guest 原断言、真实产品 Web 动作/HTTP、direct PID/executable
SHA、worker generation、运行态 ZIP 与停止历史：先请求 ZIP，再 `purge=0`
停止并默认释放 Flash。正向输入逐字段核对真实 POST 或显式 already-equal
no-op，以及操作前串口 prefix/offset 和新鲜窗口；no-op 不冒充注入 POST，
RGB/Fan/Buzzer 输出专用 case 必须保持零输入 POST。三路 native frame 分次
捕获并分别绑定摘要，人工可读性另审，不声称原子同帧或物理硬件 PASS。

`test_host_io_preparation.py` 与 `test_host_io_execution.py` 覆盖上述离线门禁、
原流程保留和输入绑定。`platform/tests/test_unit_ledc_readback_patch.py` 随平台
unittest 在 CI 中长期检查 0037 的 S3 地址范围/掩码及 classic 隔离；其中的 C
片段测试不执行 QEMU 或固件，不能授予 IO 功能 PASS。

## 同 guest 文件包探针

`run_live_package.py` 默认只输出plan；`--execute`须显式指定`--mpy-cross`、精确
`--expected-runtime-sha256`及全新`--out-dir`。支持四款准入主机的PIR/Relay，
通过8787可见session验证相同入口配不同`.mpy`、Python/namespace模块、JSON和PNG。
覆盖A/B替换、SyntaxError恢复、stale身份、字节码不兼容、额外空目录及文件篡改拒绝、
新C恢复；ZIP逐字节核验后才停止，保留历史并释放Flash。图片读bytes显示并放在
圆屏有效区域；该scaffold不修改原驱动或替代Unit控制器。

```sh
PYTHONPATH=platform/tools:tests/units:.work/py312 python3.12 tests/units/run_live_package.py \
  --execute --device cores3 --unit pir --mpy-cross /path/to/official/mpy-cross \
  --expected-runtime-sha256 <required-qemu-sha256> --out-dir /tmp/m5-live-package
```

限纯字节码依赖，不支持native emitter、二进制入口或保存为boot。
实际范围与失败记录见[文件包证据](../../docs/evidence/2026-10-26-live-package-and-detent/README.md)。

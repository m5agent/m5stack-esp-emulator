# UI 对账、执行与候选修复

`inventory_ui.source.json` 是文档与实际导出的对账分母，不是功能通过表。
`ui_native_bindings.py` 同时解析实例 `VAR` 与静态 `STATIC_VAR` 绑定，保留
C owner、真实预处理声明、binding arity、static/instance 与类型继承关系：

```sh
python3 tests/uiflow2/api_sweep/ui_native_bindings.py \
  --uiflow-root /path/to/pinned-uiflow \
  --output .work/api-sweep/lvgl-native-bindings.json \
  --split-dir .work/api-sweep
```

`lvgl-core-own-methods.json` 包含结构体、容器、display/indev 与模块函数；
`lvgl-objects-own-methods.json` 包含 obj 与其 widget 子类。两者都是 recipe
索引；反射、owner 相同或继承关系不产生功能 PASS。复用结果必须指出同一个
实现、签名、实际调用、参数域、资源生命周期与来源，不能把未执行的回调、
图像类型或另一设备继承为通过。

## 可见会话

先通过 Device Service 建立正确设备、固件、`program_transport=uart-repl`
的 running 会话，再在同一个 VM 中执行：

```sh
PYTHONPATH=platform/tools:.work/py python3.12 \
  tests/uiflow2/api_sweep/run_ui_live.py \
  --api http://127.0.0.1:8788 \
  --device cores3 --session-id SESSION_ID --lane native-objects \
  --token-file /path/to/service-token --out-dir .work/api-sweep/object-run
```

示例使用独立的本机 Device Service；按实际服务地址显式传入必填 `--api`，
token 只从已有文件读取。`--lane` 支持 `display`、`canvas`、`widgets`、
`widgets-module`、`m5ui`、`native-styles`、`native-objects`、
`native-objects-more`、`native-widgets`、`native-widgets-more`、`lifecycle`
和 `corrections`。`--method` 可收窄至单项；Widgets/M5UI
另指定 `--target`。默认在取 evidence ZIP 后 `purge=0` 停止；明确需要继续同
VM 时才传 `--keep-session`，最后一批仍须取 ZIP、停止、核对 PID/Flash/历史。

`STATE_PASS` 只表示列出的 native state/callback/layout oracle 成立；
`FRAME_PASS` 是指定颜色、位置、区域或实际 QR 解码通过。OCR 的 `GLYPH_PASS`
只验证字形内容，不替代颜色、对齐或大小变化。`GROUP_ERROR` 后未到达的调用
仍为 NOT_RUN。空画面以外的任意非空图不能代替图像或交互 oracle。

有限、冷启动的原生 recipe 使用 `run_guest.py`，不需要先建立 warm 会话。
例如逐项测试 object namespace，避免一个 foreign-class setup 错误跳过其余
方法：

```sh
PYTHONPATH=.work/py python3.12 tests/uiflow2/api_sweep/run_guest.py \
  --api http://127.0.0.1:8788 --token-file /path/to/service-token \
  --device cores3 \
  --source tests/uiflow2/api_sweep/probe_lvgl_obj_namespace_stock.py \
  --done-marker LVGL_OBJ_NAMESPACE_STOCK_DONE \
  --out-dir .work/api-sweep/obj-stock-new
```

该 runner 通过 Device Service 上传/组合固件、创建可见会话，保存 source /
firmware / runtime / frame / ZIP hash，再停止并核对历史与进程。每次使用新的
ignored 输出目录。headless LVGL 的 canvas 内存像素 oracle 是原生绘图证据，
不等于板载显示屏或物理硬件验证。

`CALL_OK` 只表示调用返回；`UNSUPPORTED_BINDING` 必须有实际调用和合法 typed
资源的拒绝证据，不能由普通 fixture 初始化错误推断。`BLOCKED_BUILD_CONFIG`
保留已调用但未启用的构建功能，`BLOCKED_MODEL` 保留缺失的数据面。矩阵输入
调用后仍返回 NULL、dump-tree 无可观察日志等情况，不应改记功能 PASS。

`run_ui_live.py --lane m5ui --target CLASS` 不传 `--method` 时仅构造控件；
空 `results` 不能算该类方法已执行。文档方法全集的独立入口为：

```sh
PYTHONPATH=platform/tools:.work/py312 python3.12 \
  tests/uiflow2/api_sweep/run_m5ui_documented.py \
  --api http://127.0.0.1:8788 --token-file /path/to/service-token \
  --firmware-id ADMITTED_CORES3_UART_FIRMWARE_SHA256 \
  --expected-runtime-sha256 PINNED_QEMU_SHA256 \
  --uiflow-root /path/to/pinned-uiflow --out-dir .work/api-sweep/m5ui-new
```

这个入口要求已准入的 CoreS3 UIFlow UART composition；其 bootstrap 必须发出
`M5EMU_UART_REPL_READY`，避免在 MicroPython 启动完成前发送 raw-REPL 指令。
它只创建自己拥有的新会话，按 inventory 的 `documented_surfaces` 为每个组件
生成包含全部文档方法的独立程序，每个方法重建原始控件状态；最后另测
`m5ui.init/deinit`。它不把 native 继承清单并入分母。返回子 label/button 的
文档示例误归属、未导出的 wrapper 方法按 `DOCUMENTATION_MISMATCH` 保留，
并记录实际 member/type 观察。`STATE_PASS` 只验证指定参数域的 getter/state；
`PENDING_FRAME_OR_INPUT` 仍需要独立画面或输入 oracle。最终 ZIP、runtime
身份、停止、Flash 释放和历史收据通过后，报告仍为 `EXECUTED_WITH_BOUNDARIES`，
不把方法调用或构造成功汇总为全功能 PASS。

## M5UI 源码候选

`0001-m5ui-native-marshalling.patch` 修正三处独立源码问题：三角形 descriptor
数组 getter 返回副本、单参数浮点图像缩放缺整数转换、整数 Spinbox step
错误乘十。准备器校验固定 commit、全部 pre/post SHA 与 patch 正反应用；
输出保留 `candidate_m5ui` 包及原 `M5Base`，不改变参考固件或冻结模块。

```sh
python3 tests/uiflow2/api_sweep/prepare_m5ui_candidate.py \
  --uiflow-root /path/to/pinned-uiflow --out-dir .work/api-sweep/m5ui-candidate
```

在两个独立输出目录运行 `--lane corrections`：默认不加候选目录，候选运行加
`--candidate-dir .work/api-sweep/m5ui-candidate`。若要求同 VM 对照，第一批明确
加 `--keep-session`，第二批继续使用相同 session，并在最后取 ZIP 和停止；
两个冷启动会话不能标为同 VM。候选结果绝不覆盖默认固件失败。

Label+ 的独立 Python 源码修正由 `prepare_plus_candidate.py` 准备，
`run_plus.py --candidate-dir` 显式上传 `candidate_label_plus.py`；不传候选目录
才是原冻结库 lane。实际 HTTP 返回值和定时器引发的新增请求均需核对。
requests2、TLS、USB 的范围和复现分别见[补丁目录](../../../patches/uiflow2-api/README.md)、
[protocol 说明](README-protocols.md)和[硬件 / USB 说明](README-hardware.md)。

## 原生 GFX C 候选

`0003-display-raw-buffer-length.patch` 按官方文档的字节长度转换为 RGB565 像素数，
并在 `startWrite` 前拒绝负数、奇数、超出 buffer 或 window 的长度。历史规避
调用传入 `len(raw)//2`；修正固件按文档传 `len(raw)`。候选固件不自动替换参考
固件，不能把规避调用当成 SDK 已修复。

`0004-display-path-length-unbox.patch` 将 MicroPython `mp_obj_len` 的 tagged
small-int 解包后再进行原有的 128 字符判定；范围为原来被误判的 64–127 字符
路径，不声称取消原判定或验证任意长度路径。

```sh
python3 tests/uiflow2/api_sweep/build_rawbuf_candidate.py \
  --build-root /path/to/complete-cores3-build \
  --base-image /path/to/that-build-full-flash.bin \
  --extra-manifest patches/uiflow2-api/0004-display-path-length-unbox.json \
  --out-dir .work/api-sweep/gfx-candidate-build
```

该增量入口只读原 checkout、object、static library、ELF 与 image。新目录内
编译一个被固定 SHA 的 translation unit、替换独立库的对应成员并 relink；
校验 base 的 app 与既有 build 相同，只有 app 分区改变。receipt 明确标注
incremental/cold_build=false；不能宣称独立冷构建。用 `run_guest.py` 的
`--base-image` 与 `--expected-base-sha256` 分别执行 matching preimage 与候选，
不修改设备目录默认 reference。

`probe_rawbuf_correction.py` 覆盖大端、swap、小于 window 的字节数及候选的
bounds 负控。`probe_display_resources.py` 需要在 host 前置
`DISPLAY_FIXTURES=repr(probe_ui.fixture_files())`，在 guest 写入短/长绝对路径，
并分别验证 PNG/BMP/JPEG/自动识别的短文件、64–127 字符文件和 bytes 三个域。
图片由 guest decoder 经 SPI/GDMA/panel 输出；host 只检查最终指定像素。

`0014-widgets-qrcode-text.patch` 也使用 `build_rawbuf_candidate.py`，通过
`--manifest` 选择其 JSON，不能混用 GFX translation unit 的 source hash。
双板需各自匹配的 cached build / base；Cardputer-ADV 另显式指定
`--cached-build` 和其 8 MiB 容量 `--flash-size 0x800000`。

`0019-widgets-qrcode-geometry.patch` 在 `setCursor` / `setSize` 改变几何前
擦除旧区域，同文件叠加顺序为 `0014 → 0019`。用
`probe_widgets_qrcode_geometry.py` 分别运行 stock、与构建匹配的 SDK 原版和
候选，再用 `analyze_widgets_qrcode_geometry.py --stock DIR --preimage DIR
--candidate DIR --build-receipt RECEIPT --out SUMMARY` 验证同源输入、固件 /
runtime / ZIP 身份和停止收据。三个 QR 解码与两个旧独占区域检查分别保留，
新位置能解码不能覆盖旧图块残留失败。匹配的 HCI transport SDK cache 是
另一构建身份，不能冒充历史 SDK 镜像；它必须绑定自己的 app 和 full-flash。

`analyze_widgets_frames.py --root WARM_BATCH --out SUMMARY` 为已执行的 Widgets
调用补充独立画面 oracle：Label 同字形缩放、Title 整数高度和光标平移、
QRCode 原区域隐藏。它不修改原状态结果；缺失的原厂/候选参数域仍独立保留。
`probe_widgets_qrcode_text.py` 以调用前后独立解码的 QR 文本
验证 `setText`，不能以画面变化替代解码。

## 原生 LVGL 候选及资源生命周期

`build_lvgl_candidate.py` 默认包含 `0005` 和 `0006`，并通过重复的
`--extra-manifest` 添加明确的补丁。以 allocator 修正为例：

```sh
python3.12 tests/uiflow2/api_sweep/build_lvgl_candidate.py \
  --build-root /path/to/complete-cores3-build \
  --base-image /path/to/that-build-full-flash.bin \
  --extra-manifest patches/uiflow2-api/0018-lvgl-cache-entry-allocation.json \
  --out-dir .work/api-sweep/lvgl-cache-candidate-new
```

需要叠加 generator 修正时，顺序为 `0006 → 0008 → 0009 → 0012 → 0013 → 0015`，
其中 `0006` 已默认添加，不要重复传入。独立补丁和叠加后的 postimage hash
不同，必须分别核对 JSON 的 `candidate_sha256` 与 `stack_candidate_sha256`。
`0016`、`0017`、`0018` 修改不同的原生 C 文件，仍须逐个指定，不能由目录中
存在补丁推断它已经进入固件。完整文件名、修复行为和各 lane 的边界见
[0001–0018 索引](../../../patches/uiflow2-api/README.md)。

构建器只在新目录中准备候选源、生成绑定、编译所有被修改的 LVGL C 单元和
binding、替换独立 archive / direct-link object 并 relink。receipt 必须证明
原源树、archive、binding 与 app 分区外内容未变。使用 matching SDK 原镜像
和该 receipt 中的候选镜像分别执行同一个 probe；原厂 frozen 镜像另记一条
lane。`run_guest.py` 的 alternate base 必须同时提供 `--base-image` 和精确的
`--expected-base-sha256`，不能更换 device-matrix 默认 reference。

这些 recipe 验证不同资源域，不能互相替代：

- `probe_lvgl_corrections.py`：完整 Roller 选项、object/display/indev 的实际
  回调和 user-data 身份。
- `probe_lvgl_subclasses.py`、`probe_lvgl_menu_helpers.py`、
  `probe_lvgl_unsigned_words.py`：真实内部子类、foreign typed namespace 参数、
  unsigned 高位参数；每个别名都需要调用记录。
- `probe_lvgl_object_user_data.py`、`probe_lvgl_lifecycle.py`：原 wrapper 对象
  身份、删除失效和 custom animation 的实际查找 / 删除。
- `probe_lvgl_observer_cleanup.py`：精确 object-delete 订阅成员、保留的其它
  subject 通知及自动删除。旧版必须先记录失败，repair 只允许用于安全清理。
- `probe_lvgl_cache_entry_alloc.py`：先验证未被修补的 allocator 返回 metadata，
  再测独立 payload、指针、引用和删除；不能先手动 `init` 再授予 alloc PASS。
  `analyze_lvgl_cache_entry_alloc.py` 将同源 SDK 原版 / 候选与构建 receipt、
  固件、运行时、ZIP 和清理状态绑定。

object namespace 中普通对象方法、class 首参数方法和 layer 首参数方法需要
分别构造 typed 资源。`probe_lvgl_obj_namespace_stock.py` 每项独立执行，保留
NULL 参数拒绝、构建功能未启用和仅调用成功等较窄结论；原厂结果不从候选
固件继承。getter 返回的原生 transform 指针必须在 reset/delete 释放前复制，
destruct 的 local-style 清理用 typed `get_local_style_prop` 判断；
`has_style_prop(WIDTH)` 仍可能找到 class 默认宽度。

## 逐项结果

```sh
python3 tests/uiflow2/api_sweep/summarize_ui_results.py \
  --run-dir .work/api-sweep/cores3-ui-run \
  --runtime-log cardputer-adv=.work/api-sweep/cardputer-ui-export/serial.txt \
  --output .work/api-sweep/ui-per-api-results.json
```

该详细表较大，保留在 ignored 存储。相同 execution 中一个参数域成功不能
抹掉另一个域失败，source override 或 alternate firmware 进入独立 candidate
观察，常量只记 INVENTORY_ONLY。`UNAVAILABLE_ON_DEVICE` 需要该固件的实际
import 失败；普通未编写 fixture 保留 NOT_RUN。硬件结果始终独立记录。

原生 own-method / module 对账另使用 `join_ui_native_results.py`，显式列出经过
审查的执行根目录，不扫描混有废弃 fixture 的整个历史缓存。例如：

```sh
python3.12 tests/uiflow2/api_sweep/join_ui_native_results.py \
  --declarations .work/api-sweep/lvgl-core-own-methods.json \
  --declarations .work/api-sweep/lvgl-objects-own-methods.json \
  --run-dir .work/api-sweep/obj-stock-new \
  --run-dir .work/api-sweep/other-reviewed-run \
  --output .work/api-sweep/ui-native-selected.json
```

最终分母、所选 roots 与各状态以该次生成结果为准。join 按执行记录区分
reference、已登记 base hash 的 matching SDK 原版、candidate firmware 和
candidate source override；未登记的 alternate image 不能仅凭名称当作
matching preimage。它保留同一方法不同参数域的全部状态，明确列出未执行项。
排除已纠正的 fixture 时应保留原始记录和纠正理由。即使所选方法全部有实际
观察，也不能据此宣称所有接口、参数域、别名、设备或物理硬件全部通过。

# 浏览器 UIFlow 编程工作台：CoreS3 限定验收

日期：`2026-11-04`。本块整体为 **PARTIAL**：新的精确 CoreS3 工作台镜像已完成浏览器代码执行验收；其余 18 款公开板型的新默认 guest、完整按键、逐板提速和实际上线仍未完成。当前执行队列继续以 [Backlog](../../project-backlog.md) 为准。

所有固件执行结果均为 **virtual-device validation**，来自静态站中的同一浏览器 QEMU、原始 UIFlow2 VM 和 UART0。无 Device Service 会话，也不授予物理时序、RF、电气或真机结果。四档布局检查与文件组合另列，不能代替 guest 执行。

## 三轮执行及保留的首次失败

三轮都使用 CoreS3 的同一工作台 Flash：
`52f38f562f6e3749357a2ed4834efd72d16870046ea052f2f31691743cb5384d`。
其官方 UIFlow2 基底为 `1324f12d…d2c1264`，仅用明确的网页编程 boot/main 覆盖既有 VFS 文件。运行时仍是原 UIFlow2；默认启动脚本执行 `M5.begin()` 后返回真实 REPL，不是原厂联网菜单。

| 轮次 | 结果 | 执行身份与限定范围 |
| --- | --- | --- |
| 首次 signed-array 路径 | **FAIL**，7 项中 6 项通过 | WASM `3c6b2490…df4567`；应用 ready 后，实际 UART 输入已使 guest 进入 raw REPL，但编辑器等待握手超时，未确认整段源码执行。不能写成 UIFlow 固件失败。 |
| unsigned-array 修复后 smoke | **PASS**，20 项 | 同一 `3c6b2490…df4567` 和 Flash；真实网页默认固件、UTF-8 中文输出、多行求和、同 VM 再执行及正常停止通过。未执行完整异常、导入、暂停或硬 reset 验收。 |
| fresh 74-patch 完整编辑器 | **PASS**，54 项 | WASM `2c72cda0…8de5d14`；10 次实际 raw-paste 执行，含长 UTF-8 源码、预期异常、文件导入、暂停/继续、中断、真实红帧及硬 reset 后新 console 执行。 |

首次失败的具体缺陷是 Emscripten `FS.write` 给出 `Int8Array`，engine 原先保留了这一类型，而 runtime 的二进制订阅只接受 `Uint8Array`。文本串口仍能显示 raw prompt，二进制握手却被遗漏。显式拷贝为 `Uint8Array` 后，同 Flash、同旧 WASM 的后续 smoke 通过；实际 Int8Array 控制字节另由 host contract 保留。该后续 PASS 不抹去首次 FAIL。

首次失败保留了六个 CDP Worker 在关闭 context 前全部消失的观察，但未保留停止后的正常 exit 收据；不从后续成功轮次继承它。两轮 PASS 分别具备正常 exit0、零强制兜底、iframe 保留时 pthread 消失，以及移除 iframe 后全部六个 Worker 消失的证据。

## 新运行时的完整编辑器范围

完整轮次把执行 web/test 源码逐项核对到项目提交 `dd9ae2a08bec4263a22b0e49c0507f9ae22ec4a3`。静态导出 manifest 为 `b28b9f89…462dae4`；同轮固件、WASM、profile、源码、测试脚本和导出内容的完整 SHA 均在 [summary.json](summary.json)。历史两轮只保留当时的完整内容哈希，不补写未记录的项目提交。

实际通过的行为包括：

- 中文 UTF-8 打印、多行循环，以及约 4.5 KiB UTF-8 字面量源码的 raw-paste 信用流控；
- guest 返回预期 `SyntaxError`、`RuntimeError` 后，导入 `.py` 并继续执行；
- 无限循环产生实际输出，暂停后保留 UART owner，继续后通过真实 Ctrl-C 返回 `KeyboardInterrupt`，再执行新程序；
- `M5.Lcd.fillScreen(0xFF0000)` 产生 320×240 实际 RGB565 红帧；
- 运行中硬 reset：旧执行以 `AbortError` 终止，console epoch 从 `0` 变为 `1`，同浏览器会话的新 boot 到达新 ready 后再次执行；
- 请求正常停止后，实际 CDP Worker 全部关闭，且没有 Device Service 请求或页面异常。

首次 ready 观测为 `27.483 s`，使用保守的 `cores3-wasm-vm-div8`、clock divisor `8`。这是一次启动观测，不是提速结论；原固定示例的正常时钟结果不能转授给新的工作台 SHA。

同一新工作台 Flash 后续以独立 exact-SHA 正常钟候选完成 54/54，单次 ready 为 `10.971 s`，见[正常钟后续证据](../2026-11-04-browser-uiflow-workbench-wallclock/README.md)。该记录另存源码变换与导出身份，不改写本页 div8 基线或首次 FAIL，也不转授其余 18 板。

## 文件组合与布局是独立证据层

19 款公开板型都已用 source-built LittleFS WASM 组合明确的官方 UIFlow2 基底与编程启动脚本。逐文件重新读取、独立 LittleFS 再挂载、原文件/目录保留、VFS 外字节与完整 Flash SHA 核验通过；19 组身份均列在摘要。Atom Matrix 两个改版可共享相同 Flash 字节，其板型 profile 仍分别绑定。

这批组合报告没有记录当时 Node wrapper/test 文件本身的 SHA。摘要明确保留该缺口，并把当前提交的复现工具哈希单独列出，不追认成原始同轮身份。组合和读回只证明包装结果，不能据此授予另外 18 款板的 guest、按键或性能 PASS。

纯 model-only 静态导出另在 `1440 / 1024 / 768 / 390 px` 做了截图、视觉复核、页面横向溢出、编辑器边界及键盘焦点检查，均通过。Tab/Shift+Tab 可离开编辑器，导入动作有可见焦点；未启动固件 Worker，Run/Interrupt 保持禁用。该层没有执行任何固件。

## 复现入口与原始证据

使用 Python 3.12+，从当前锁进行 fresh QEMU 源码构建，并构建 LittleFS；保留所有源码包、许可和构建 manifest：

```sh
python3 platform/tools/bootstrap_qemu_browser_runtime.py \
  --cache .work/uiflow-build --output .work/uiflow-runtime --jobs 4
python3 scripts/browser-littlefs/build.py \
  --emcc .work/uiflow-build/emsdk/upstream/emscripten/emcc
python3 platform/tools/build_public_site.py \
  --output .work/uiflow-site --base-path /showcase/ \
  --qemu-runtime .work/uiflow-runtime --littlefs-runtime .work/browser-littlefs
npm ci --prefix platform/tests
M5_PUBLIC_SITE="$PWD/.work/uiflow-site" \
M5_WASM_NODE_MODULES="$PWD/platform/tests/node_modules" \
M5_WASM_CHROME="<system-Chrome-executable>" M5_QEMU_DEVICE=cores3 \
node platform/tests/test_public_uiflow_guest.mjs
```

完整测试要求系统 Chrome 的硬件 ANGLE/Metal 路径，自动选择随机静态服务端口并验证导出的 Service Worker。新机器构建会产生自己的运行时哈希，必须保存本次身份；不能声称复现了上述旧二进制。默认全测，不设置 `M5_UIFLOW_SMOKE_ONLY`。原始报告为约 3.7–5.2 MB，源码 Git 只收录其大小、SHA 和有界结论，保留真实帧/串口/输入及 CDP 原文于外置原始证据。

文件组合工具见 [README](../../../tests/browser-qemu/uiflow_workbench/README.md)，按钮测试另由 [按键入口](../../../tests/browser-qemu/uiflow_workbench/README.buttons.md)执行。当前块不关闭全设备按键、逐板速度或 Pages 发布任务。

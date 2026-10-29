# 现有 C/QEMU 到 WASM 的构建实验

核查日期：2026-10-28。按用户澄清，Rust 项目仅作参考；本实验复用当前定制
C/QEMU，不把另一套内核的两款演示作为已有板级/Unit 能力的替代交付。

本页保留 2026-10-28 的阶段实验范围与当时失败。后续公众入口及正式
Pages 已有[独立部署证据](evidence/2026-10-29-github-pages-production/README.md)；
共享帧、host poll、正常时钟候选和逐板准入见
[2026-10-29 证据](evidence/2026-10-29-wasm-performance-devices/README.md)。
本页的旧补丁数量、NOT RUN 和后续计划不反向定义当前状态。

## 当前结论

C 可以编译成 WASM。现有 QEMU 的编译和链接已经实际打通，并在 Chromium
中运行了完整生成物的版本、板型枚举和无固件 QMP 请求。此前直接判断移植
工作量太大并停止，依据不足。

真正需要适配的是 QEMU 使用的宿主环境：原生代码生成、GLib 回调 ABI、
libffi、pthread/协程、文件描述符、事件唤醒、内存和生命周期。浏览器不能
直接执行原生 TCG 生成的机器码；本轮采用官方已有 TCI 解释后端，将 Xtensa
译成 TCG 中间操作，再通过 WASM 中的 TCI 执行。CoreS3 固定 guest 已完成限定功能与停止重开，
详见[阶段证据](evidence/2026-10-28-qemu-wasm-cores3/README.md)；不能给出相对原生或 Rust 的速度倍数。

## 已执行的证据

| 层级 | 结果 | 实际范围 |
| --- | --- | --- |
| 当前源码复用 | PASS | 固定 Espressif QEMU 9.2.2 和完整 30 层板级/Unit 补丁；112 个相关文件中 111 个逐字节不变，仅共同的 `meson.build` 增加宿主构建适配 |
| C 依赖/链接 | PASS | Emscripten 3.1.50；真实 GLib、libffi、pixman、zlib、libgcrypt 和 libgpg-error；生成完整 `qemu-system-xtensa.js/.wasm/.worker.js` |
| helper/crypto | PASS | 指针/i32/i64 libffi 往返；真实线程锁、SHA256/AES 已知答案、MPI、RSA 签名/验签和改摘要拒绝；不是 QEMU guest 结果 |
| 浏览器 pthread | PASS | 无隔离响应头的本地静态服务，固定 SW 重载后取得 COI/SAB；真实两个 C pthread、mutex、100000 次调用及 join/退出码检查 |
| 完整 QEMU 浏览器入口 | PASS | Chromium 156.0.8078.73，真实 Worker，`-version` 和 `-machine help`；包含 CoreS3/Core2/StickS3/Cardputer-ADV 等现有板型 |
| 较小初始内存 | PASS，限 CLI | 相同 QEMU 对象只重新链接；初始 256 MiB、最大 2 GiB、允许增长，版本和板型命令均退出码 0；不是 guest 峰值内存 |
| 无固件 QMP/退出 | PASS，限此配置 | `-machine none -S`；真实 greeting、capabilities、query-status、quit ACK 和 SHUTDOWN；显式 process-exit 修正后退出码 0，四个 Worker 在 harness 强制清理前全部自然关闭 |
| CoreS3 固件/LVGL/输入/PIR | PASS，限固定fixture | typed SHA callback、主CPU jump栈恢复及64KiB线程栈；显式vm-div8离线慢时钟下，两新会话的完整LVGL帧/触摸/PIR/ZIP/历史/自然退出通过。默认wallclock曾出现schedule queue full，未关闭该配置缺口；见[证据](evidence/2026-10-28-qemu-wasm-cores3/README.md) |
| Pages/其他浏览器/硬件 | NOT RUN | 未发布；Chromium 本地静态实验不代表实际 github.io、Safari、Firefox 或硬件验收 |

所有浏览器实验使用独立随机端口和新上下文；自己的 SW、Workers、浏览器和
服务均清理。用户测试服务没有被访问。无固件主循环实验属于后端移植回归；
一般固件功能测试继续通过专用 Device Service 的可见 session 取证；显式
浏览器 WASM 验证按当前 AGENTS.md 使用独立静态端口和浏览器本地 session
记录，不能拼接 Device Service 证据。

QMP 实验仍出现 Emscripten 的 `prlimit64`、`mprotect`、`pipe2`、`madvise`
不支持告警。请求响应正常不能证明这些宿主操作在所有路径都安全；当前只
验证了这些无固件控制路径；CoreS3实际guest停止重开另有下面的限定证据，不覆盖所有宿主系统调用。

独立副本的诊断标记已经覆盖 shutdown notifier、main loop、全部 cleanup 阶段
及 C main 返回；这些标记均已出现，但初版没有运行时退出回调。SDK 的
proxy-main 在 main 返回后会检查 keepalive。本轮仅在 Emscripten 下显式
`exit(qemu_main())`，保留完整 QEMU cleanup 及标准 process-exit 路径，修正后
三组浏览器测试均观察到退出码 0 和全部 Worker 自然关闭。没有使用 force-exit
跳过清理；具体 keepalive 计数和挂起 fiber 的来源仍是解释假设，未独立测量。

无隔离响应头的正对照使用同源、项目作用域的
[`coi-serviceworker`](https://github.com/gzuidhof/coi-serviceworker/tree/7b1d2a092d0d2dd2b7270b6f12f13605de26f214)
（MIT），固定源码和 hash 见摘要，采用 `require-corp`。应用的 `doReload`
等待 `serviceWorker.ready` 及 `controllerchange` 后重载；默认立即重载曾触发
首次控制竞态，失败轮保留。需 secure context；这是本地静态实验，尚未部署
到实际 Pages，也没有把 SW 加入产品。

原始失败轮保留：zlib 错选 Darwin libtool、libffi 交叉检测、QEMU configure
选项/静态 gpg-error 定位、`is_daemonized` 重复定义、浏览器脚本误用 machine
名称、无固件退出等待超时。修复后的结果单列，没有覆盖失败记录。

## 来源与体积

QEMU base：[`40edccac415693c5130f91c01d84176ae6008566`](https://github.com/espressif/qemu/tree/40edccac415693c5130f91c01d84176ae6008566)。
基础 WASM 支持参考官方
[`v10.1.0`](https://github.com/qemu/qemu/tree/f8b2f64e2336a28bf0d50b6ef8a7d8c013e9bcf3)，
保留 9.2 版本和现有板级源码，回移适配。
补丁及依赖适配见 [研究补丁](../patches/qemu-wasm-probe/README.md)，
最终 hash 与分层状态见 [构建摘要](evidence/2026-10-28-qemu-wasm-build/summary.json)。

完整 WASM 约 22 MiB，不含 ROM、固件和模型。此前约 4 MiB 的 Rust WASM
与它并非同能力、同构建配置，不能据体积给出性能或兼容性排名。默认模板的
2 GiB 是共享线性内存配置，四个 Worker 共享它；本轮已证明 CLI 可以使用
256 MiB 初始配置。文件大小、线性内存、浏览器 RSS 和 guest 实际需求分别
统计；后续CoreS3阶段另采集活跃进程树RSS，保留共享页面重复计数与非peak/PSS口径。

## 构建复现要点

先从固定 base 新建独立 QEMU 源码，按 `scripts/bootstrap-unit-runtime.py`
的 `PATCHES` 顺序应用全部 30 层，再应用研究 `0001` 和 `0004`。不要在已含 WASM
修改的树重复运行原 native source 校验，也不要 reset 用户已有源码。

隔离安装 emsdk 3.1.50，始终显式设置 `EM_CONFIG`；原生构建工具使用 Meson
1.5.0、Ninja 和 native pkgconf 2.4.3。WASM 依赖版本为 zlib 1.3.1、libffi
3.4.7、GLib 2.84.0（PCRE2 10.44）、pixman 0.44.2、libgpg-error 1.51 和
libgcrypt 1.11.0。依赖 archive hash 见摘要。构建只使用目标 prefix 的
pkgconfig/include/library，不混入 Homebrew 原生库。

以官方
[`emsdk-wasm32-cross.docker`](https://github.com/qemu/qemu/blob/f8b2f64e2336a28bf0d50b6ef8a7d8c013e9bcf3/tests/docker/dockerfiles/emsdk-wasm32-cross.docker)
为依赖参考，实测需要以下修正：

- zlib configure 指定 `--uname=emscripten`，用 SDK 的 `emar/emranlib`。
- Autoconf 同时指定真实 build triplet 和 wasm32 host，避免 Node 可运行导致
  误判为原生；禁用原生汇编/ISA 优化，但保留真实 crypto 实现。
- libgpg-error/libgcrypt 分别应用研究 `0002/0003`；编译 libgcrypt 实际静态
  库子目录，完整上游测试程序未作为通过项。
- GLib 按官方配方关闭未支持的 host 功能，使用 libffi；清除误检的
  `HAVE_POSIX_SPAWN/HAVE_PTHREAD_GETNAME_NP`。官方式 `res_query` 不支持
  shim 只返回 HOST_NOT_FOUND，不能据此宣称 guest DNS 已支持。

QEMU configure 核心参数如下，`EMCC/EMXX/WASM_PREFIX/CRYPTO_PREFIX`
均指向此次隔离目录；并设置静态依赖的 `PKG_CONFIG_LIBDIR`。

```sh
../qemu-source/configure \
  --target-list=xtensa-softmmu --enable-tcg-interpreter --cpu=wasm32 \
  --static --without-default-features --enable-gcrypt --enable-pixman \
  --disable-docs --disable-tools --disable-werror --disable-plugins \
  --disable-slirp --disable-sdl --disable-gtk --disable-cocoa --disable-vnc \
  --disable-curl --disable-libssh --disable-gnutls --disable-nettle \
  --disable-guest-agent --host-cc=clang --cc="$EMCC" --cxx="$EMXX" \
  --extra-cflags="-I$WASM_PREFIX/include -I$CRYPTO_PREFIX/include -Wno-incompatible-function-pointer-types" \
  --extra-ldflags="-L$WASM_PREFIX/lib -L$CRYPTO_PREFIX/lib"
ninja -j3 qemu-system-xtensa.js
```

上述步骤是本次人工实验的复现要点，不是经过干净 CI 验收的一键产品构建器。
关闭宿主 SLIRP/桌面 UI 是首轮构建范围；并不表示已有网络、音频或宿主资源
接入已迁到浏览器。较小内存实验将链接参数 `-sTOTAL_MEMORY=2GB` 替换为
`-sINITIAL_MEMORY=256MB`，并添加 `-sMAXIMUM_MEMORY=2GB`、
`-sALLOW_MEMORY_GROWTH=1`、`-sEXIT_RUNTIME=1`；不修改板级源码。

## CoreS3 实际 guest 与兼容修正

专用 Device Service 经[研究传输](../scripts/qemu-wasm-browser/README.md)管理可见
session，真实 CPU/控制器在 Chromium 的 WASM 中运行。服务原生工具仍准备虚拟
Flash；Node 只运输 UART、QMP、MEMFS PPM 与生命周期。这是移植研究验证路径，
尚未把公众页面改为完全由用户浏览器装载、运行和保存固件。

实际 guest 暴露了两个宿主兼容问题：

- `esp_sha_start` 把返回 int 的 SHA compressor 强转成 void callback，WASM
  会因函数签名不同 trap。`0006` 用三个精确类型的 void wrapper 调用原算法。
- Asyncify Fiber 往返后再 `longjmp`，原 Emscripten 3.1.50 路径没有恢复 C 栈。
  最小真实 C/libffi 复现的负控每轮下降 608/624 bytes；`0009` 保存 setjmp 前
  的 SP，并在非零返回后恢复，再执行原 QEMU cleanup。修正的 2MiB/64KiB
  复现均零漂移，真实 CoreS3 的 64 次 Flash-MMU 入口 SP 也保持一致。
  [独立复现](../tests/browser-qemu/fiber_sjlj/README.md)不需要固件。

`0007` 的 2MiB 栈只保留为历史诊断对照，最终 64KiB 路径不应用它。
`0009` 仅覆盖主 `cpu_exec_setjmp`；`cpu_exec_step_atomic` 的另一个 setjmp
尚未修改或验证，不能称所有异常路径均已关闭。

默认双 CPU/MTTCG、wallclock 的 r11 第二场出现一次 `schedule queue full`，
虽然后续画面与输入仍能运行，该轮必须判 PARTIAL。源码显示 FreeRTOS timer
每30ms先schedule `timer_cb`，再由callback schedule LVGL task；慢TCI下的
回调压力是合理解释，尚不能把MTTCG本身定为根因。single/icount auto 对照未
在120秒内READY；fixed shift8能启动并完成交互，但仍出现queue full，均非修复。

`0010` 增加明确的 Emscripten VM clock divisor。`vm-div8` 固定使用8，默认1
及native行为不变；VM elapsed clock与启停offset使用同一源，host monotonic
与`cpu_get_ticks`不变。保留两个guest CPU、TB链、原定时器、CCOUNT/CCOMPARE
和WDT，**虚拟时间及WDT到期相对墙钟一起变慢**，不能宣称真实频率或物理时序。
它与icount互斥。解析用signed整数并检查1..1024，拒绝负数回绕/空值/溢出；
实际C函数的24组解析/时钟算术对照通过。radio仍有REALTIME pacing路径，
不属于此次离线配置。

在这个显式离线慢时钟下，完整帧、背景负控触摸、两次按钮计数、PIR
false→true→false、两新会话、ZIP-before-stop、历史/租约/Flash释放与Worker
自然退出均有实际证据；逐轮失败与最终源码/固件/runtime绑定统一见
[CoreS3阶段证据](evidence/2026-10-28-qemu-wasm-cores3/README.md)。
完整RGB匹配独立native参考只说明限定fixture的画面已收敛，不是每次screendump
都有原子帧，也不把旧native runtime结果转授新WASM。

## 浏览器控制通道的宿主线程配置

最新main805候选在r15/r16首次完整guest通过，但重开时出现QMP超时。
r16的40秒观测证明socket始终存在、guest心跳与QEMU主循环继续；fd0 poll
在约7秒后不再被独立QMP context访问，screendump未进入monitor而留在JS队列。
所以不能把`wait_qmp`的通用“socket未出现”文字当成被删除，也不能宣称guest停机。
无固件70秒空闲能正常响应，普通stdin EAGAIN也不等于EOF。

`0012`仅让Emscripten stdio的QMP使用现成default main-loop context，
保留原解析/dispatch/response、双guest CPU与原控制器；native及其它chardev
分支保持原选择。它不再offered OOB，当前adapter从未协商OOB，普通in-band
路径不变。这是明确的宿主I/O线程配置，底层GLib/watch具体根因仍未确定。
最终无诊断产物、真实交互/停止重开与独立idle/断连证据见阶段摘要，不以
增加保活请求代替活性修复。

## 当时下一步与准入边界

当前已证明复用原C/QEMU运行真实CoreS3的路线可行，无需把所有外设重写成Rust。
整体仍为PARTIAL：需继续默认时钟/调度兼容、未覆盖异常路径、长期稳定性和公众
浏览器入口；网络socket、BLE peer、音频和文件持久化分别适配。研究传输不回写
MEMFS可变Flash/eFuse/SD，不能继承native快照或retain_flash语义。

后续先把经过准入的离线profile接入公众页面，补浏览器资源装载、输入/帧/串口/
Unit控制及停止重开，再验实际Pages的COI/SW和许可/构建来源。Safari/Firefox、
其它设备/固件与真机均不能继承。当前不能承诺全部设备换编译器即可等价运行，
也不再把这条路线判为不可行。早期30层/CLI结果保留历史范围，与后续guest
结果分别绑定，精确main和补丁兼容来源见阶段摘要。

# 剩余 Xtensa 板型的浏览器准入证据

日期：`2026-10-29`。类别为同一浏览器实例的 virtual-device validation；
物理硬件和本轮正式 GitHub Pages 部署均为 `NOT RUN`。

StopWatch、Cardputer-ADV、StamPLC、StackChan、PaperColor、PaperMono 新增公开
浏览器参考示例；连同既有四板，最终公开导出独立执行 **10 板、11 例**。
CoreS3 两种示例均包含分享重开。完整身份、报告 SHA、同 guest 的串口/帧摘要、
输入和清理见 [summary.json](summary.json)。这些结果只授予固定示例路径，
不授予任意固件、其它 Unit 或原生/物理硬件 PASS。

## 修复与复现实验

QEMU factory、MEMFS、原直接 UART 和 QMP 从 iframe Window 移到 module
DedicatedWorker；iframe 保留直接父源与单 MessagePort 准入。这样 guest
FS 同步代理不再等待 DOM/Three.js 线程。原 Flash、正常时钟、45 层 WASM 的
SwiftShader 对照完成三次真实触摸和 90.147 秒持续运行，实际观察六 Worker
全部关闭时 iframe 仍在。Metal 的独立对照也保留，但不是软件 GPU 支持证据，
也不是当前 46 层 runtime 的性能基准。

- `0016` 明确映射 QAPI qcode 到 Cardputer 物理矩阵，经原 TCA FIFO/I2C
  和原 KeyboardI2C decoder；实际 C 负控覆盖 204 个控制，浏览器实际检查
  11 个选择按键的按下、释放、计数文字与状态像素。
- `0017` 仅 WASM 周期 systimer 对迟到 deadline 作相位保持的推进，防止
  timerlist 重复回放过去的周期。实际 old/WASM/native 控制保留 counter/IRQ
  语义；这项修复单独没有关闭此前浏览器 UART WDT，旧失败仍保留。
- `0018` 根据 [TI SCPS215G](https://www.ti.com/lit/ds/symlink/tca8418.pdf)
  第 16、28–30 页修复默认 CFG0 的 TCA 锁存/W1C：FIFO 非空必须保留 K_INT，
  最后 pop 仍需另行 W1C。45 层 Worker 的 N-release 失败保留；相同固定
  Flash 在 46 层运行时通过 66 项检查。5 项实际 C 前后对照、3 文件无缓存
  复验和完整源码正反应用通过。CFG1 的 50 µs 脉冲及 KEY_IEN 不继承 PASS。

最终 WASM SHA256 为 `9d2db548e3f4b2622d9839b57311cbab7244775a492d4fff660140c19f68ac93`；46 层、147 个修改源文件，所有对象和依赖
完整重建，64 KiB 主栈/pthread 栈与 overflow check 的实际链接参数均核验。
源码包和精确 lock 哈希在摘要中；执行二进制、ROM 和 Flash 不进入源码 Git。

## 最终同源静态导出门禁

所有行共享最终 `publication_eligible=true` 导出和同一个 runtime。静态站没有
Device Service URL；测试阻止 8787、8830 及 `/api/v1` 请求。每行含真实网页选择、
本地固件组合、ready/serial、物理 framebuffer、板级输入、暂停恢复与退出。

| 板型 / 示例 | clock divisor | 完整 Flash SHA256 | 检查数 |
| --- | ---: | --- | ---: |
| stopwatch / board-display-input | 1 | `7300ee10e6dbb0e45af8b322d50e09176331cbf916f06ae52ff7be46f60999cc` | 22 |
| sticks3 / board-display-input | 1 | `a8a88bf4fd2736d4bfd2f4c629b4040c0d38ca8d1ec54156dd74b34cd5a38632` | 23 |
| atoms3r / board-display-input | 1 | `39c8204958c09516407ee6743d532777b7ac81f7650d2fbf7c1038587b361a80` | 23 |
| cores3 / stock-div8 | 8 | `78961297e751ec9c743b4cdf89cc2c137e7e2c801dda3ead9df2ea45d59fbd3f` | 28 |
| cores3 / wallclock-candidate | 1 | `e9500994f4c0e1708ec35f5a46146225ac330d210a2427e1fc537c33635d9554` | 28 |
| cardputer-adv / board-display-input | 1 | `9ca3d53adf8bc81013a1062461961c27ae0450c1ee5e5b1ece6c21753818623b` | 66 |
| stamplc / board-display-input | 1 | `56b2fb1ce84b9fdde53b8e71737913bcf154e39b633b4311c26f2b3fd6e700bc` | 23 |
| stackchan / board-display-input | 1 | `87f453709526d8b70c4951e3c3600f44946fb07a951884170dd1fad7650cae87` | 22 |
| papercolor / board-display-input | 1 | `2ecc41a9ab58c8c8e83d4bea25012460c0e3aaf5a5ebdb339e4590a0a30821bc` | 25 |
| papermono / board-display-input | 1 | `2b7311756055a6b508da9d4717b023149e3d2d1634ae54712aa1786486002f70` | 31 |
| core2 / board-display-input | 1 | `5d252ee60ce0f6a481b13ccdf6f911ac0c41687b888ef273dc7c455e62a5b2c2` | 22 |

电子纸逐像素匹配固定官方 QUALITY 算法的 palette/marker/count bit 抖色规则，
不把实际灰块或 Spectra 色块当均匀矩形。PaperMono 同时验证目标外不计数，
并显式记录 raw 点、原逻辑坐标和释放缓存。非 CoreS3 板型的原生 RGB565 帧
逐像素读回模型纹理，按 nativeRasterRotation 映射，等相应 viewer render
序列后才截图。测试不替换输入、客体像素或控制器结果。

清理门禁只延后 iframe DOM `remove()`，真实 UI stop/QMP quit/dispose 照常。
浏览器必须观察 engine 和五个嵌套 pthread 全部关闭，且此时 iframe 仍存在、
remove 恰好请求一次，随后才真正移除 DOM。正常退出的 dispose 强杀和 owner
fallback 均为零；owner closing 通知及 pre-removal 快照本身不当作 close 证明。
CoreS3 每例两次运行分别重复这一门禁。失败/暂停期间 engine 崩溃的及时报错
和 fallback 收据由额外宿主契约检查，不能用 mock 替代此处客体验证。

## 重建与边界

Python 3.12+，按 [Pages 部署](../../pages-deployment.md) 从固定源码完整构建：

```bash
python3 platform/tools/bootstrap_qemu_browser_runtime.py --jobs 2
python3 scripts/browser-littlefs/build.py \
  --emcc .work/qemu-browser-runtime-build/emsdk/upstream/emscripten/emcc
python3 platform/tools/build_public_site.py --output .work/public-site \
  --base-path /showcase/ --qemu-runtime .work/qemu-browser-runtime \
  --littlefs-runtime .work/browser-littlefs
npm ci --prefix platform/tests
npm exec --prefix platform/tests -- playwright install chromium
M5_PUBLIC_SITE=.work/public-site M5_PUBLIC_QEMU_OUT=.work/public-qemu-admitted \
  node platform/tests/test_public_qemu_admitted_boards.mjs
```

原始日志、帧、失败对照和精确源码收据归档到独立内部 work log；此目录只保留
有界摘要、哈希和复现入口。普通 checkout 的 C/平台契约不需要 `.work` 缓存。

PaperMono stock 逻辑触摸校准、StopWatch 触摸偏差、Cardputer 普通 GPIO IRQ/
Fn/modifier/overflow、EPD 其它模式、长期稳定性、Flash 持久化、网络、音频、
其它 Unit、任意固件和硬件等价性均保持各自边界。CoreS3 旧示例保留 div8；
独立调度候选才是 div1。C6 RISC-V、P4 和 Linux ARM64 浏览器目标仍未准入。
原生全外设矩阵未在本轮重跑；本轮没有新增原生设备或硬件 PASS 声明。

管理员合并后仍须手动运行原仓库 Pages workflow，重新构建、通过全公开板型
门禁并部署，然后从正式 HTTPS 地址另验。本地静态导出 PASS 不表示线上已更新。

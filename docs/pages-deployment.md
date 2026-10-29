# GitHub Pages 虚拟设备部署

入口为仓库根 `index.html`，由 `platform/tools/build_public_site.py` 导出。
GitHub Pages 只托管静态文件；C/QEMU、客体 CPU、板级控制器、
LVGL 和 PIR 在访问者浏览器内运行，不需要 Device Service 或本机 Node 服务。
逐设备准入由 `platform/web/qemu-browser-profiles.json` 的 `admission` 定义，
并与本次 runtime 的 `compiled_profiles` 取交集。已编入二进制的 machine、
候选预览或原生验证均不能自动获得公开准入。未准入的设备可浏览模型或连接
独立 HTTPS Device Service。本轮代码需要重新构建发布；旧站点证据见文末。

## 仓库管理员部署

1. 合并 PR 后，在仓库 **Settings → Pages → Build and deployment → Source**
   选择 **GitHub Actions**。工作流不会代替管理员启用 Pages。
2. 打开 **Actions → Prepare public simulator site → Run workflow**，选择 `main`。
   `publish=false` 先构建并验证，下载 `public-simulator-site-preview` artifact
   可审查导出内容。首次完整源码构建较慢，工作流上限为 90 分钟。
3. 确认后再次运行，设置 `publish=true`。项目站的 `base_path` 默认
   `/m5stack-esp-emulator/`；若更改仓库名，需要同步前缀。用户站或独立域名根路径用 `/`。
4. `service_url` 默认留空。仅需其它原生设备时配置公开 HTTPS 服务地址；
   **不要**填入 token、带密码的 URL、本机地址或内部端点。
5. 部署 job 完成后打开其 `page_url`。首次访问会注册项目范围内的
   Service Worker 并刷新一次，以启用 QEMU pthread 所需的共享内存。
   选择已准入设备，点击“开始运行”，等待示例画面，再测试相应按键或触摸。
   CoreS3 可选择正常速度的 LVGL 调度候选修复示例，或保留的原始慢放基线。

工作流只接受手动触发。部署要求 `main`、显式 `publish=true`、构建和每个
公开板型的真实客体验收成功，包括 CoreS3 两种示例。候选预览导出明确标为
`publication_eligible=false`，聚合发布门禁拒绝它。构建 job 只有仓库读取权限，
部署 job 才取得 Pages/OIDC 权限。
不要只复制 `index.html`：模型、字体、WASM、Worker、固件组合器和对应源码包
都必须按 artifact 中的目录结构保留。

## 访问者流程与浏览器要求

默认打开网页即可使用，不要求登录。此 PR 不包含账号、OAuth、后端数据库或
共享会话。若产品需要账号鉴权，应另接真实身份服务；静态 Pages 无法安全保存
服务端密钥。

推荐桌面 Chromium，使用 HTTPS、允许本站 Service Worker 和共享内存。
浏览器至少需要约 256 MiB 共享 WASM 初始内存，允许增长；最大配置为 2 GiB。
关闭标签页、停止或刷新会释放该实例。低内存设备、其它浏览器和后台标签页
调度没有相同的验收结论。

参考固件由浏览器直接从固定官方 CDN 下载，校验 SHA256 后，用源码构建的
LittleFS WASM 在本地组合固定源码，重新挂载逐文件读回并核对完整 Flash。
CoreS3 原始示例仍精确匹配 `78961297…bd3f`；正常速度示例另加入
`candidate_lvgl_loop.py`，精确匹配 `e9500994…9554`，包含明确的 Python
LVGL 调度候选修复。其他板型的显示/输入 probe 使用各自基底、分区布局和
源码配置；完整 SHA、原文件保留数量及执行身份写入组合收据。
ROM 同样从固定 Espressif 官方地址直接下载并校验。下载需要上游 CORS 可用；
断网、CDN 撤回、SHA 不匹配会明确失败，不替换为主机绘制的演示画面。
URL / 本地 `.bin` 入口按选定板型检查完整 ESP32/S3 合并镜像、芯片与分区边界；
未验证固件不获得兼容性承诺。

触摸经 QMP 绝对坐标和板级触摸控制器到达 LVGL；PIR 经 Unit 模型和 GPIO
到达原固件驱动。串口、帧和本地证据来自同一浏览器实例。停止保留页面最后一帧，
可下载 JSON 运行记录；本机历史仅保留最近五条摘要和串口，不保存 Flash、
跨设备共享状态或刷新后的历史画面。浏览器存储不可用时仍可运行和下载记录。

## 时间、功能与许可边界

- CoreS3 原始基线保留 `cores3-wasm-vm-div8`：虚拟时间与看门狗到期均
  相对墙钟慢放八倍。只有完整 Flash SHA 匹配的正常速度候选示例才选择
  `cores3-wasm-wallclock-sdk-candidate`、clock divisor 1；未知固件保留原配置。
  Python 调度候选不修复 C timer 第一层的重复入队，也不授予 stock SDK 或
  其他应用稳定性结论。新板型的时钟、ROM 和输入按各自 profile 验证。
- 共享帧来自真实 QEMU display surface，带序列校验，普通采帧不再使用
  QMP/PPM 临时文件。约 33 ms 的取帧周期是传输上限，不是动画 FPS。
  静态画面可零传帧；性能报告分别记录请求、传帧、像素变化与输入延迟。
- 保留双客体 CPU、TCI、原板级与 Unit 控制器、QMP in-band；不提供 QMP OOB。
  网络、音频、其它 Unit、Flash 持久化和任意固件兼容性均需分别验证。
  当前网页 C/QEMU 配置只开放 UART 输出；串口文本输入保持禁用。
- 纯网页记录属于 `browser-local-qemu-evidence`，没有远程 `/api/v1` lease；
  不将原生服务、其它 guest 或物理设备结果拼接成浏览器 PASS。
- QEMU WASM 及链接依赖保留各自 GPL/LGPL/宽松许可。站点随执行文件提供
  `platform/runtime/qemu/NOTICE` 和 `corresponding-source.tar.xz`，包含修改后的
  QEMU、完整补丁/构建配方、依赖来源及许可；重新分发时必须保留这些材料。
- 仓库和 Pages artifact 不打包 ROM、官方固件或派生 Flash。公开下载地址不被
  当作再分发授权；它们只在访问者浏览器取得、校验并使用。

## 本地重建与验收

需要 Python 3.12+、C/C++ 构建工具、autoconf/automake/libtool、bison/flex、
ninja、Git，以及足够的构建磁盘空间。构建器使用隔离目录和固定 Emscripten 3.1.50，
不修改全局 SDK。详细来源见 [C/QEMU 构建配方](../scripts/qemu-wasm-build/README.md)。

```bash
python3 platform/tools/bootstrap_qemu_browser_runtime.py --jobs 2
python3 scripts/browser-littlefs/build.py \
  --emcc .work/qemu-browser-runtime-build/emsdk/upstream/emscripten/emcc
python3 platform/tools/build_public_site.py --output .work/public-site \
  --base-path /m5stack-esp-emulator/ \
  --qemu-runtime .work/qemu-browser-runtime \
  --littlefs-runtime .work/browser-littlefs

npm ci --prefix platform/tests
npm exec --prefix platform/tests -- playwright install chromium
NODE_PATH="$PWD/platform/tests/node_modules" \
M5_PUBLIC_SITE="$PWD/.work/public-site" \
M5_PUBLIC_BASE_PATH=/m5stack-esp-emulator/ \
node platform/tests/test_public_qemu_admitted_boards.mjs
```

验收器只启动随机端口静态文件服务器，无 COOP/COEP 响应头，以覆盖 Pages 的
Service Worker 首控流程。聚合器为每个公开板型启动独立 guest，CoreS3 两例
执行下载/组合、LCD、DOM 触摸正反例、PIR、暂停/继续、停止/重开与四档宽度；
其他板型检查完整标记像素、原驱动输入与清理。原始报告在 ignored
`.work/public-qemu-admitted`。只验 CoreS3 时可显式设置
`M5_QEMU_EXAMPLE=stock-div8` 或 `wallclock-candidate`，运行
`platform/tests/test_public_qemu_guest.mjs`。
对已部署站点可设置 `M5_PUBLIC_URL=https://<owner>.github.io/<repository>/`
复用同一验收器。不得把本地子路径测试写成公开部署测试；实际 URL 和结果写入验证台账。

## 已验证的部署参考

正式站点已部署到
<https://m5agent.github.io/m5stack-esp-emulator/>。原仓库
[Pages 工作流](https://github.com/m5agent/m5stack-esp-emulator/actions/runs/40719197233)
绑定 main 提交 `8e47c6ba`，完成固定源码构建、真实 CoreS3 guest 验收和
GitHub Pages 部署；部署后从正式 HTTPS 地址独立复验 21 项检查全部通过。
站点 manifest 声明 `1922` 个资产，`service_url` 为空，
`firmware_bundled=false`。运行时、固件 SHA、公开报告 SHA 和边界见
[正式部署证据](evidence/2026-10-29-github-pages-production/README.md)。

测试 fork 的 [Pages 站点](https://yuyun2000.github.io/m5stack-esp-emulator/) 已由
[Linux Actions](https://github.com/yuyun2000/m5stack-esp-emulator/actions/runs/40689514606)
从固定源码构建、完成真实 guest 验收并部署；公开 HTTPS 地址另跑同一验收器通过。
确切运行时/固件 SHA、检查与限制见[部署证据](evidence/2026-10-28-qemu-wasm-pages/README.md)。
该 fork 结果保留为部署前对照，不替代上面的正式站点证据。

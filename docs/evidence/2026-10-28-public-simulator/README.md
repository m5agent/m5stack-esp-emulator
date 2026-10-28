# 公众模拟器：浏览器执行与页面验证

日期：2026-10-28。源码基线 `2740fd767478a6599ce4d5533cb5d1b345730222`；
本轮修改在 `codex/public-simulator-workbench`。哈希与逐设备检查点见
[summary.json](summary.json)，架构对照见[浏览器调研](../../browser-runtime-feasibility.md)。

## 已复现的浏览器执行

`PublicBrowserRuntime` 在 Chromium 的 module Worker 内执行固定源码构建的
esp32sim WASM。PaperS3 使用 JIT，StopWatch 使用解释器以避开上游 IMU JIT
卡住路径。两份独立干净 source archive / Cargo target 构建得到相同 WASM。
ROM、源码与固件 SHA 均在 summary 绑定；WASM/ROM/固件不进入源码 Git。

- PaperS3 官方出厂 v0.5：540×960 真实控制器 RGB565 LE 帧，GT911 触摸切换
  蜂鸣器图标，串口应用 marker、暂停与停止；仿真 API 请求为零。
- StopWatch 官方 UserDemo v0.5：468×466 原始帧，A+B 打开菜单、触摸进入应用，
  暂停与停止；仿真 API 请求为零。模型面板宽466，原始帧宽468，未验证裁剪映射，
  页面保留原始屏幕单独显示，不授3D纹理映射通过。
- 两设备的首次应用检查点约为本机15秒；这只是单次观测，不是速度承诺或对照
  基准，没有同固件峰值内存/CPU/FPS对照。
- 官方 CDN 两个固件 URL 已另由 Chromium 实际跨域 GET：HTTP200、可读 `cors`
  响应、字节数和SHA一致；不将本地镜像fixture通过当成公网CORS通过。

复现（Node/Playwright 与 Chromium 可用，先将官方固件下载到本机 ignored 目录）：

```sh
python3 platform/tools/bootstrap_browser_runtime.py --fetch-rom
node platform/tests/test_public_browser_guest.mjs --execute \
  --device papers3 --runtime .work/browser-runtime \
  --firmware /path/to/papers3-factory-v0.5.bin --out .work/papers3-recheck
node platform/tests/test_public_browser_guest.mjs --execute \
  --device stopwatch --runtime .work/browser-runtime \
  --firmware /path/to/stopwatch-userdemo-v0.5.bin --out .work/stopwatch-recheck
python3 platform/tools/build_public_site.py \
  --output .work/public-site --base-path /showcase/ \
  --browser-runtime .work/browser-runtime
M5_PUBLIC_SITE=.work/public-site node platform/tests/test_public_workbench_browser.mjs \
  --real-browser-runtime --runtime .work/browser-runtime
```

固件公开 URL 和 SHA 位于 `platform/web/browser-profiles.json`。普通 checkout
测试不会下载或执行固件；真实 guest 回归必须显式 `--execute`。首次 PaperS3
回归因 native fetch receiver 绑定错误失败，修正后重跑通过；失败原始记录保留。
访问第三方线上网页失败的尝试也未记为该站点功能 PASS。

## 首页与模型的完整回归

最终首页单次17组检查通过：`/showcase/` 子路径与设备别名、URL下载/SHA后自动
启动官方PaperS3、实际DOM鼠标触摸改变图标、暂停/继续/停止、四档布局、未知设备、
下载取消和错误恢复，以及服务控制台导航、失败重连和未知创建结果的切换限制。
其中原生停止、Unit选路、目录失败、重连和未知create五组使用UI fixture，不授guest通过。
PaperS3外壳在390宽度的缩放过渡越界已修复，四档实际bounds均在stage内。
默认 `npm --prefix platform/tests test` 内的首页16组契约不执行guest；真实guest需显式选项。
旧service smoke保留为 `test:legacy`，必须指定独立测试origin并拒绝8787。
未连接时，设备会话与WebBurner入口展开连接面板，不向静态Pages请求API；连接后
指向所选服务的控制台，保留服务路径前缀。候选服务失败或旧会话停止未确认时，
原服务、Unit配置和控制台链接保留。最终source hashes与17组report SHA见summary。

最终390宽度完整截图已目视检查。早期连续resize后立即截图曾出现重复页面片段的
compositor取证问题；补充与默认布局检查相同的150ms绘制等待后，最终独立整轮
截图正常。没有修改DOM边界断言，最终真实运行首个应用检查点为14,767ms。

模型来源固定在 `c48940c3aad3f2e8e9b8906b82071a88f2a3de1e`。最终第三轮独立
完整运行15m36s通过17主机、184附着Unit、201独立预览和423张PNG；所有140个
浏览器context关闭，无页面错误或资源缺失。13个显示主机验证RGB565 BE/LE与PNG
红绿蓝及原生旋转。视觉预览不会向guest发送控制，附件销毁、输入无回声、嵌套HUB、
焦点按键释放和WebGL fallback均在同轮检查。

前两轮失败保留：PoE-P4的固定色LED未纳入测试oracle；TimerCamera-F/X的固定蓝色
组件还揭示了真实unknown清理问题。修复后固定色保留原色并归零亮度，RGB仍清黑；
先做定向回归，再完成独立全量第三轮，没有拼接各轮为完整PASS。以上是浏览器模型
集成证据，不证明外设控制器协议、电气接线、可选产品配置或固件兼容性。

上一轮平台单次1355项通过、4项可选固定编译器/源码依赖跳过；四生成器、Node契约、
UTF-8/JSON/隐私路径与凭据检查当轮通过。这是最终创建恢复/导航修改前的历史整轮，
不作为最终源码全集通过声明。源码范围不包含ROM/WASM/固件/ZIP/依赖目录。

## 可选原生桥：受控CoreS3示例

独立Device Service通过跨origin/token、分块上传与导入，执行现有
`tests/uiflow2/cores3_ui_test/main.py` 的源绑定固件。最终plain `runtime=qemu`
同guest完整通过：真实320×240帧、controller输入(160,180)使touches从0变1，
左上角绿色marker由0变16像素，计数区域220像素变化；串口保留实际309字节。
固件、源码、runtime、前后/历史帧和ZIP的SHA均见summary。

实际pre-stop ZIP先于DELETE `purge=0`取得，8个文件的大小/SHA和guest身份核验
通过；历史保留同一触摸后帧，Flash释放，guest/自建服务退出且无活跃lease。
新opt-in入口 `test_public_native_service.mjs` 需要显式独立服务、token文件和
固件/compose receipt，不会默认访问用户服务。

早期harness错误保留并纠正：串口任意长度不能当应用ready；异步等待必须显式
await布尔结果；短暂面板初始化不能当示例首帧；二进制仪表空响应不能当ZIP为空。
最终整轮使用真实应用像素、guest输入反馈和controller的实际ZIP Blob。

该PASS只覆盖受控plain示例。stock镜像此次只验证上传与DEVELOP画面；unified
虽已渲染示例，但没有预期READY串口marker，未完成该路径输入验收。不能说应用
没有执行，也不能把plain示例转授stock/unified。这些是可选原生路径的扩展验证，
不作为已限定两设备browser发布的硬门禁。本轮未新跑完整原生外设矩阵，未部署。

## 原生创建响应丢失：独立真实回归

最终首页通过独立Device Service实际上传CoreS3原BIN并导入。服务真实分配session、
启动QEMU PID后，测试丢弃第一次202响应；首页自动停止流程以完全相同JSON字节和
key重放。两次POST的`idempotent_replay`依次为false/true，只新增一个历史session。
同guest的7文件evidence ZIP先于DELETE `purge=0`取得且全部大小/SHA核验通过；
终态lease释放、active sessions为0、实际guest PID退出，自建服务关闭并释放端口。
源码、输入/规范固件、QEMU与ROM、ZIP及完整receipt的SHA绑定见summary。
这轮证明短时丢响应的真实创建/恢复/停止生命周期，没有执行应用显示或输入验收。

创建恢复使用完整原始body与相同`idempotency_key`重放POST；不能修改Unit配置后
沿用同一key。服务持久化key/body摘要与session映射，最多4096条，映射本身没有
独立TTL。当前客户端租约为600秒，重放不续租；历史purge/prune、映射淘汰或状态
丢失后不保证继续去重。这不是永久收据，也没有只按key查询会话的接口；首次POST
根本未到达时，恢复POST可能首次分配设备。页面内的未知intent恢复前仍保留owner
并禁止切换设备或服务；刷新后丢失页面内存intent不属于自动恢复保证。本轮未验证
服务重启或长时间断连，不向其他固件或原生路径转授通过。

```sh
node --experimental-default-type=module platform/tests/test_public_session_recovery_service.mjs \
  --execute --service http://127.0.0.1:8829 --token-file /path/to/private-token-file \
  --firmware /path/to/public-cores3-uiflow2.bin --python /path/to/python3.12 \
  --out .work/public-native-recovery-recheck
```

## 边界

这些结果属于 browser virtual-device validation，不是 hardware validation。
公开交付范围是静态站、固定source-build内核和PaperS3/StopWatch两profile的上述
官方固件路径，以及独立视觉模型。原生服务是可选连接，受控CoreS3通过不授全native PASS。
PaperS3 的16级灰阶、RTC/TF/音频/电源键/联网，StopWatch完整外设与浏览器
Unit原驱动均未通过本轮验收；其他主机不能继承本轮结果。PaperS3无专属3D模型，
保留原生方向的2D屏幕。本站支持的 native QEMU 路径需要另行连接 Device Service。

没有访问、停止或重启用户的8787；没有部署到GitHub Pages。原始帧、串口、
下载固件、完整报告均在 ignored `.work` 与本地工程记录，源码只保存精简总结。

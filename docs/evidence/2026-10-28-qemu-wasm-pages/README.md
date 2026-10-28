# CoreS3 C/QEMU 静态网页验收

日期：2026-10-28。结论限定为 browser virtual-device；物理硬件 NOT RUN。

[测试站点](https://yuyun2000.github.io/m5stack-esp-emulator/) 已完成 Linux Actions
固定源码构建、导出站真实 guest 验收、Pages 部署及公开 HTTPS 独立复验。
[成功部署运行](https://github.com/yuyun2000/m5stack-esp-emulator/actions/runs/40689514606)
绑定 `ff9b39fca75a7dafc907d8736daa68c3c456faa6`；原仓库部署仍由管理员执行。
部署步骤和免登录访问方式见 [Pages 指南](../../pages-deployment.md)。

## 固定执行范围

Emscripten 3.1.50、双客体 CPU / TCI 与真实板级控制器；实际链接命令确认主栈及
pthread 栈各 64 KiB、STACK_OVERFLOW_CHECK=2。限定配置为 `cores3-wasm-vm-div8`。
固定官方基底在访问者浏览器由 LittleFS WASM 写入示例源码，最终 Flash SHA 为
`78961297e751ec9c743b4cdf89cc2c137e7e2c801dda3ead9df2ea45d59fbd3f`，
ROM SHA 为 `b5c7090cc22efce51c1323cef31ca96fcd673a5b1d1b1017e219d393f2659913`。

| 验收层 | WASM SHA256 | 实际结果 |
| --- | --- | --- |
| macOS 本地无隔离头项目子路径 | `4e707f78d54fc813840cb3dde4d93786743b3ca35d49f33773229830ce732b87` | 21检查、两场、10 Workers关闭 |
| Linux Actions 导出站 | `716f3b6a8750335613da2897be0933d1497965962d0dc1b3f2754ebf76316c89` | 21检查、两场、13 Workers关闭 |
| 公开 HTTPS 页面 / Chrome 156.0.8078.73 | 与本次 Linux 构建相同 | 21检查、两场、10 Workers关闭 |

每轮首场完成首次 SW 控制/共享内存、真实 RGB LCD、DOM 触摸正反例、PIR QOM
及客体双向转换、QMP 暂停/继续、1440/1024/768/390 布局、正常停止与本地历史。
第二场验证分享链接自动启动新 guest、ready 串口和正常退出；不授予第二场完整
LCD/输入回归。各场 exit=0、WorkersAtExit=0，容器 dispose 无需强制终止 Worker。
无 JavaScript 错误，也没有访问 Device Service 或本机仿真接口。

公开报告 SHA 为 `0bdf6a9d17f81714d72fb82d6f66c2d83c9feef450888991d3596a847c970d6d`；
Linux 报告 SHA 为 `078ed666d23b30ea758b2e9ef0083e7dabe8154409bf37fe019ca163aa6d69fa`。
公开与 Linux 验收的 site/runtime manifest SHA 逐字一致，详见[脱敏摘要](summary.json)。
JSON 原始证据含同一实例的 runtime/固件 SHA、串口、真实像素、输入和退出状态；
报告、截图、请求和失败轮保留在内部工作记录，源码只提交摘要。

## 分发与源码核对

公开对应源码包 35,141,752B，SHA 为
`4f8d90840bde7df6e868b72a2cc79ab006c4c485f1413b34a6ef8dcc86a090f1`。
144 个锁定源、40 个 QEMU 补丁、2 个依赖补丁、9 个依赖归档及 recipe/lock
全部匹配。公开包与本次 Linux 验收产物绑定，归档外层无 ESP ROM、固件或测试磁盘镜像。
保留的15个非Xtensa Linux-user VDSO helper（46,896B）已单列核对，对应源码、
构建规则和 GPL 标识在同包；它们不是 ESP 固件。未递归审计依赖归档，也未验证
完整离线重建或源码到二进制逐位对应。旧本地 v4 包中的非目标 QEMU iotest sample
保留为历史证据；当前 CI 包已排除 sample_images 和不透明镜像后缀。

修复包括 pthread blob 地址重定位、共享 HEAP 复制后 UTF-8 解码、UART/PPM 独立
解码、QMP VM running 门禁，以及 generation/取消/禁用存储/退出/receipt 隔离。
首次 Linux 运行因未安装 headless shell 在启动浏览器前失败；修正安装后完整重跑。
本机公开复验的首次 Node 资源预检在浏览器启动前中断，最终使用系统 HTTPS 代理
完成静态资源核验；仅增加进度日志，没有修改验收器或网页执行源码。

## 边界与复现

本轮不验证默认墙钟下的 LVGL 调度缺口、其它异常路径、长期稳定性、网络、
音频、其它设备/Unit、任意固件兼容性或 Flash 持久化。vm-div8 下虚拟时间与
WDT 一起慢放至墙钟的1/8；UART 仅输出。完整原生矩阵和硬件本轮 NOT RUN。

按 Pages 指南构建后设置 M5_PUBLIC_SITE 与 M5_PUBLIC_BASE_PATH，运行
`node platform/tests/test_public_qemu_guest.mjs`；公开 URL 验收另设 M5_PUBLIC_URL。
原始报告分别保留各轮输入、来源哈希和结果，不拼接其它 guest/原生/硬件结论。

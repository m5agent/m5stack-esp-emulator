# CoreS3 C/QEMU 静态网页验收

日期：2026-10-28。结论限定为 browser virtual-device；物理硬件 NOT RUN。

最终本地产物使用 Emscripten 3.1.50、双客体 CPU / TCI 与真实板级控制器，
实际链接命令确认主栈及 pthread 栈各 64 KiB、STACK_OVERFLOW_CHECK=2。
固定官方基底在访问者浏览器由 LittleFS WASM 写入示例源码，最终 Flash SHA 为
`78961297e751ec9c743b4cdf89cc2c137e7e2c801dda3ead9df2ea45d59fbd3f`，
ROM SHA 为 `b5c7090cc22efce51c1323cef31ca96fcd673a5b1d1b1017e219d393f2659913`。
WASM SHA 为 `4e707f78d54fc813840cb3dde4d93786743b3ca35d49f33773229830ce732b87`。

无 COOP/COEP 响应头的项目子路径静态服务器，首次 SW 控制/共享内存、
真实 RGB LCD、DOM 触摸正反例、PIR QOM 及客体双向转换、暂停/继续、四档
1440/1024/768/390、正常停止、历史摘要和分享链接第二场自动启动共 21 项 PASS。
两场共 10 Workers 关闭；每场 exit=0，Emscripten 退出时已无 Workers，随后
容器 dispose 无需强制终止任何 Worker。未向 Device Service 或 Node 仿真接口请求。

JSON 本地证据含同一实例的 runtime/固件 SHA、串口、实际像素、控制器输入和退出状态。
源码仅提交[脱敏摘要](summary.json)，原始报告/帧/请求与失败轮保留在内部工作记录。

修复的网页边界包括：pthread blob 相对 URL 的确定性地址重定位；共享 HEAP
先复制后 UTF-8 解码；UART 与 PPM 独立 decoder；QMP VM running 门禁；
旧 generation/取消/禁用存储/非零退出/旧 receipt 的隔离，以及本地生命周期记录。

公开部署当前 NOT RUN，不能从本地子路径 PASS 继承。Linux Actions 将从固定源码
完整构建，并在最终站点包上重跑同一真实 guest 测试；部署说明见
[Pages 指南](../../pages-deployment.md)。旧 v4 的对应源码包含非目标 upstream
QEMU iotest sample，最终 CI 配方只修包装过滤、不改变 C/链接路径。

本轮不验证默认墙钟下的 LVGL 调度缺口、其它异常路径、长期稳定性、网络、
音频、其它设备/Unit、任意固件兼容性或 Flash 持久化。vm-div8 下虚拟时间与
WDT 一起慢放；UART 仅输出。完整原生矩阵和硬件本轮 NOT RUN。

复现：按 Pages 指南构建后，设置 M5_PUBLIC_SITE 与 M5_PUBLIC_BASE_PATH，运行
`node platform/tests/test_public_qemu_guest.mjs`。公开 URL 验收另设 M5_PUBLIC_URL。

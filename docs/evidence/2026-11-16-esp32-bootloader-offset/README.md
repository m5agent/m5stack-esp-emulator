# ESP32 ROM 引导偏移校验

[Issue #228](https://github.com/m5agent/m5stack-esp-emulator/issues/228) 的原版 BIN
`16cd916ac688555171a6d00ebf877d71053fcd40148c493564ab70ca90992c82`
在 `0x0` 放了 bootloader，将段数据 `40 20 20 04` 留在 ESP32 ROM 的读取位置 `0x1000`。
[旧版复现](baseline-summary.json)在 `12c01eab…` 接受合并、导入并判 `valid=true`；62.41 秒内
串口重复 19 次 `invalid header: 0x04202040`，停止前 ZIP 里的 135×240 帧为全黑。

[同镜像复验](summary.json)绑定服务源码 `1cb1975b…`、同 Xtensa `5ce7d9f5…` 和同 ROM
`9115bbcd…`。普通合并及已存错位镜像的会话请求返回 422，包导入返回含引导偏移的 400，
重新分析为 `valid=false`。独立审核进程以保存快照和原版 BIN 得到 `E_STATIC`，该请求未创建会话。
官方 StickC-Plus2 UIFlow2 2.5.4 `9b553277…` 的 bootloader 在 `0x1000`，分析通过；原生串口
出现 `Startup with network type: WIFI`，最终 Cloud 画面有 32,301 个非黑像素。

本记录覆盖 virtual-device validation。首次截图观察的方向参数及正控串口断言有误，原始失败日志保留，
黑帧另从旧版 ZIP 解码，正控使用板面帧和真实启动标记。物理硬件、配对和浏览器执行为 `NOT RUN`。

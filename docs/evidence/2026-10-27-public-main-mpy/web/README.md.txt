# Public main.mpy Preview Web evidence — 2026-10-27

本目录保存同一代 45 服务、同一 CoreS3 虚拟设备的实际 Web 验收，以及关键离线回归。入口为 `index.json`；便携核验：

```sh
python3 -B verify.py
```

核验只读取归档，不连接服务、不创建 guest、不产生新的固件执行或硬件证据。需要核对仍保留的内部原文件时使用 `--check-originals --workspace <repository>`；默认不依赖原工作树或 /tmp。

## 已验证的范围

- 6 个 mandatory 阶段通过：只读加载外部 main.mpy 包、Web Run、Web 重复 Run、PIR true、PIR false、取消后通过“新建 main.py 程序”恢复源码运行。
- 原 VM 的私有 nonce 和 REPL owner 保持一致，MPY 顶层真正执行计数为 1 → 2 → 3；name/main/sys/import 身份、实际 main.mpy/dep.mpy 路径和依赖值来自本次 execution.serial_offset 之后的 LOAD 窗口。MPY LOAD 不代表 START 或应用就绪。
- 原始 binary checkpoint 前后 GET 完全相同。两个 Web MPY Run 复用原 revision，没有保存/改写字节码；回源码操作只在用户点击 Run 时保存新的 main.py 完整包，删除根 main.mpy 并保留 dep 原字节。
- 7 次实际 Web 写操作：2 次 MPY Run、2 次 PIR 输入、1 次取消、1 次源码包保存、1 次源码 Run；没有创建新的 session。
- 原始 direct API PNG 中心依次为绿、绿、绿、白、绿、蓝，均有 execution/revision/frame hash；真实 3D 外壳屏幕、PIR mounted anchor 与 annotation、串口和 guest-QOM 分开采样并相互核对。它们不是原子快照，也不是物理设备测量。
- 最后 ZIP 在交还清理权限前取得；归档只保留其原 SHA/大小和成员指纹，未保存 ZIP 字节。ZIP 内最后一帧 SHA 与最后 direct PNG 一致。最终关闭/释放凭据由根目录 API-runtime 证据持有。

## 必须保留的 PARTIAL

Optional browser response capture 有 364 条响应。其中 8 条 HTTP 200 PNG 响应被 Playwright 观察为 0 字节：保留原空体和原始指纹，明确标记 PARTIAL，不当作 PNG 或 texture-transfer PASS。另有 77 条正常 HTTP 304，合法地没有响应 entity，没有虚构 body 文件；它们与 200 零体分开统计。6 个 mandatory 阶段的 direct PNG、mounted 屏幕、串口和 QOM 验收独立通过，不借这些可选空体证明显示。

## 文件与指纹

- `live-gen45-r1/`：原运行的 report、逐次 API/browser 响应、6 张 direct PNG 与 12 张 mounted/card 截图。JSON 内原文件字节 payload 已替换为 redacted metadata；本目录不含原 main.mpy、dep.mpy、固件、ROM 或 ZIP 字节。
- `observer/`：执行 observer、默认不接触 API 的计划与归档脚本。
- `offline/`：109 项 Preview Python、25 组 shared-client、33 组 managed editor、14 组 ordinary editor、11 组创建/恢复 browser 回归。均为 host/browser fixtures，不能据此声称 guest 或硬件通过。
- `source-snapshot/`：Web 与相关 Preview/test 源码。于执行后采集；凡 live report 记录的源文件，其内容 SHA 与执行前/后记录一致。额外 helper/test 快照仅用于复现上下文，不扩大 live 指纹覆盖。完整固件/MPY 源码、编译工具链和 recipe 由根目录 API-runtime 证据提供。
- `index.json.originals` 区分 original SHA256/SHA512 与实际 archive SHA256/SHA512。JSON payload/本机工作树路径发生脱敏时，两个指纹分别保留，不能把脱敏文件 SHA 当作原响应 SHA。被省略的 ZIP 只有 original 指纹和成员 metadata，没有 archive 文件。
- `manifest.json` 覆盖便携目录中每个实际文件；`verify.py` 进一步核对六阶段身份、计数、PNG CRC/中心像素、取消、source fork、依赖原 SHA、PARTIAL/304 分类与离线回归凭据。

本目录只证明所列固件、profile、运行实例和输入路径的 virtual-device 结果。Hardware execution: NOT RUN。

# 默认同色灯反馈与 UIFlow 程序能力契约

日期：2026-10-26。归属 `UNIT-01`。硬件验证：NOT RUN。

本块把默认网页的 RGB/Encoder/8Encoder 全灯同色与全灭接入真实 3D 灯组件，
并明确同 VM 程序入口契约。非对称灯分布没有物理通道依据时保持 unknown；
未知外观撤掉旧颜色/亮度/发光，不代表已观察到电气关灯。原电气数组继续显示，
状态读取恢复后重新应用。同色依据是任意未知排列下全 N 同色不变，不是猜测通道。

`GET /devices.program_features` 明确四款准入主机仅 `qemu`、`main.py` 入口、
纯字节码 `.mpy` 依赖、fresh exec globals 和 interrupt-only；二进制入口与
native emitter 为 false。未准入设备返回空对象；这不授予任意上传固件 REPL 兼容性。
[实际7设备查询](verification/uniform-led-program-features-live-20261026.json)
与[宿主156项定向测试](verification/uniform-led-program-features-host-20261026.txt)分别留证。

## 证据层次

- [官方绑定研究](binding-research/README.md)：固定资料、内部固件/原理图和排列证明；
  逐灯位置、旋转物理 source/角度/方向及极性仍待验证。8Encoder逻辑counter
  可被guest写/reset，不能直接据此驱动机械轴。
- [mounted前端fixture](frontend/README.md)：14颗实际灯、unknown/恢复、非法值、
  首次/轮询HTTP失败、显式mapping优先、6种迟到GET销毁顺序及零回声。
  原r4使用旧cache标签；[g版七程序回归](verification/node-final/report.json)
  和[同色fixture](verification/node-final/uniform/report.json)单独保留最终源码SHA。
- [最终完整新批次r3](live-browser-r3/README.md)：两可见session、8次同VM程序、14个实际灯组件/材质断言，I2C/RMT原驱动、独立QOM/fresh串口、真实帧、默认无binding网页和浏览器503恢复。新的front/iso定位截图与直接WebGL PNG完整取景；这是完整canvas取景，不是全部14灯同屏无遮挡或Encoder两灯光学可读性验收。
- [真实会话r2与首轮失败](live-browser/README.md)：每组同一CoreS3 VM连续四程序，
  分别使用被动HUB上的Encoder/8Encoder真实I2C驱动和直连RGB的RMT驱动。
  r2的数据/材质/串口/QOM断言通过，A/B/C/D浏览器图片裁掉了上部3D区域，
  因此不作为完整浏览器视觉展示；截图修正后的新整批另列，不拼接结果。
- [main.mpy研究](main-mpy/README.md)：固定源码与CoreS3同VM实验确认普通导入
  不执行if-main；新source globals也不替换REPL主模块。初始化后动态运行的
  主路径无需每次重刷固件，完整二进制脚本入口仍OPEN。

真实层限定稳定程序阶段；frame、Unit GET和独立QOM是分次采样，不声明原子快照。
通用ZIP QOM存在500-node截断，不能当作完整Unit raw；相关独立raw QOM保存在
各阶段报告，ZIP另核最终leaf状态、串口字节窗口、程序/source及成员大小/SHA。
功能测试只走8787 Device Service可见session，先ZIP，再stop/purge0；默认释放Flash，
保留历史/末帧并独立核owned PID退出。

## 兼容性与剩余边界

保留显式有证据的LED mapping优先、既有输入API和所有未改controller模型。
新增known=false只表示反馈未知，不生成Unit输入POST。显式unknown组件、DOM提示、
材质与diffusion/glow同时撤回，失败命令不能把unknown升成known。

UNIT-HOST-29的逐灯位置/旋转、UNIT-HOST-33的main.mpy入口仍OPEN；Preview/Run、
SSE、AIFlow checkpoint/虚拟目标、程序revision回收及完整native/IRQ/thread清场未完成。
本块未改QEMU/C控制器，完整矩阵本轮NOT RUN；上一独立完整轮66/67的Core2 IMU
marker问题继续保留，不用单例或本块浏览器结果补成PASS。虚拟结果不授予机械、电气、
光学或真机结论。

## 本块验证与保留记录

前端g版本七个Node回归程序通过；mounted专用fixture另核14主机/29视觉Unit与
Scroll既有语义。宿主平台两次早期运行分别因snapshot过期和证据分区漏导航失败；
修正后独立完整重跑952项通过，原失败与最终日志均在verification，不拼接为一轮通过。
加载服务的owned idle reload保留原program revision字节，见[启动收据](verification/service-reload.json)。

本块所有原始失败、截图局限与独审分别保留。修改当前执行脚本不会重写r1/r2来源，
各分区sources保留对应冻结版本；原始官方来源保留字节，个别尾空白在.gitattributes
使用精确路径例外，不修剪原证据。仓内归档不含固件/ROM/compiler二进制。

限定实现提交`3b220560`后已重新fetch/merge `origin/main@f2061759897955e6017d4aa2a41bd5ba962c35b6`，结果Already up to date，工作树干净、实际r3源码哈希保持；见[同步收据](integration.json)。整体UNIT-01仍进行中。

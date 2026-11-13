# main 与常驻服务交付验收

日期：`2026-11-13`。验证类型：**virtual-device validation**。

源码 [`4f09fcba8364e02cb1f60eeec0422e3cae66db54`](https://github.com/m5agent/m5stack-esp-emulator/tree/4f09fcba8364e02cb1f60eeec0422e3cae66db54)
已进入 main，精确提交的 [CI 43414271086](https://github.com/m5agent/m5stack-esp-emulator/actions/runs/43414271086)
通过。主 Device Service 与固件审核使用的 Device Service 已更新，发布后实际
客体、原版应用及清场结果见[交付摘要](summary.json)。本次未提交 Burner。

## 执行身份

| 项目 | 固定身份或范围 |
| --- | --- |
| Xtensa native | `35c35ef2427e121dcd232215339c5219b7e22bc6c63821c92e356c9573d42b26` |
| C6 native | `3679e74e893670a5fd665345addcf00e0e49b9f708c6d4093960f8dc228b0db4` |
| main / CI | [源码与精确 CI 收据](main-ci.json) |
| 部署与保留 | [部署、配置、历史、备份及回滚边界](deployment.json) |
| 共享运行时回归 | [两轮高负载矩阵](../2026-11-13-native-final-regression/README.md)：保留其执行源码、源码等值核对、逐例产物和零重试身份；不改写为在部署后重新执行 |

发布后验收核对实际客体进程的可执行文件 SHA，使用专用 Device Service 会话，
从同一会话获取串口、画面或网络/音频证据。ZIP 在停止前获取；停止后确认终态、
可变 Flash 释放、租约释放和已观察进程退出。公开摘要仅保留哈希和功能结果，
不包含配对码、会话标识、进程号或服务拓扑。

## 发布后结果

| 路径 | 实际观察与范围 | 证据 |
| --- | --- | --- |
| UIFlow2 原版云端配对 | 六款设备共八条路径：CoreS3 网页入口，StickS3、Core2、AtomS3R、StopWatch、Cardputer ADV 的 API 入口，以及 CoreS3/Core2 的独立 API 复验。每条均由本会话 ZIP 的 PCAP 重新解析实际非空 MQTT 配对响应，并查看官方配对画面 | [九条独立会话的帧、固件、ZIP 与网络证明](post9.json) |
| 网页本地编程 | CoreS3 页面显式选择本地编程模式；真实 guest 输出 `CLOUD_MODE_EDITOR_CONTROL_OK`，显示 `Local code OK`，随后关闭所属 Preview 并释放其会话 | [本地编程与清场收据](post9.json) |
| 原生帧方向 | 五份原版 StickS3 固件在最终运行时上分别使用 90/90/270/180/0 度；raw/display 为同一采样，独立全像素比较与逐帧目视均通过 | [五份原 BIN、归一化 Flash、帧与 ZIP](orientation5.json) |
| Cardputer ADV MP3 Player v1.0.0 | 原 SD 库列出 `TEST.MP3`；实际 Enter 输入进入 `NOW PLAYING`，播放进度变化。guest 扬声器 PCM 非静音，157 个窗口匹配 524 Hz 夹具，音调能量占比 0.85159–0.99018 | [原版 dry-run 判定](original-reviews.json) · [输入、SD、PCM、应用字节与帧](original-functional-observations.json) |
| Core2 2048 Game v1.0 | 原版应用执行右/左/上/下两轮，共八次移动；每个棋盘独立满足对应方向的滑动/合并及一个合法新增方块，并经目视复核 | [八次坐标、前后棋盘、方块生成和帧 SHA](original-functional-observations.json) |
| Core2 for AWS 原版显示控制 | 最终 Xtensa 上观察 90.024 秒，1 次启动、无致命错误；30/60/90 秒均显示完整介绍页，时钟与滚动条更新，应用分区字节未改变 | [原 BIN、完整串口、帧与清场](aws-summary.json) |

MP3 与 2048 均使用原保存快照执行 dry-run，原应用分区字节回读相等。
它们的最终判定结合完整 ZIP 串口和独立功能/画面复核，不以“输入已接受”或
“帧有变化”单独判通过。2048 不通过改写棋盘或固件替代滑动；MP3 的声音证据
是 guest PCM，不是物理声学测量。

## 失败历史与结果复用

发布后前三次私有编程验收脚本失败继续保留为 `INFRA_FAILED`：

1. [首次](retained-attempt-01.json)把实际 Preview 创建误按普通 session 追踪，未取得所属会话收据。
2. [第二次](retained-attempt-02.json)未观察到创建请求 intent，虽然已经创建客体，仍不能授予验收通过。
3. [第三次](retained-attempt-03.json)客户端请求上下文不符合 Preview 策略。修复私有 HTTP 客户端后通过；服务安全策略未放宽。

三次均按确切所属 Preview/会话恢复证据、关闭并清场；不是固件失败，也不是
“没有启动客体”。旧失败与原始结果哈希不被后续成功覆盖。
最终九条结果由**第二轮的八条成功云端路径和第四次的成功编程路径**组成。
云端八条未重复执行，其结果行与旧摘要绑定，并再次核对各自独立会话的 ZIP、
网络回包、帧、运行时及清场；没有把前三次失败的编程结果计入最终通过。
AWS 显示控制另保留一次立即失败的宿主路径解析检查，未将其计入 90 秒观察。

## 保留与未完成范围

既有历史和服务配置保持，独立备份已核验；全部本轮测试会话在最终读回时无
活动客体或租约。30 项隔离宿主控制验证了部署/回滚处理，**实际常驻回滚未执行**。
原状态保留在原处，**状态迁移未执行**，不宣称完全脱离既有状态存储。

- #225 在正式交付 Xtensa 上仍为 `PARTIAL`；私有 GPIO 候选没有进入该运行时，不能继承为欢迎页或 BLE HID 通过。
- 原 Launcher 与原 StackChan BIN 不继承修复源码重建版的通过。RFID 原版仍有重启；Tab5 DSI/CSR/USB 模型与 Zigbee 数据面缺口继续开放。
- 原 Atom 厂测远端 HTTP 404 保留；Core2 HamRadio 的远程无线电功能没有因进入仪表页而通过。
- AWS 串口仍有 BMI270 加速度/陀螺仪读取失败，本轮只授予介绍页显示稳定性；触摸滑动、传感器、AWS 云端和无线电功能没有验收。
- 方向复验不扩展镜像/reset 的 guest 证据。其它固件、板型与更长观察时间不能继承这些结果。
- 本轮物理硬件和 browser-WASM 验证均为 `NOT RUN`。原生服务网页使用 native 客体，不是浏览器 WASM 客体；现有 WASM 结果保持其原运行身份。

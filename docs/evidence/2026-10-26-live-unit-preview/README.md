# 多 Unit 同 guest 程序与共享实时预览

日期：2026-10-26。分类：**virtual-device validation**；hardware validation **NOT RUN**。
本批所有执行通过本机8787 Device Service创建可见session；未直接启动QEMU。

## 多 Unit 连续程序

CoreS3、AtomS3R、StickS3、StopWatch分别运行两组被动HUB装配：

| 组 | 原固件自带Unit驱动 | 实际I2C地址 |
| --- | --- | --- |
| sensors | ENV III、NCIR、TVOC | 0x44/0x70、0x5a、0x58 |
| controls | Encoder、8Encoder、Joystick v1.1 | 0x40、0x41、0x52 |

最终八组合 **PASS**，共40次预期程序提交、96次逐leaf输入向量；故意SyntaxError
是负控，不称40个程序都正常完成。[cohort](units/cohort.json)、
[独立审核](units/cohort-audit.json)与[最终guest帧检查](units/native-review.json)。

每例一次 `program_mode=uiflow-live` 初始化，同PID/固件/VM nonce执行finite、
无限循环A、替换B、SyntaxError和恢复。A/B各对三个leaf输入两种不同fixture，
在新的串口byte offset之后核对原驱动值，并独立读实际QOM与每leaf新增I2C流量。
总线扫描必须等于该组地址集合，不接受板载总线泄漏或同地址被动并联。
Encoder两灯、8Encoder九灯分别有A/B输出读回；第九灯通过原驱动的register helper写入，
不冒称高层 `set_led_rgb()` 覆盖第九通道。

CoreS3两组另走真实网页表单输入，程序仍由外部REST接口提交：
[sensors](unit-web/sensors/api/report.json)、[controls](unit-web/controls/api/report.json)。
两例各5次程序/12向量，分别展开为36/56次实际DOM字段POST，guest/QOM和DOM色块匹配。
当前Encoder/8Encoder缺少确认过的通道/角度binding，实际3D LED仍熄灭、旋转仍为零；
不能把此处功能PASS称为完整灯光或机械动画PASS。
[Web边界负控](unit-web/web-boundary-audit.json)固定92次真实POST、168次GET、58份
DOM/model快照及A/B两组非对称颜色；两例的API/DOM通过与3D灯光/旋转未闭合分开记录。

源码从冻结GPIO构造真实 `machine.I2C`，不上传custom驱动。TVOC原构造会重做IAQ
初始化，探针每版本等待16秒；这不是下发延迟。输入是显式虚拟fixture，输出经
guest原驱动和SoC/Unit控制器获得；不证明气体化学、人体生理、电气或真机行为。
装配不支持运行中hotplug；HUB不解决地址冲突，也不任意并联GPIO/UART。

八个guest均在取ZIP后停止，历史和最后帧保留、Flash释放、原PID消失。
本归档共13个独立session（八组合、共享frame一例、PIR/Relay网页两例、多Unit网页两例）；
[当前清理复核](cleanup-summary.json)逐例只读确认stopped、Flash未保留与原PID不存在，
并保存本地服务health与active=0。
每例ZIP中的原始串口bytes、新鲜窗口、revision源码、执行记录、controller状态
均复核；全部公开JSON没有内部 `captured_monotonic`。固件、加载服务与runtime身份
按各报告绑定；实际QEMU均为
`d1ba0063f80f6f8bdeeaa831f0d16ce4004ff3692a2d0587663e121bb93f45ff`。

## 按需共享画面与真实网页

`frame.png?max_age_ms=1..1000` 为QEMU显式启用per-session single-flight样本，
同窗口复用PNG和采集元数据，ETag匹配返回304。默认无参数/零、readiness、
evidence和stop仍直采，不因缓存静默改变取证语义。采集失败不兜底旧成功图。
程序替换、reset、stop和进程身份变化会使缓存/旧在途结果失效。
Tab5/network未准入共享采样；其原有fresh路径保持，Tab5旧GDB并发边界单列
`UNIT-HOST-28`，不能从QMP门禁继承。

[实际frame服务报告](frame-service/report.json)验证：8个并发条件读者复用同一样本、
默认GET仍200直采、A/B实际像素变化、新execution即使像素相同也返回304和新身份、
显式reset后重新运行、先ZIP再stop和带原时间的persisted历史。内部TTL clock
不进入wait JSON、ZIP或历史metadata。样本序号仅为该进程内preview发布序号，
不是guest绘制次数，也不包含所有默认fresh请求。

[真实CoreS3网页](web-service/report.json)另验证PIR/Relay两例：实际DOM输入/程序
提交、guest串口与QOM、PNG像素进入模型display、SyntaxError可见及恢复。
本轮记录32次200与90次304，只是该次运行观察，不是性能基准或SLA。
程序上下文头表示采集期间的当前execution，不证明应用已绘制，也不是帧/Unit/serial
的原子快照。[13组浏览器fixture](web-fixtures/report.json)另覆盖response/blob/解码
晚到、同id换owner、超时/销毁、304及真实3D/generic绘制前guard。
网页每visual最多一个3秒有界请求，慢session不阻塞其它session的下一次轮询。

## 来源、归档与边界

[service-start.json](service-start.json)固定最终加载模块SHA，
[source-snapshot.json](source-snapshot.json)固定runner及产品源码；相应文本快照可重放。
全部ZIP的CRC、成员路径/大小/SHA与binary排除见[zip-index](zip-index.json)。
[校验报告](verification.json)和[原始输出](verification/)保留852项平台测试、
四个validator与11项Unit runner离线检查的实际日志，区分宿主/浏览器fixture、
实际guest与硬件。此前修复前轮次留在本机 `.work`，不混入最终cohort。

Encoder/8Encoder的[固定官方来源与模型binding研究](encoder-binding-research/README.md)
保留17个文本文件和独立来源摘要。原理图证明LED电气链，模型命名证明物理CH位置，
已检查资料尚未连起非均匀颜色的索引到空间位置；Encoder的30 pulses/rev规格与
UIFlow示例58 counts/rev也不能合成一个已确认角度换算。`UNIT-HOST-29`保持OPEN，
整体3D动画为**PARTIAL**；全灯同色的排列不变性不是非均匀通道binding或物理旋转PASS。

Scroll/Roller485本轮完成[固定官方协议审计](../../unit-research/scroll-roller485.md)，
来源下载的成功字节逐一验SHA；保留一个旧产品URL的404记录，不伪装成功。
两款仍只在视觉库，未实现内部controller/功能准入。内部FW与文档版本冲突、
Scroll int32与高层int16差异、Roller真实运动/保护/桥接边界均明确记录。

Preview/Run资源、SSE/后台订阅采样、AIFlow checkpoint/虚拟目标接入、多文件/
二进制`.mpy`/assets同步、保存开机与native/IRQ/thread完整清理仍未完成。
完整执行队列只维护在[项目Backlog](../../project-backlog.md)。

重放（需已准入reference与实际QEMU、运行中的8787服务）：

```bash
PYTHONPATH=platform/tools:tests/units:.work/py312 \
  /opt/miniconda3/bin/python3.12 tests/units/run_live_unit_batch.py \
  --execute --device cores3 --group sensors \
  --expected-runtime-sha256 d1ba0063f80f6f8bdeeaa831f0d16ce4004ff3692a2d0587663e121bb93f45ff \
  --out-dir /tmp/m5-live-sensors
PYTHONPATH=platform/tools:tests/units:.work/py312 \
  /opt/miniconda3/bin/python3.12 tests/units/run_frame_preview.py --execute \
  --expected-runtime-sha256 d1ba0063f80f6f8bdeeaa831f0d16ce4004ff3692a2d0587663e121bb93f45ff \
  --out-dir /tmp/m5-frame-preview
node platform/tests/test_frame_preview.mjs
```

其它主机/controls要分别运行，不能仅从CoreS3继承。8个并发读者的序号断言
要求请求处于同一1000ms窗口，重负载应先核对实际时序，不能将窗口到期误判缓存错误。

# 外部 Agent：UIFlow 实时编程与 Unit 会话

日期：`2026-10-26`。API 契约：`1.41.0`。

实时编程使用“首次启动 UIFlow2 → 同一 guest 连续下发程序 → 读取实际屏幕、
串口及 Unit 状态”的路径。每次改源码调用 `/sessions/{id}/program`，不重刷
固件、不重启虚拟设备。下方原 composer 流程用于首次初始化、完整文件准备和
兼容执行；连续编辑不再重复走这条路径。

先读`GET /devices`的`program_features`：当前入口仅`main.py`，纯字节码`.mpy`
可作依赖，二进制入口和native emitter为false，cleanup仍是interrupt-only。
脚本以新globals执行、初始`__name__='__main__'`，不会替换REPL的
`sys.modules['__main__']`。当前固件普通导入`.mpy`保留模块名，if-main守卫不执行，
不能把“模块导入成功”当作完整UIFlow脚本入口已支持。

默认网页对RGB/Encoder/8Encoder的全灯同色和全灭显示真实3D灯反馈；非对称颜色因物理灯位未确认而标unknown，仍可查看原始电气数组。读取失败会撤回旧颜色，恢复后重新显示。该范围不包含旋转角度，见[证据与限制](evidence/2026-10-26-uniform-led-and-program-capabilities/README.md)。

## 同一设备实时运行程序

推荐直接创建 `program_mode="uiflow-live"` 会话。后端从缓存的 UIFlow2 reference
初始化 UART REPL 一次，自动设置 source pin、串口传输与 bootstrap READY；之后
只调用 `/program`。该模式只准入 `runtime=qemu` 和 CoreS3、AtomS3R、StickS3、
StopWatch，且拒绝同时传入 `firmware_id`、`uiflow_source_sha256` 或应用 ready
条件；不会替换调用者指定的固件。`GET /devices` 的 `program_modes` 声明准入。

```http
POST /api/v1/sessions
Content-Type: application/json

{"device_id":"cores3","program_mode":"uiflow-live","ttl_seconds":600,"units":[{"id":"external1","unit_id":"pir","port_id":"port-a"}]}
```

Unit 端口必须来自该主机 `/units?device_id=...` 的确认接线，源码里的白黄 GPIO
使用返回 session 的冻结 `units[].pins`。网页 Live sessions 可勾选“开启实时编程”，
再在该会话下编辑源码和运行；模式不替代每段应用自己的 READY 与控制器读回。
首次创建的幂等键仍绑定原始请求，不因内部派生固件增加而失效。

兼容路径仍可自行准备固件，再指定 `program_transport="uart-repl"`。这个低层
选项不自动改造 guest 的 REPL 路由。已验证的 S3 reference 的一次性 `boot.py`
如下，配一个 `pass` 的 `main.py` 经下方 composer 初始化，再创建带 Unit 的会话：

```python
from machine import UART
import os
_repl_uart = UART(0, baudrate=115200, timeout=0, timeout_char=0)
os.dupterm(_repl_uart, 0)
_repl_uart.irq(handler=os.dupterm_notify, trigger=UART.IRQ_RX)
_uiflow_run_main = False
print("M5EMU_UART_REPL_READY")
```

该初始化只适用于已准入的 USB-console S3 reference。已有原生 UART REPL 的固件不应
重复安装动态 UART IRQ；其他主机不得直接继承这段路由的验证结论。首次准备
使用原有固件 source pin。之后提交完整单文件源码：

```http
POST /api/v1/sessions/SESSION_ID/program
Content-Type: application/json

{"source":"print('hello from the same guest')\n","expected_execution_id":null,"timeout_seconds":10}
```

读取 `GET /api/v1/sessions/SESSION_ID/program`，下一次提交把
`expected_execution_id` 换成返回的 `program.execution_id`。过期身份或并发传输
返回 409；超时返回明确错误，不自动重新刷机或替换 guest。源码最多 65536
UTF-8 字节，超时配置 1–30 秒，由 guest MicroPython 编译。多文件、纯字节码
`.mpy` 依赖与资源使用下方 `files` 请求；二进制入口和保存开机程序仍待实现。

每次尝试保存独立 `execution_id`、不可变 `revision_id`、源码 SHA、固件 SHA、
PID、串口窗口与执行状态，停止前 evidence ZIP 包含执行记录和 revision 源码。
START 只代表 guest 进入执行；以应用自己的 READY、实际帧和 Unit 读回确认效果。
`execution_mode=same-guest-uart-repl`、`cleanup_mode=interrupt-only` 表示用
Ctrl-C 中断并通过 raw REPL 执行，不保证清空 native 模块、定时器、IRQ 或线程。
遇到不可中断的 native 调用，调用者应按错误显式停止/重建会话。

Unit 仍在创建 session 时接线；运行期间通过现有 `unit-input`、`units`、
`serial`、`frame.png` 观察同一 guest 的控制器与应用效果。当前尚无运行中热插拔、
SSE；Preview编排和1.43托管Web消费者已有CoreS3 PIR/Relay限定验收，AIFlow前后端尚无接入验收结论。QEMU 画面已增加显式
`frame.png?max_age_ms=125` 的按需共享采样与 ETag/304；默认无参数仍直接采新帧。
采集时间/程序身份是该帧的观察上下文，不等于应用 READY 或与 Unit 原子采样。
Preview托管会话必须经`/previews/{id}/input`、`runs`、`renew`、`close`控制，不能
使用下文普通session的旧mutation路由；reset暂不提供。先读取完整
`/program-revisions/{revision_id}/files`再编辑main.py，保留所有MPY/模块/资源；
保存完整新checkpoint后引用Run，详见[API](device-service-api.md#stable-preview-and-asynchronous-runs)与[Web证据](evidence/2026-10-27-preview-web-consumer/README.md)。
可复现的四款主机同 guest/PIR、Relay/屏幕/程序异常恢复探针见
[`run_live_program.py`](../tests/units/run_live_program.py)，以 Device Service
创建可见 session，停止前取证，停止后保留历史。
CoreS3、AtomS3R、StickS3、StopWatch 各自的 PIR/Relay 共8组合、40次程序通过；
CoreS3 另有真实网页创建、输入、程序替换、画面进入模型屏幕和异常恢复证据，见
[直接创建与 Web 验证](evidence/2026-10-26-live-program-web-and-hosts/README.md)。
早期手动 bootstrap 的 AtomS3R 基线保留在
[首轮实时程序证据](evidence/2026-10-26-uiflow-live-program/README.md)。
上述早期结果不外推其它 Unit、任意源码、多文件资源或物理设备。
每session最多256次execution；单源码store默认256、可显式配置1..4096，完整包store独立限256。额度
耗尽返回明确错误，不自动删除历史或重跑未知提交；公共checkpoint响应明确gc_enabled=false。服务重连期间可能丢失串口输出，
原活跃程序保持 unknown，不能仅根据旧 START 恢复 running。

## 先保存完整checkpoint，再引用运行

外部Agent可先`POST /api/v1/program-revisions`，必须显式提交下面三个字段：

```json
{"source_kind":"uiflow2-package","entrypoint":"main.py","files":{
  "main.py":{"encoding":"utf8","data":"from app import value\nprint(value)\n"},
  "app.py":{"encoding":"utf8","data":"value = 42\n"}
}}
```

响应`revision`含不可变`revision_id`、全部文件SHA/大小和`created_at`；`limits`公开实际包配额和`gc_enabled=false`。
相同文件bytes使用utf8/base64均得到同ID，重复POST仍201且保留原created_at。
`GET /api/v1/program-revisions/{revision_id}`核验存储完整性并返回metadata；保存成功还没有运行程序。

在已初始化session中，将返回的ID放入`POST /api/v1/sessions/{id}/program`的`revision_id`，
同时带当前`expected_execution_id`（首次null）和可选1..120秒timeout。该请求只能有这三个字段，
不能混入source/files/entrypoint/source_kind。服务端读取既有完整包并在同VM部署/执行，不再create revision。
未知或旧python-only ID返回404，stale为409，混用/坏ID为400；格式已知不合法/native MPY在分配execution前拒绝。
实际guest的版本/容量/文件完整性仍在原部署路径检查，运行时拒绝可能已经中断旧程序，应查询执行收据。

这为Preview/Run提供不可变输入；旧/program仍同步确认开始。新增协调器契约见[Preview/Run](device-service-api.md#stable-preview-and-asynchronous-runs)，2026-10-27已另行完成CoreS3 PIR/Relay限定验收，不能把旧接口或此子集转授其它guest PASS；它也不提供多租户控制权。
配额仍有界且不自动回收，不能把复用ID当作长期生命周期已经完成。完整包内容和guest边界见下一节。

## 同一 VM 的完整文件包

`GET /devices` 的 `program_source_kinds` 中，`uiflow2-python` 对应原 `source`，
`uiflow2-package` 对应完整文件快照。两种请求互斥，但可在同一 session 连续使用：

```json
{"expected_execution_id":null,"files":{
  "main.py":{"encoding":"utf8","data":"from app import read\nprint(read())\n"},
  "app.py":{"encoding":"utf8","data":"import json\ndef read():\n with open('assets/settings.json') as stream:\n  return json.load(stream)\n"},
  "assets/settings.json":{"encoding":"utf8","data":"{\"enabled\":true}\n"}
},"entrypoint":"main.py","timeout_seconds":120}
```

图片、字体、音频、数据和 `.mpy` 依赖用 `base64` 编码实际文件 bytes；不要把
二进制转换成 UTF-8。每次提交完整集合，删除的模块与旧目录不继续参与导入。
源码/字节码在虚拟设备自己的 MicroPython 与文件系统内运行，不执行 host Python。
`.mpy` 必须是与实际 guest 匹配的纯字节码依赖，使用官方相应 `mpy-cross`；
原生 emitter、伪造头的 native payload 和 `main.mpy` 入口不准入。

总 decoded 上限 1MiB、64文件、单文件256KiB，路径最多192 UTF-8字节/8层；
禁止 boot.py、越界路径和别名冲突。HTTP JSON 上限2MiB，包超时1–120秒/默认120秒；
该预算含真实UART传输、guest哈希读回和应用开始确认，不限制程序最长运行时间。
进度见 `program.deployment`，`activated` 仍不等于应用 READY。重复revision会重验
guest文件及目录；篡改文件或增加额外空目录均拒绝。guest最多保留64个包/暂存目录，
另受实际Flash空闲空间限制；不会暗中删旧包、刷固件或新建guest。

托管模块清理包括 namespace package；native/IRQ/thread仍可能保留，不能当作完整
reset。文件留在专用目录，不改系统boot/main，不保存为开机程序。逐设备与真实
Unit/画面验证范围应查台账，不能从这一请求示例直接继承PASS。
四款准入主机×PIR/Relay的完整文件包、缓存替换/完整性拒绝和恢复已分别验证，见
[八组合文件包证据](evidence/2026-10-26-live-package-and-detent/README.md)。

当前参考固件的 `drawImage(path)` / `drawPng(path)` 存在已复现兼容性问题。
资源可按官方bytes接口使用：

```python
with open("assets/pixel.png", "rb") as stream:
    M5.Display.drawImage(stream.read(), 8, 8)
```

文件路径问题与bytes成功属于不同结论，见
[实际六格实验与固定源码](evidence/2026-10-26-live-package-and-detent/image-path-research/audit.md)。


## 多 Unit 的同设备连续程序

四款准入主机现分别验证了两组被动 HUB 装配：ENV III + NCIR + TVOC，以及
Encoder + 8Encoder + Joystick v1.1。每组创建一次会话，A/B 两段源码在同一
guest 中分别验证三片叶子的输入与原驱动读回；编码器组另核对 LED 输出。
精确固件、串口窗口、控制器与源码见
[多 Unit 与共享预览证据](evidence/2026-10-26-live-unit-preview/README.md)。

CoreS3 传感器组可直接这样装配，后续通过同一个 `/program` 接口连续编程：

```json
{"device_id":"cores3","program_mode":"uiflow-live","units":[
  {"id":"hub1","unit_id":"hub","port_id":"port-a"},
  {"id":"env","unit_id":"env-iii","parent_id":"hub1","port_id":"grove-1"},
  {"id":"ncir","unit_id":"ncir","parent_id":"hub1","port_id":"grove-2"},
  {"id":"tvoc","unit_id":"tvoc","parent_id":"hub1","port_id":"grove-3"}
]}
```

HUB 共享真实 I2C 总线；从返回的冻结白黄 GPIO 创建 `machine.I2C`，使用固件自带
`ENVUnit`、`NCIRUnit`、`TVOCUnit`，不再上传替代驱动。源码与可重放探针见
[`run_live_unit_batch.py`](../tests/units/run_live_unit_batch.py)，使用 `--device`
及 `--group sensors|controls`，只有 `--execute` 才执行。TVOC 每次重新构造会
进入真实 IAQ 初始化，探针等待16秒；这是传感器模型行为，不是代码下发延迟。
温度、压力、气体和编码器输入是显式虚拟 fixture；反馈由 guest 真实驱动经过
控制器读写获得，不代表外部物理测量或传感器完整化学/生理模型。

被动 HUB 不提供地址复用；相同 I2C 地址不能同挂，也不支持任意 GPIO/UART
并联。其它主机先从 `/units?device_id=...` 选其确认端口，不能照搬 CoreS3 的
端口或 GPIO。Roller485仍只有外壳，不在功能附件准入中。

## Scroll 的限定运行时

Scroll通过独立I2C控制器模型准入CoreS3、AtomS3R、StickS3、StopWatch的已确认端口；
`implemented`表示存在实现，`model_completeness=partial`保留完整模型缺口。
逐主机同guest程序证据使用`runtime.program_validation`及`same-guest-scroll-protocol-v1`契约；
它与既有完整host/Web验证类别分开，只有CoreS3条目链接真实Web，其余主机Web为NOT RUN。
装配形态为`{"id":"external1","unit_id":"scroll","port_id":"<确认端口>"}`，
默认地址0x40与Encoder冲突，不能同挂被动HUB。使用固件原`unit.ScrollUnit`与返回的
白黄GPIO；源码生成/实际执行入口见[`run_live_scroll.py`](../tests/units/run_live_scroll.py)。

外部输入是`pressed`和`source-count`，每个`unit-input`请求最多一个字段，必须分别提交；
混合请求400提前拒绝，不会先改按钮再因计数溢出留下部分状态。
创建时`initial`可同时设两字段。`source-count`限定[-32768,32767]且单事件差分≤32767，
对应不回绕的TIM=0x8000+source；逻辑count/increment的int32溢出409拒绝。
counter/reset是guest逻辑操作，不移动物理source，也不转动3D轴。

原驱动getter暴露低16位，`set_rotary_value`仅加Python偏移。原始counter仍是int32；
选择0x50..53时即制作并消耗增量快照，跨STOP/连续程序续读保留旧TX位置。
`led-rgb`为quiescent/latest-value模型读回，可驱动唯一RGB灯；STM32多槽队列、
burst/跨槽partial及LED时序未模拟。没有可靠角度标定，不提供默认count→机械旋转映射。
TIM回绕、bootloader执行/版本、配置持久化和地址0单播均未完成，详见
[官方来源与模型边界](unit-research/scroll-roller485.md)。所有结论均为虚拟验证范围。

## 首次初始化与兼容固件流程

以下给出 Python 源码 → 派生 UIFlow2 固件 → 可见 Device Service session →
Unit 输入/guest 读取/画面 → evidence 的原有完整流程。CoreS3 已有选定的
27 种 Unit 源码场景：25 种原驱动、IR/Buzzer 两种显式 custom 驱动。
下方给出可直接重放的源码 JSON；它们来自多批独立会话，不是原版 27 项
单次全绿运行。下面逐字 Button 与 HUB + ENV III + NCIR 示例也已独立运行。
AtomS3R、StickS3、StopWatch 的 Button/Relay/ENV III 另有九个源码 API
会话通过；随后新增八种 Unit、24 个组合通过，三主机各有11种选定源码场景。
本页共60份场景请求，各批固件与运行时分别绑定；其它组合或任意代码不继承 PASS。当前能力、未完成
门禁和日期化结果分别见[项目当前状态](project-status.md)、
[项目 Backlog](project-backlog.md)、[验证台账](validation-ledger.md)。
完整对象、错误码和安全约束见[API](device-service-api.md)与
[OpenAPI](device-service.openapi.yaml)。

## 1. 查设备与 Unit 准入

以下命令假设服务已在本机 `8787` 运行。需要认证的部署应使用其既有认证配置。
先建立一个保存请求、响应和 evidence 的临时目录：

```bash
M5_API=http://127.0.0.1:8787/api/v1
M5_AGENT_DIR=$(mktemp -d /tmp/m5-agent-unit.XXXXXX)
curl -fsS "$M5_API/devices/cores3" -o "$M5_AGENT_DIR/device.json"
curl -fsS "$M5_API/units?device_id=cores3" -o "$M5_AGENT_DIR/units.json"
```

检查 `backend_ready`、Unit `runtime.hosts`、输入定义和主机 port。源码入口
只接受 `cores3`、`atoms3r`、`sticks3`、`stopwatch` 的已知本地 reference，
不接受任意 MicroPython base。下例固定 **CoreS3 + Button + PORT.A**；
该口 white=GPIO1、yellow=GPIO2。UART0 TX43/RX44 也只属于本 CoreS3 示例，
换主机必须重新核对，不可只改 `device_id`。

Unit 需在创建 session 时接入；当前没有运行中 hotplug。模型存在、
`implemented` 或 HTTP 输入成功，都不能替代 guest 实际使用该驱动的证据。

## 2. 保存 CoreS3 的 main.py

下面初始化 UIFlow2 原驱动，并通过同一 GPIO 控制器读回 active-low 信号。
它沿用仓内 `tests/units/probe/main.py` 的已核调用方式。本次提交生成的新
固件仍需独立运行验证。

```bash
cat > "$M5_AGENT_DIR/main.py" <<'PY'
import time
import M5
from hardware import UART
from machine import Pin
from unit import ButtonUnit

console = UART(0, baudrate=115200, tx=43, rx=44)
M5.begin()
button = ButtonUnit((1, 2), True, type=2)
signal = Pin(1, Pin.IN, Pin.PULL_UP)
screen = M5.Display
screen.setRotation(1)
screen.setBrightness(255)
screen.fillScreen(0xFFFFFF)
screen.setTextColor(0x0282CB, 0xFFFFFF)
screen.setTextSize(2)
screen.setCursor(6, 6)
screen.print("Agent Button")
console.write("AGENT_UNIT_READY\r\n")
previous = None
while True:
    M5.update()
    pressed = signal.value() == 0
    if pressed != previous:
        console.write("AGENT_BUTTON pressed=%d\r\n" % int(pressed))
        screen.fillRect(0, 38, screen.width(), 80, 0xFFFFFF)
        screen.setCursor(6, 42)
        screen.print("PRESSED" if pressed else "RELEASED")
        previous = pressed
    time.sleep_ms(100)
PY
```

没有提交 `boot.py` 时，服务生成 `_uiflow_run_main = True`。如果自行提交
`boot.py`，服务保留其原文；必须自行保证 `main.py` 会运行。

## 3. 提交源码并固定 source 身份

宿主 Python 在此只读 UTF-8 文本并构造 JSON，**不执行 main.py**：

```bash
python3 - "$M5_AGENT_DIR" <<'PY'
import json
from pathlib import Path
import sys
root = Path(sys.argv[1])
payload = {"device_id": "cores3", "files": {"main.py": (root / "main.py").read_text(encoding="utf-8")}}
(root / "source-request.json").write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
PY
curl -fsS -X POST "$M5_API/firmware/uiflow" \
  -H 'Content-Type: application/json' \
  --data-binary "@$M5_AGENT_DIR/source-request.json" \
  -o "$M5_AGENT_DIR/firmware.json"
```

普通 `POST /firmware` 等价请求需要加 `"kind":"uiflow"`；便利入口
`/firmware/uiflow` **禁止** `kind`。两个入口均拒绝未知字段。可以附加
`expected_base_sha256` 固定 reference。必须有根目录 `main.py`；允许嵌套
package；最多 128 个 caller `.py` 文件、每个 256 KiB、合计 1 MiB UTF-8
字节。另外，**整个 HTTP JSON 请求体也限制为 1 MiB（1,048,576 字节）**，
字段名、路径、标点、空白和 JSON 转义均计入；解码后源码合计未超过 1 MiB，
仍可能因请求体过大返回 `413 body_too_large`。HTTP 限额与 helper 源码限额
同时生效；不能承诺任意 1 MiB 源码都能通过 JSON 入口。本页示例远小于
这两个限额。路径和现有 VFS 冲突检查详见 API。

从真实响应生成 session 请求，不手写 firmware/hash：

```bash
python3 - "$M5_AGENT_DIR" <<'PY'
import json
from pathlib import Path
import sys
root = Path(sys.argv[1])
firmware = json.loads((root / "firmware.json").read_text())
source = firmware["source"]
assert firmware["kind"] == source["kind"] == "uiflow"
assert source["artifact_id"] == source["metadata"]["source_sha256"]
request = {
    "device_id": "cores3", "runtime": "qemu",
    "firmware_id": firmware["firmware_id"],
    "uiflow_source_sha256": source["metadata"]["source_sha256"],
    "ready_marker": "AGENT_UNIT_READY", "ready_timeout_seconds": 120,
    "ttl_seconds": 300,
    "units": [{"id": "button1", "unit_id": "button", "port_id": "port-a"}],
}
(root / "session-request.json").write_text(json.dumps(request), encoding="utf-8")
PY
curl -fsS -X POST "$M5_API/sessions" \
  -H 'Content-Type: application/json' \
  --data-binary "@$M5_AGENT_DIR/session-request.json" \
  -o "$M5_AGENT_DIR/session-created.json"
M5_SESSION_ID=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["session_id"])' \
  "$M5_AGENT_DIR/session-created.json")
curl -fsS -X POST "$M5_API/sessions/$M5_SESSION_ID/wait" \
  -H 'Content-Type: application/json' \
  --data '{"ready_marker":"AGENT_UNIT_READY","timeout_seconds":120}' \
  -o "$M5_AGENT_DIR/session-ready.json"
```

`uiflow_source_sha256` 是源码身份 pin：UIFlow firmware 缺此字段返回
`400 uiflow_source_binding_required`；不匹配或给非 UIFlow 固件附此 pin 返回
`409 uiflow_source_binding_mismatch`，不会启动 guest。相同 image 字节可能由
不同 caller-source 声明产生，因此不能只固定 `firmware_id`。遇到竞态冲突时
重新 compose 并使用新响应，不能去掉 pin。

打开产品的 [Live sessions](http://127.0.0.1:8787/platform/web/sessions.html)，
按返回的 session ID 选择对应会话。观察原生 framebuffer、串口、Unit 和输入；
源码提交成功与会话出现在列表中并不代表 ready marker 已出现。

## 4. 写入 Button，核对新串口与画面

下面宿主脚本为每次输入先保存串口 cursor，要求**输入之后的新串口**出现
对应值，再保存 live Unit 状态和 frame。它只调用 Device Service API，不运行
guest 源码：

```bash
python3 - "$M5_API" "$M5_SESSION_ID" "$M5_AGENT_DIR" <<'PY'
import json
from pathlib import Path
import sys
import time
from urllib.request import Request, urlopen
api, session_id, output_dir = sys.argv[1:]
root = Path(output_dir)
base = api + "/sessions/" + session_id

def call(path, payload=None):
    body = None if payload is None else json.dumps(payload).encode()
    request = Request(base + path, data=body, headers={"Content-Type": "application/json"})
    with urlopen(request, timeout=20) as response:
        return json.load(response)

for pressed in (True, False):
    label = "pressed" if pressed else "released"
    before = call("/serial?offset=0&limit=262144")
    offset = before["next_offset"]
    response = call("/unit-input", {"id": "button1", "values": {"pressed": pressed}})
    (root / (label + "-input.json")).write_text(json.dumps(response), encoding="utf-8")
    marker = "AGENT_BUTTON pressed=%d" % int(pressed)
    fresh = ""
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        chunk = call("/serial?offset=%d" % offset)
        offset = chunk["next_offset"]
        fresh += chunk["data"]
        if marker in fresh:
            break
        time.sleep(0.2)
    (root / (label + "-serial.txt")).write_text(fresh, encoding="utf-8")
    if marker not in fresh:
        raise RuntimeError("fresh guest marker missing: " + marker)
    (root / (label + "-units.json")).write_text(json.dumps(call("/units")), encoding="utf-8")
    with urlopen(base + "/frame.png", timeout=20) as response:
        (root / (label + "-frame.png")).write_bytes(response.read())
PY
```

核对新串口分别为 `pressed=1`、`pressed=0`，画面分别为 `PRESSED`、
`RELEASED`，并检查 `/units` 的 controller 属性/计数。按键控制测试证明的是
本固件在该 GPIO 模型上读取输入；HTTP ACK/QOM 接受值单独只证明输入已注入。
不要用宿主脚本生成的标记冒充 guest 串口，也不要复用旧串口命中。

## 5. 停止前取证，保留历史

```bash
curl -fsS "$M5_API/sessions/$M5_SESSION_ID" -o "$M5_AGENT_DIR/session-final.json"
curl -fsS "$M5_API/sessions/$M5_SESSION_ID/serial?offset=0&limit=262144" \
  -o "$M5_AGENT_DIR/serial.json"
curl -fsS "$M5_API/sessions/$M5_SESSION_ID/units" -o "$M5_AGENT_DIR/unit-state.json"
curl -fsS "$M5_API/sessions/$M5_SESSION_ID/device-state" -o "$M5_AGENT_DIR/device-state.json"
curl -fsS "$M5_API/sessions/$M5_SESSION_ID/frame.png" -o "$M5_AGENT_DIR/frame.png"
curl -fsS "$M5_API/sessions/$M5_SESSION_ID/evidence" -o "$M5_AGENT_DIR/evidence.zip"
curl -fsS -X DELETE "$M5_API/sessions/$M5_SESSION_ID?purge=0" \
  -o "$M5_AGENT_DIR/session-stopped.json"
```

先检查 ZIP 可打开、请求/响应对应同一 session，再归档文件和 SHA256。若输入或
等待失败，仍应先取诊断 evidence 再停止。默认释放完整 mutable Flash，保留
metadata、serial、最后帧；仅在需要 Flash snapshot/diff/raw 时在停止参数加
`retain_flash=1`。不要用 `purge=1` 清掉本轮历史。

`firmware/uiflow-source.json` 保存 hash provenance；`units/runtime.json`、
`units/state.json`、`units/contract.json` 保存执行定义、读数与冻结契约。
源码正文保留在服务内部 CAS；`GET /artifacts/{id}` 只返回 metadata，没有
公开 raw 下载入口。公开 session/ZIP 中的 provenance 不包含代码正文。

要区分四种身份：

| 字段 | 表示什么 |
| --- | --- |
| `source.metadata.base_sha256` | 原始缓存 UIFlow2 reference |
| `source.artifact_id`、`source.metadata.source_sha256`、session `artifact_sha256`/`source_artifacts[0]` | 规范化 caller-files JSON；不包含自动生成的 boot.py |
| `firmware_id`、`firmware_sha256`、`source.metadata.firmware_sha256` | 派生的完整 Flash 镜像 |
| session Flash/snapshot/diff hash | 运行中可变 Flash 的对应时刻状态 |

`effective_source_sha256` 还纳入 generated 文件；单文件 hash、`origin`、实际
VFS 读回、保留检查和工具链在 metadata。`COMPOSED_NOT_EXECUTED` 描述打包
步骤，不因后来的 session 测试改写。运行结论需另存真实 session/evidence。

## 多 Unit：创建前配置 HUB 和两个 I2C leaf

被动 HUB 不是 PAHUB，不切换 I2C 地址。以下拓扑是独立于 Button 示例的
**另一次 session**，两路 I2C leaf 共享 CoreS3 PORT.A 的 SCL1/SDA2：

```json
{
  "units": [
    {"id":"hub1","unit_id":"hub","port_id":"port-a"},
    {"id":"env1","unit_id":"env-iii","parent_id":"hub1","port_id":"grove-1"},
    {"id":"ncir1","unit_id":"ncir","parent_id":"hub1","port_id":"grove-2"}
  ]
}
```

把 `main.py` 改为下面程序，重新执行第 3 步的 compose，生成新的 firmware 和
source pin，并在发送 session 请求前把 `units` 替换为上述数组。该组合已在
本指南逐字源码的新 session 中通过：两个 leaf 的新串口、各自 I2C 计数、
网页输入、屏幕与取证均核对；HUB 为被动接线，不虚构自己的总线事务。

```python
import time
import M5
from hardware import UART
from machine import I2C, Pin
from unit import ENVUnit, NCIRUnit

console = UART(0, baudrate=115200, tx=43, rx=44)
M5.begin()
bus = I2C(0, scl=Pin(1), sda=Pin(2), freq=100000)
env = ENVUnit(i2c=bus, type=3)
ncir = NCIRUnit(bus)
screen = M5.Display
screen.setRotation(1)
screen.fillScreen(0xFFFFFF)
screen.setTextColor(0x0282CB, 0xFFFFFF)
screen.setTextSize(2)
console.write("AGENT_UNIT_READY\r\n")
while True:
    M5.update()
    temperature = env.read_temperature()
    humidity = env.read_humidity()
    pressure_pa = env.read_pressure() * 100
    ambient = ncir.get_ambient_temperature()
    target = ncir.get_object_temperature()
    console.write("AGENT_ENV %.2f %.2f %.2f\r\n" % (temperature, humidity, pressure_pa))
    console.write("AGENT_NCIR %.2f %.2f\r\n" % (ambient, target))
    screen.fillRect(0, 0, screen.width(), 180, 0xFFFFFF)
    screen.setCursor(6, 6)
    screen.print("T %.1f C\nRH %.1f %%\nP %.1f Pa\nIR %.1f C" % (temperature, humidity, pressure_pa, target))
    time.sleep_ms(500)
```

分别调用同一 session 的 `/unit-input`：

```json
{"id":"env1","values":{"temperature-c":28.5,"humidity-pct":61.0,"pressure-pa":100800}}
```

```json
{"id":"ncir1","values":{"ambient-c":24.0,"object-c":37.5}}
```

仍需按第 4 步的方法在输入前记录 serial cursor，核对之后的新
`AGENT_ENV`/`AGENT_NCIR`、两个 leaf 的总线计数和同 session frame；数值允许
芯片转换精度范围，不要求字符串逐字等于输入。`ENVUnit.read_pressure()`
返回 hPa，此处乘 100 对应 API 的 Pa。主机附件选择不会自动初始化 guest
驱动；程序必须实际创建这两个 Unit 并持续读取。重复 I2C 地址、拓扑循环、
占用同一个 slot 或未建模的并联 GPIO drive 均应拒绝。不要把 Button 和这些
I2C leaf 并接到同一被动 HUB。

## 已验证的 27 种源码场景

本表均为 CoreS3。以下每个链接都是仓内冻结的 `source-request.json`，包含 caller Python 文件，
可提交到 `POST /firmware/uiflow`。同目录 `prepared.json` 保存主机、
`ready_marker`、`attachments` 和初始 fixture。附件必须整体保留：例如 Thermal
依赖明确的 raw fixture，不能删掉 `initial` 后把该场景仍称为功能验收。
旧 `session-request.json` 的 `firmware_id` 只属于历史执行；重放必须使用
**本次 compose 响应**的 `firmware_id` 与 source pin。

| Unit / 场景 | 冻结源码请求 | 本次选定路径 |
| --- | --- | --- |
| Button | [JSON](evidence/2026-10-26-unit-source-api-29d8/batches/five-r1/button/source-request.json) | 原驱动 |
| Relay | [JSON](evidence/2026-10-26-unit-source-api-29d8/batches/five-r1/relay/source-request.json) | 原驱动 |
| ENV III | [JSON](evidence/2026-10-26-unit-source-api-29d8/batches/five-r1/env-iii/source-request.json) | 原驱动 |
| RGB | [JSON](evidence/2026-10-26-unit-source-api-29d8/batches/five-r1/rgb/source-request.json) | 原驱动；含短帧负控 |
| Encoder | [JSON](evidence/2026-10-26-unit-source-api-29d8/batches/five-r1/encoder/source-request.json) | 原驱动 |
| Color | [JSON](evidence/2026-10-26-unit-source-api-expanded-29d8/batches/sensors-r1/color/source-request.json) | 原驱动 |
| ToF | [JSON](evidence/2026-10-26-unit-source-api-expanded-29d8/batches/sensors-r1/tof/source-request.json) | 原驱动 |
| NCIR | [JSON](evidence/2026-10-26-unit-source-api-expanded-29d8/batches/sensors-r1/ncir/source-request.json) | 原驱动 |
| Heart | [JSON](evidence/2026-10-26-unit-source-api-expanded-29d8/batches/sensors-r1/heart/source-request.json) | 原驱动；raw IR/red/FIFO |
| TVOC | [JSON](evidence/2026-10-26-unit-source-api-expanded-29d8/batches/sensors-r1/tvoc/source-request.json) | 原驱动 |
| Ultrasonic-I2C | [JSON](evidence/2026-10-26-unit-source-api-expanded-29d8/batches/sensors-r1/ultrasonic-i2c/source-request.json) | 原驱动 |
| Thermal | [JSON](evidence/2026-10-26-unit-source-api-expanded-29d8/batches/sensors-r1/thermal/source-request.json) | 原驱动；显式 raw fixture |
| PIR | [JSON](evidence/2026-10-26-unit-source-api-expanded-29d8/batches/io-default9-r1/pir/source-request.json) | 原驱动 |
| Dual Button | [JSON](evidence/2026-10-26-unit-source-api-expanded-29d8/batches/io-default9-r1/dual-button/source-request.json) | 原驱动 |
| LIMIT | [JSON](evidence/2026-10-26-unit-source-api-expanded-29d8/batches/io-default9-r1/limit/source-request.json) | 原驱动 |
| Key | [JSON](evidence/2026-10-26-unit-source-api-expanded-29d8/batches/io-default9-r1/key/source-request.json) | 原驱动 |
| Angle | [JSON](evidence/2026-10-26-unit-source-api-expanded-29d8/batches/io-default9-r1/angle/source-request.json) | 原驱动 |
| Light | [JSON](evidence/2026-10-26-unit-source-api-expanded-29d8/batches/io-default9-r1/light/source-request.json) | 原驱动 |
| Fan | [JSON](evidence/2026-10-26-unit-source-api-expanded-29d8/batches/io-default9-r1/fan/source-request.json) | 原驱动；三阶段控制器，动画限 100% duty 观测段 |
| RS485 | [JSON](evidence/2026-10-26-unit-source-api-expanded-29d8/batches/io-default9-r1/rs485/source-request.json) | 原驱动 |
| HUB + ENV III + NCIR + TVOC | [JSON](evidence/2026-10-26-unit-source-api-expanded-29d8/batches/io-default9-r1/hub/source-request.json) | 被动 HUB、三个独立 I2C leaf |
| Joystick v1.1 | [JSON](evidence/2026-10-26-unit-source-api-expanded-29d8/batches/controls-v2-r1/joystick-v11/source-request.json) | 原驱动；display-only 调整 |
| 8Encoder | [JSON](evidence/2026-10-26-unit-source-api-expanded-29d8/batches/controls-v2-r1/8encoder/source-request.json) | 原驱动；display-only 调整 |
| CardKB | [JSON](evidence/2026-10-26-unit-source-api-expanded-29d8/batches/controls-v2-r1/cardkb/source-request.json) | 原驱动；display-only 调整 |
| RFID2 | [JSON](evidence/2026-10-26-unit-source-api-expanded-29d8/batches/controls-v2-r1/rfid2/source-request.json) | 原驱动；display-only 调整 |
| IR | [JSON](evidence/2026-10-26-unit-source-api-expanded-29d8/batches/custom2-r1/ir/source-request.json) | 显式 custom callback-root |
| Buzzer | [JSON](evidence/2026-10-26-unit-source-api-expanded-29d8/batches/custom2-r1/buzzer/source-request.json) | 显式 custom callback-arity |

例如，在仓库中选 Color 场景，沿用第 1 步的环境变量和输出目录：

```bash
M5_REPO_ROOT=$(git rev-parse --show-toplevel)
M5_CASE_DIR="$M5_REPO_ROOT/docs/evidence/2026-10-26-unit-source-api-expanded-29d8/batches/sensors-r1/color"
curl -fsS -X POST "$M5_API/firmware/uiflow" \
  -H 'Content-Type: application/json' \
  --data-binary "@$M5_CASE_DIR/source-request.json" \
  -o "$M5_AGENT_DIR/firmware.json"
python3 - "$M5_CASE_DIR" "$M5_AGENT_DIR" <<'PY'
import json
from pathlib import Path
import sys
case, output = map(Path, sys.argv[1:])
prepared = json.loads((case / "prepared.json").read_text(encoding="utf-8"))
firmware = json.loads((output / "firmware.json").read_text(encoding="utf-8"))
source = firmware["source"]
assert firmware["kind"] == source["kind"] == "uiflow"
assert source["artifact_id"] == source["metadata"]["source_sha256"]
assert source["metadata"]["source_sha256"] == prepared["source_cas_sha256"]
request = {
    "device_id": prepared["device_id"], "runtime": prepared["runtime"],
    "firmware_id": firmware["firmware_id"],
    "uiflow_source_sha256": source["metadata"]["source_sha256"],
    "ready_marker": prepared["ready_marker"], "ready_timeout_seconds": 180,
    "ttl_seconds": 900, "units": prepared["attachments"],
}
(output / "session-request.json").write_text(json.dumps(request), encoding="utf-8")
PY
curl -fsS -X POST "$M5_API/sessions" \
  -H 'Content-Type: application/json' \
  --data-binary "@$M5_AGENT_DIR/session-request.json" \
  -o "$M5_AGENT_DIR/session-created.json"
```

随后按第 3–5 步从新响应读取 session ID、等待该场景的 ready marker，观察
Live sessions，使用 `/units` 声明的输入并核对新串口、控制器与实际帧，停止前
取 ZIP。冻结请求固定 reference SHA；若服务 reference 已变，应重新审查与
验证场景，不能去掉身份检查后沿用旧 PASS。附件/源码成功重放只是新一次
执行的起点，完整验收还需重复各场景的输入、负控与输出断言。

## 三主机：Button、Relay、ENV III

AtomS3R、StickS3、StopWatch 各自的三个场景已通过新源码 compose 和独立可见
session。下表可复用上节的 JSON 重放步骤；把 `M5_CASE_DIR` 改为相应请求所在
目录，附件仍从同目录 `prepared.json` 读取，使用本次响应的 firmware/source
pin。这些主机的入口使用原 `host_probe` 四个 Python 文件和显式生成的主机
配置，运行时调用各 reference 固件内原驱动，不上传或替换驱动。

| 主机 | 主 Grove `port_id`；white/yellow GPIO | Button 源码 | Relay 源码 | ENV III 源码 |
| --- | --- | --- | --- | --- |
| AtomS3R | `custom`；1/2 | [JSON](evidence/2026-10-26-unit-source-hosts-29d8/batches/post-sync-r1/atoms3r/button/source-request.json) | [JSON](evidence/2026-10-26-unit-source-hosts-29d8/batches/post-sync-r1/atoms3r/relay/source-request.json) | [JSON](evidence/2026-10-26-unit-source-hosts-29d8/batches/post-sync-r1/atoms3r/env-iii/source-request.json) |
| StickS3 | `custom`；10/9 | [JSON](evidence/2026-10-26-unit-source-hosts-29d8/batches/post-sync-r1/sticks3/button/source-request.json) | [JSON](evidence/2026-10-26-unit-source-hosts-29d8/batches/post-sync-r1/sticks3/relay/source-request.json) | [JSON](evidence/2026-10-26-unit-source-hosts-29d8/batches/post-sync-r1/sticks3/env-iii/source-request.json) |
| StopWatch | `port-a`；11/10 | [JSON](evidence/2026-10-26-unit-source-hosts-29d8/batches/post-sync-r1/stopwatch/button/source-request.json) | [JSON](evidence/2026-10-26-unit-source-hosts-29d8/batches/post-sync-r1/stopwatch/relay/source-request.json) | [JSON](evidence/2026-10-26-unit-source-hosts-29d8/batches/post-sync-r1/stopwatch/env-iii/source-request.json) |

端口、内部 I2C、reference 和显示参数均按主机固定，不能只替换 CoreS3 的
`device_id`。原探针保留 BMI270 初始化前后及外部操作后的读数、ENV 外部精确
scan/两个输入向量、Button 四次 GPIO/IRQ 边沿和 Relay 双输出。原生 frame
分别为 128×128、135×240、466×466；StopWatch 的 guest canvas 仍为
468×468，不能据此把原生 PNG 判错。该批验证非空帧和尺寸，不把这些检查等同
于所有显示状态的可读性或跨请求原子快照。该九组合不转授其它 Unit，后续
八种见下节；此前的 BIN 路径结果也不自动转授。详见
[九组合证据](evidence/2026-10-26-unit-source-hosts-29d8/README.md)。

## 三主机：新增八种 Unit

以下24个实际源码 API 会话已通过，均为原驱动；范例沿用上述 JSON 重放步骤，
主机接线从同目录 `prepared.json` 读取，使用新 compose 响应创建带 Unit 附件的
session。附件在创建时固定，运行中 hotplug 尚未实现。Fan三例在同步前的
`cba4e3c` 上执行，其余21例在PWM块提交 `0a6a9a2` 并fetch/merge之后全新准备；
两批481项源码依赖清单和字节哈希相同，运行时均为 `d1ba`、worker gen12。

| Unit | AtomS3R 源码 | StickS3 源码 | StopWatch 源码 |
| --- | --- | --- | --- |
| PIR | [JSON](evidence/2026-10-26-unit-source-host-io-d1ba/batches/rest-r1/atoms3r/pir/source-request.json) | [JSON](evidence/2026-10-26-unit-source-host-io-d1ba/batches/rest-r1/sticks3/pir/source-request.json) | [JSON](evidence/2026-10-26-unit-source-host-io-d1ba/batches/rest-r1/stopwatch/pir/source-request.json) |
| Dual Button | [JSON](evidence/2026-10-26-unit-source-host-io-d1ba/batches/rest-r1/atoms3r/dual-button/source-request.json) | [JSON](evidence/2026-10-26-unit-source-host-io-d1ba/batches/rest-r1/sticks3/dual-button/source-request.json) | [JSON](evidence/2026-10-26-unit-source-host-io-d1ba/batches/rest-r1/stopwatch/dual-button/source-request.json) |
| LIMIT | [JSON](evidence/2026-10-26-unit-source-host-io-d1ba/batches/rest-r1/atoms3r/limit/source-request.json) | [JSON](evidence/2026-10-26-unit-source-host-io-d1ba/batches/rest-r1/sticks3/limit/source-request.json) | [JSON](evidence/2026-10-26-unit-source-host-io-d1ba/batches/rest-r1/stopwatch/limit/source-request.json) |
| Key | [JSON](evidence/2026-10-26-unit-source-host-io-d1ba/batches/rest-r1/atoms3r/key/source-request.json) | [JSON](evidence/2026-10-26-unit-source-host-io-d1ba/batches/rest-r1/sticks3/key/source-request.json) | [JSON](evidence/2026-10-26-unit-source-host-io-d1ba/batches/rest-r1/stopwatch/key/source-request.json) |
| RGB | [JSON](evidence/2026-10-26-unit-source-host-io-d1ba/batches/rest-r1/atoms3r/rgb/source-request.json) | [JSON](evidence/2026-10-26-unit-source-host-io-d1ba/batches/rest-r1/sticks3/rgb/source-request.json) | [JSON](evidence/2026-10-26-unit-source-host-io-d1ba/batches/rest-r1/stopwatch/rgb/source-request.json) |
| Fan | [JSON](evidence/2026-10-26-unit-source-host-io-d1ba/batches/fan-r1/atoms3r/fan/source-request.json) | [JSON](evidence/2026-10-26-unit-source-host-io-d1ba/batches/fan-r1/sticks3/fan/source-request.json) | [JSON](evidence/2026-10-26-unit-source-host-io-d1ba/batches/fan-r1/stopwatch/fan/source-request.json) |
| RS485 | [JSON](evidence/2026-10-26-unit-source-host-io-d1ba/batches/rest-r1/atoms3r/rs485/source-request.json) | [JSON](evidence/2026-10-26-unit-source-host-io-d1ba/batches/rest-r1/sticks3/rs485/source-request.json) | [JSON](evidence/2026-10-26-unit-source-host-io-d1ba/batches/rest-r1/stopwatch/rs485/source-request.json) |
| HUB + ENV III + NCIR + TVOC | [JSON](evidence/2026-10-26-unit-source-host-io-d1ba/batches/rest-r1/atoms3r/hub/source-request.json) | [JSON](evidence/2026-10-26-unit-source-host-io-d1ba/batches/rest-r1/sticks3/hub/source-request.json) | [JSON](evidence/2026-10-26-unit-source-host-io-d1ba/batches/rest-r1/stopwatch/hub/source-request.json) |

每份请求保留原 host IO 探针、原13个driver Python文件和主机配置，共19个caller
文件；初始化、负控、完整原控制器断言、BMI270内部总线前后/loop与native显示
合同均保留。PIR/按钮/Limit/Key有新鲜GPIO输入，RGB含full→短帧负控→full的
真实RMT路径，Fan保留三阶段LEDC，RS485保留UART FIFO与超限负控，HUB有
三个独立I2C leaf。RGB/Fan为output-only，实际网页零正向input POST。

逐例源码CAS/固件/直接PID、真实DOM/HTTP、输入前与下一输入前的串口边界、
Unit QOM、停止前ZIP和停止后history/最后帧/Flash释放/进程退出均绑定。
显示可读性限实际看过的捕获帧；三主机的HUB长数字会跨行，numeric-token
连续性为PARTIAL，完整数值另由UART/QOM核对。Fan动画不外推其它duty或物理转速。ADC准入、
Thermal fixture、原IR/Buzzer、其它Unit/主机和任意新固件不继承。
详见[24组合与完整边界](evidence/2026-10-26-unit-source-host-io-d1ba/README.md)。

## 结果边界

本页示例的 ready、输入、帧和 ZIP 必须来自新源码构建的同一个 guest。源码
打包/读回成功不会自动成为四主机 functional PASS。上述选定场景合并首轮
八个会话与本轮二十五个会话的证据；新轮有 22 个功能 PASS、一个 Thermal
missing-fixture 负控 PASS、原 IR 的待审观察和原 Buzzer FAIL。具体分层见
[首批](evidence/2026-10-26-unit-source-api-29d8/README.md)与
[扩展批次](evidence/2026-10-26-unit-source-api-expanded-29d8/README.md)。

- CoreS3 选定27种场景与三主机各11种选定场景有实际源码API执行证据，
  具体固件/主机/输入/运行时按批次单列；其它组合不继承。CoreS3 控制四例使用
  `controls-probe-cores3-native-display-v1`，原驱动和控制断言
  不改，只做可逆的 display-only 调整；显示可读性限实际捕获帧。Heart 不证明
  BPM/SpO2，Fan 动画不外推其它 duty、比例或物理转速。
- 原 IR 本轮为 `REVIEW_REQUIRED / protocol_status=PASS`，独审结论
  `OBSERVED_PROTOCOL_PASS_RISK_OPEN`，历史 GC 风险仍 OPEN；原 Buzzer
  自然 timer-zero FAIL，手动 OFF 后的零不补自然停止 PASS。旧 IO harness
  对输出类 Buzzer 误要求输入 POST，附加 `browser_error` 属 harness 误分类，
  不代表产品浏览器故障。两种 custom 场景单列，不升级原驱动结论。
- PWM 初始化 route 已由 `0038` 修复：同固件无后续 setter 的新旧运行时
  八窗对照通过，新 `d1ba` 独立完整矩阵 67/67 case、274/274 check PASS。
  只覆盖实际采样窗口，原 Buzzer.once、完整 PWM 周期/latch/fade 与偶发
  Core2 marker 根因仍分别开放；完整 ROM/C6 起始 freeze 和一个摘要命令字段
  有明确取证限制，详见[PWM归档](evidence/2026-10-26-unit-pwm-route-d1ba/README.md)。
  旧66/67不改写，单例复测不拼接。硬件验证为 **NOT RUN**；虚拟数值与显示
  不证明物理电气、温度、红外、声学或 RF 行为。

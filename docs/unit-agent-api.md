# 外部 Agent：UIFlow 源码到 Unit 会话

日期：`2026-10-26`。API 契约：`1.35.0`。

本页给出 Python 源码 → 派生 UIFlow2 固件 → 可见 Device Service session →
Unit 输入/guest 读取/画面 → evidence 的最短流程。下面逐字源码已在两个独立
CoreS3 可见 session 实际通过：Button，以及 HUB + ENV III + NCIR。另有
Button/Relay/ENV III/RGB/Encoder 五例源码 API 批次通过；范围与原始输入见
[本轮证据](evidence/2026-10-26-unit-source-api-29d8/README.md)。这不继承为
其它主机或任意代码的 PASS。当前能力、未完成
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

## 结果边界

本页示例的 ready、输入、帧和 ZIP 必须来自新源码构建的同一个 guest。源码
打包/读回成功不会自动成为四主机 functional PASS，也不关闭原 Buzzer/IR
驱动、PWM 初始化或共享 runtime 的完整回归门禁。硬件验证为 **NOT RUN**；
虚拟控制器输入、数值、显示不证明物理电气、温度、红外、声学或 RF 行为。

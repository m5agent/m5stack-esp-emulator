# Unit 第十二批 c 类 4 款 guest 证据（batch12c）

日期：`2026-11-03`。范围：`8servos2-chain`（U223）、`chainbus`（U212）、
`cat1-cn`（U204）、`mini-imu-pro`（U171）。**4/4 PASS**；全部仍是
virtual-device validation，不是硬件确认。

## 关键点

| 项 | 值 |
| --- | --- |
| QEMU | canonical 75f1d24 + 39 层链（0120–0159）+ `0161-unit-batch12c-chain-frames` |
| 运行时二进制 SHA-256 | `feec1b119051b5d7f101ca124b686c4cba6d62daf572e90240516d9f34caed25` |
| Device Service | 独立 `127.0.0.1:8823`（`.work/unit-batch12c-service.port`），独立 state/token、host-image；未触碰 8787/8799/8801/8802/8803/8831 |
| 参考固件 | cores3 `platform/.cache/firmware/cores3/uiflow2.bin` |

## 0160 证据修复

`0161-unit-batch12c-chain-frames.patch`（base 39 层链 through 0159）修复 Chain
AA55 帧解析：协议 length = data_len + 3，因此**无数据的 get/enumeration/
heartbeat 请求 length=3 是合法的**；旧模型要求 length≥4，并在遇到这种帧时
**清空整个接收缓冲**，导致 guest 连续发帧时只处理前三个状态命令。改为接受
length≥3 后，8Servos2-Chain/ChainBus 的全部请求均被解析。
（patch sha256 `b9d07d03619781a1df957622944f235b4ab29be741f65363e4f0cd2f5d86ecce`）

## 结果

| Unit | guest 路径 | QOM/证据 |
| --- | --- | --- |
| `8servos2-chain` | raw UART 115200 AA55 Chain 帧（driver-gap）：set mode/angle/RGB + get modes/angles/ADC/RGB/current | channel-modes[0]=4、servo-angles[0]=90、adc-values=初始 8 值、rgb[0]=0x112233、current=123.5 mA、frames≥5；设备类型 0x000C |
| `chainbus` | raw UART AA55 ChainBus 帧（driver-gap）：device type/I2C forward fail-closed/brightness/GPIO/ADC/work status | chain-uid 回显、gpio-levels=[true,false]、adc-values=[111,222,333,444]、I2C forward 响应 status=0、frames≥5；设备类型 0x0006 |
| `cat1-cn` | raw UART 115200 ML307R-DL AT（driver-gap）：AT/ATE0/CPIN?/CREG?/CSQ/CGSN/CGMM | +CPIN READY、+CREG 0,1、+CSQ 99,99、CGSN 862…、CGMM ML307R-DL；QOM tx-hex 含 AT/ATE0、frames≥5 |
| `mini-imu-pro` | frozen generic BMI270（0x68，accel/gyro/temp）+ BMP280（0x76，pressure） | guest accel=(0.125,-0.0625,0.03125)、gyro≈(100.09765,-50.048824,25.024412)、temp=25.0、BMP280≈100499.97 Pa；QOM 与 fixture/ whoami=0x24 一致 |

## 边界

- Chain×2：只有 raw UART AA55 字节/帧层；级联拓扑、舵机 PWM/机械、9-24V
  供电、INA199 电流电气、I2C 转发（fail-closed status 0）均 NOT RUN；
  无官方 Unit 驱动（driver-gap）；PORT.C 用 cores3 PORT.A harness。
- `cat1-cn`：只断言 AT 字节层；蜂窝 RF/SIM/PDP/网络/TLS/HTTP/MQTT 与身份
  字符串真实性 NOT RUN；PORT.C harness。
- `mini-imu-pro`：只断言 BMI270 0x68 fixture 子集 + BMP280 0x76 压力；BMM150
  aux/init blob/量程/运动/磁力/姿态物理 NOT RUN；magnetic QOM fixture 不作
  guest 断言；0x68/0x76 与 mini-imu/env 系冲突。
- 所有结果绑定本固件 SHA、运行时二进制和 cores3；不能转授硬件或其他固件。
- 可选 `mini-bps-v11`：仍是 planned 且无 QEMU 模型，guest raw I2C scan 无法
  被 Unit session 准入；QMP6988 0x56 vs 0x70 二义未决，需要模型/数据面决策，
  本批未强行建模型。

## 复现

```bash
M5_SERVICE_FLASH_MODE=host-image \
M5_QEMU_XTENSA="$PWD/.work/M5StopWatch-QEMU/build/qemu/build/qemu-system-xtensa" \
M5_QEMU_XTENSA_ROM_DIR="$PWD/.work/M5StopWatch-QEMU/build/qemu/pc-bios" \
  PYTHONPATH=platform/tools python3.12 platform/tools/serve.py 8823 \
  --bind 127.0.0.1 --state-dir .work/unit-batch12c-service \
  --api-token "$(cat .work/unit-batch12c-service.token)"

export M5_SERVICE_API_TOKEN="$(cat .work/unit-batch12c-service.token)"
PYTHONPATH=platform/tools python3.12 tests/units/run_batch12c_cases.py \
  --api-url http://127.0.0.1:8823 --case <unit> --out-dir .work/unit-batch12c-evidence
```

每 session 先 ZIP 后 `purge=0`；原始产物留在本地 ignored `.work`。

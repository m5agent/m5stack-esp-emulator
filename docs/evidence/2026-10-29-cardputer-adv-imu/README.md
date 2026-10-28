# 2026-10-29：Cardputer-ADV 当前参考固件 BMI270 闭环

## 结论

官方 UIFlow2 `v2.5.3` Cardputer-ADV 参考固件在当前 QEMU
`f0eb5f6c…` 上通过板载 BMI270 数据面。器件位于 I2C `0x69`，guest
完成 CHIP_ID/软复位/INIT 序列，并通过官方 `Imu.getAccel()` /
`Imu.getGyro()` 读取 QOM 注入值。原样矩阵用例与 Device Service
会话均通过，不再需要修改 QEMU 传感器模型。

因此，Backlog 中“Cardputer-ADV 当前参考样本的 IMU 全零”已从开放项
移除。历史完整矩阵中的 Cardputer-ADV IMU 失败仍对旧 runtime/commit
有效，不回写成 PASS。

## 身份与范围

| 项目 | 值 |
| --- | --- |
| Validation | `virtual-device validation` |
| Physical hardware | `NOT RUN` |
| Device | `cardputer-adv` / `m5cardputeradv` |
| Base firmware SHA256 | `a3961c8eda7358771c8e06c9160648e87ada973d23c6f71c9939b76fa973bed9` |
| Device Service composed firmware SHA256 | `ea9fb400cdcb64f8020b4a43fca24c06f88097d7805b8dc2292185281d48c077` |
| Probe source SHA256 | `619f7d493161de5d1e94a282f4e60af932bbbe805125a37b4f14fda098b027c9` |
| QEMU SHA256 | `f0eb5f6c26f82ce99d6dad4006fcd0748991ba1a8d1ce780092d57d01d8e798e` |
| I2C address | `0x69` |

## 可执行证据

Device Service `/api/v1` 会话使用原样
`tests/uiflow2/cardputer_adv_peripherals/main.py`。QOM 在 guest READY
标记后注入：

- accel：`0.25 / -0.50 / 0.75 g`
- gyro：`10 / -20 / 30 dps`

串口输出：

```text
CARDPUTER_ADV_IMU_ACCEL 0.25 -0.5 0.75
CARDPUTER_ADV_IMU_GYRO 10.009766 -20.019532 30.029296
```

同一会话的 evidence ZIP 保留 QEMU I2C trace：

- 读取 CHIP_ID `0x00 -> 0x24`；
- 写软复位 `0x7E <- 0xB6`；
- 写 `INIT_DATA`、`INIT_CTRL`；
- 读取 accel/gyro 数据寄存器 `0x0C..0x17`；
- `INT_STATUS_1`/`STATUS` 的数据就绪位可达。

最终 frame 为 `240x135` RGB、`5,519` 个非黑像素，左上角为
`(0,255,0)`；frame SHA256
`a05b389509396e9c6d878b5f783a599c55a96074ef69f9418ca73338112d2b72`。
同一 frame 也由仓库原样定向矩阵 `cardputer-adv-imu` 生成，该轮
`attempts=1`、`retry_used=false`，四个 case checks 全部 PASS。

## 复现入口

```bash
python3 platform/tools/serve.py <isolated-local-port> \
  --state-dir <ignored-state-dir> \
  --max-sessions 2 --max-per-device 2

PYTHONPATH=platform/tools:tests/uiflow2 \
  .work/issue-review-venv/bin/python3.12 \
  tests/uiflow2/api_sweep/run_hardware_guest.py \
  --api <isolated-local-service-origin> \
  --device cardputer-adv \
  --source tests/uiflow2/cardputer_adv_peripherals/main.py \
  --runtime-env-json <i2c-trace-runtime-env.json> \
  --drive-json <qom-injection-schedule.json> \
  --done-marker CARDPUTER_ADV_IMU_GYRO \
  --out-dir <new-ignored-output-dir>

PYTHONPATH=.work/py python3 \
  tests/uiflow2/run_peripheral_matrix.py \
  --case cardputer-adv-imu \
  --out-dir <new-temporary-output-dir>
```

## 边界

- 本结果证明当前固件、板级 I2C 路由、BMI270 寄存器模型、官方 API、
  注入值回读、串口和可见 frame 的同一 guest 闭环。
- 不证明物理 IMU 精度、噪声、温漂、轴向装配、量程误差、电气性能或
  真机时序。
- 不属于其它固件 SHA、其它板型或外部传感器数据源。

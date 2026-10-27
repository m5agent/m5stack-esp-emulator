# ESP32-S3 Unit ADC 合成校准

核对日期：`2026-10-27`。

Angle 官方驱动的 `get_voltage()` 调用 MicroPython `ADC.read_uv()`。
空白的虚拟 eFuse 没有有效 S3 ADC 校准版本，ESP-IDF curve-fitting 因而返回
`ESP_ERR_NOT_SUPPORTED`。本方案给特定固件的新虚拟 session 提供合成校准，
保留官方驱动、MicroPython API、IDF curve-fitting 和 QEMU SAR 采样路径。
它证明的范围是可复现的虚拟 ADC 行为，不是真机精度、电气或生产校准。

## 固定输入与准入

- Fixture：`platform/units/fixtures/esp32s3-adc-calibration.json`。
- Helper：`platform/tools/unit_adc_fixture.py`，仅修改传入的内存
  `bytearray`，不写文件、不烧录、不接触物理设备。
- 后端：`qemu-esp32s3`，4096 字节 compact virtual eFuse。
- 参考 UIFlow2 `V2.5.3`，镜像声明的 IDF 版本为 `v5.5.5-dirty`。
- 原始参考固件 SHA256：
  `1324f12d3ddd5392f47a9eff537f9ce0b01a8e6e36d829b6bd22cdf82d2c1264`。
- 固定 app 起点 `0x10000`，ESP image headers 与 segment bytes 共
  `10018400` 字节，实际字节 SHA256：
  `c797c5c747fd5747233048b9e833137d5b7bd6d70da3f1135403614e3a9e442f`。

准入核对实际 app bytes；镜像自声明的 ELF SHA 或版本字符串不能替代它。
VFS/NVS 等 app 范围以外的 session overlay 可以变化。未知或修改过的 app
不能套用该 fixture。公开同版本 IDF 是数值公式依据；`dirty` 固件私有改动
与公开源码逐字相同并未得到证明，最终行为仍须由同一 session 的 guest
数据和控制器计数核对。

## Cardputer-ADV 电池 ADC

Cardputer-ADV UIFlow2 `V2.5.3` 的 `Power.getBatteryLevel()` 走同一 IDF
curve-fitting scheme。单独 fixture
`platform/units/fixtures/cardputer-adv-adc-calibration.json` 绑定 Cardputer
参考镜像 `a3961c8e…` 的实际 app segment
`b5cc34b9…`；session 仍可用不同 VFS/NVS overlay。Service 只在该设备、
`qemu-esp32s3` 且 app bytes 匹配时应用，receipt 写入
`units/adc-calibration.json`。该路径已使真实 `Power.getBatteryLevel()` 和
Canvas/键盘/扬声器/IMU 启动标记到达可见 frame；它不是物理电池、ADC
精度、GPIO 电气或生产校准证据。

## 官方依据

Fixture 为每份来源记录不可变 URL、commit 和 SHA256。ESP-IDF 固定为
[`b774170ff46c393eeb5e495ea37936038d3f4f4f`](https://github.com/espressif/esp-idf/tree/b774170ff46c393eeb5e495ea37936038d3f4f4f)。
核对过完整 SHA256 与 Git blob 的主要文件是：

- [S3 eFuse 字段表](https://github.com/espressif/esp-idf/blob/b774170ff46c393eeb5e495ea37936038d3f4f4f/components/efuse/esp32s3/esp_efuse_table.csv)。
- [S3 V1 校准解码](https://github.com/espressif/esp-idf/blob/b774170ff46c393eeb5e495ea37936038d3f4f4f/components/efuse/esp32s3/esp_efuse_rtc_calib.c)。
- [IDF curve-fitting](https://github.com/espressif/esp-idf/blob/b774170ff46c393eeb5e495ea37936038d3f4f4f/components/esp_adc/adc_cali_curve_fitting.c)。
- [S3 第二阶段系数](https://github.com/espressif/esp-idf/blob/b774170ff46c393eeb5e495ea37936038d3f4f4f/components/esp_adc/esp32s3/curve_fitting_coefficients.c)。
- [MicroPython ADC 实现](https://github.com/micropython/micropython/blob/78ff170de9e32c79db6e64d3e33d2bd60002bdcd/ports/esp32/adc.c)
  与 [read_u16 实现](https://github.com/micropython/micropython/blob/78ff170de9e32c79db6e64d3e33d2bd60002bdcd/ports/esp32/machine_adc.c)。
  MicroPython commit 来自 M5Stack UIFlow 仓库固定
  `3a86d8f611b3639cca755a933e01a5a829771ef1` 的 gitlink。

Espressif 数值与字段定义的派生部分遵守 Apache-2.0；版权
`2019-2023 Espressif Systems (Shanghai) CO LTD`，本项目添加合成 fixture、
冻结准入、位掩码和 host harness。完整许可在
`platform/units/fixtures/LICENSE.Espressif-ADC`。

## 位布局与合成参考

QEMU `hw/nvram/esp_efuse.c` 的 compact 文件布局中 BLOCK0/BLOCK1
各占 24 字节，BLOCK2 从 byte48 开始。bit_start 是 block 内低位在前的偏移，
不能当成线性 32 字节 block。

| 字段组 | Block | bit_start | bit_count | 合成值 |
| --- | --- | --- | --- | --- |
| `BLK_VERSION_MAJOR` | 2 | 128 | 2 | 1 |
| `ADC1_INIT_CODE_ATTEN0..3` | 2 | 149,157,163,169 | 8,6,6,6 | 全0 |
| `ADC2_INIT_CODE_ATTEN0..3` | 2 | 175,183,189,195 | 8,6,6,6 | 全0 |
| `ADC1_CAL_VOL_ATTEN0..3` | 2 | 201,209,217,225 | 全8 | 79,96,66,223 |
| `ADC2_CAL_VOL_ATTEN0..2` | 2 | 233,241,248 | 8,7,7 | 40,10,20 |
| `ADC2_CAL_VOL_ATTEN3` | **1** | **186** | 6 | 15 |

`INIT_CODE` 的零是明确的合成差分 baseline，不是从真机读取的校准值。
V1 解码后 ADC1 init code 为 `[1850,1940,1940,2010]`，ADC2 为
`[2020,2020,2020,2020]`。版本字段是共享 eFuse 元数据；本 fixture 未提供
温度传感器等其他校准，也不对其准确性作保证。

当前 S3 Unit SAR 的 12-bit 理想传递使用 attenuation `0..3` 满量程
`[950,1250,1750,3100]` mV：

```text
raw = min(4095, floor(input_mv * 4095 / full_scale_mv[atten] + 0.5))
```

因此 850mV 参考 raw 为 `[3664,2785,1989,1123]`。V1 采用无符号差分递推：

```text
adc1[3] = diff1[3] + 900
adc1[2] = diff1[2] + adc1[3] + 800
adc1[1] = diff1[1] + adc1[2] + 700
adc1[0] = diff1[0] + adc1[1] + 800
adc2[i] = adc1[i] - diff2[i] + [40,10,20,15][i]
```

上述 fixture 使 ADC1/2 都解码成同一组理想参考。Helper 只允许表内 17
个精确字段，并校验 layout、类型、版本、SAR profile 和解码结果。旧字段
只允许空白0或完全等于目标；任何冲突都在提交前拒绝整次修改。仅 OR 白名单位，
其余所有字节保持原样；不导入或生成 MAC、unique ID、package/revision、
security/key、OCODE 或真实芯片校准数据。

## 数值 oracle

12-bit MicroPython `read_u16()` 的扩展是 `(raw << 4) | (raw >> 8)`。
`read_uv()` 则先执行真实 `adc_oneshot_read`，再由 IDF 读取 eFuse 参考：

```text
gradient = floor(65536 * 850 / reference_raw)
first_mv = floor(raw * gradient / 65536)
read_uv = (first_mv - IDF_fixed_curve_error(first_mv)) * 1000
```

第二阶段保留官方整数系数、逐项截断和 `uint64_t` 乘法语义，所以电压 API
不会简单等于输入 mV 乘1000。ADC1/atten3 的部分参考为：

| 输入 mV | raw12 | read_uv |
| --- | --- | --- |
| 0 | 0 | 0 |
| 500 | 660 | 507000 |
| 850 | 1123 | 846000 |
| 1250 | 1651 | 1232000 |
| 2500 | 3302 | 2427000 |
| 3100及以上 | 4095 | 2912000 |

Host 检查可调用 `expected_ideal_input(1250)` 得到
`raw_12bit=1651, read_u16=26422, read_uv=1232000`，或对已知原始采样调用
`expected_read_uv(raw, attenuation=3, adc_unit=1)`。这两个函数仅用于测试期望，
不作为 guest 返回值或运行时数据来源。

`tests/units/adc_reference_oracle.c` 保留固定官方源码中未改动的
`get_reading_error` 函数体与完整 S3 系数/sign 数组；只补充 host typedef、
logging stub、第一阶段整数表达式和输出循环。80 个向量覆盖两个 ADC、四种
attenuation 和十个 raw 输入。Fixture 记录函数体、系数片段和 harness 的
SHA256，host 测试现场编译 C 并与 Python oracle 及固定向量逐项比较。
Host C 执行不算 guest 或 virtual-device PASS。

## 服务接入与证据

Angle/Light 使用会话冻结的 Unit fixture；Cardputer-ADV 使用 app-bound
Cardputer fixture。Unit contract 在创建时
读取固定白名单 fixture 一次，将 `{raw_utf8,sha256}` 存入
`contract.fixtures['esp32s3-adc']`，并登记 `source_hashes`。Launch 校验该
冻结 hash，调用 `load_fixture(raw=raw)`，用实际 app bytes 通过准入后调用：

```python
receipt = apply_s3_adc_calibration(
    efuse_buffer, backend="qemu-esp32s3", firmware=firmware_bytes,
    fixture_raw=frozen_utf8_bytes,
)
```

传 `fixture_raw` 时 helper 不再读取当前磁盘 fixture；receipt 的 SHA256
也绑定同一 bytes。未知 app 由服务保留原 eFuse 并记录
`not-applied`/`raw-only` 及原因，不应阻止通用固件启动；helper 本身严格拒绝。

Session 证据文件为 `unit-adc-calibration.json`，ZIP entry 为
`units/adc-calibration.json`。成功 receipt 包含 fixture id/hash、
`status=applied`、`source=session-frozen-fixture`、真实 app segment hash、
SAR profile、850mV/raw 参考、17字段以及 `hardware_validation=false`。
仍需同 session 的 QOM 注入、guest 官方 API、SAR sample counter、serial、
frame 和 stop 前 ZIP 建立数据面证据；host fixture 检查不能代替该步骤。

Host 检查命令：

```bash
PYTHONPATH=platform/tools:.work/py312 python3.12 -m unittest discover \
  -s platform/tests -p test_unit_adc_fixture.py -v
python3.12 platform/tools/unit_adc_fixture.py --check
python3.12 platform/tools/unit_adc_fixture.py --input-mv 1250
```

本次 host 输出、来源核验和真实缓存镜像的内存准入 smoke 位于
`docs/evidence/2026-10-26-unit-adc-fixture/`。该目录不包含 BIN、eFuse
镜像或机器身份数据。实际 Angle guest 结果由 Unit IO 验证记录管理。

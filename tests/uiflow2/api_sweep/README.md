# UIFlow2 全接口验证入口

本目录将官方文档、候选官方源码与两个真实 guest 的导出对账，并保存逐接口
功能 recipe。CoreS3 使用 M5UI/LVGL；Cardputer-ADV 使用 Display/Widgets。
覆盖审计仍在推进；清单存在、recipe 已编写或 `EXECUTED` 均不表示功能通过。

## 清单

- `inventory_ui.source.json`：文档、原生 LVGL 继承/共享成员与 UI 功能 recipe。
- `inventory_hardware.source.json`：硬件、总线、配置及实例返回类型的公开接口。
- `inventory_system.source.json`：系统/通信候选接口及可选外接产品目录；源码
  commit 不自动绑定参考固件，须以两款固件实际导出重新准入。
- `inventory_api.source.json`：完整 Device Service OpenAPI operation 分母，
  正向场景和拒绝边界分开，入口见 [HTTP 验证说明](README-device-api.md)。

清单生成器接受独立官方 UIFlow2 源码目录。它们只读源码，不能建立 guest
执行证据；测试、示例及未公开 helper 不属于产品公开 API。官方明确文档化的
`M5ESPNow._bytes_to` 等方法即使带下划线也纳入契约。外接产品完整目录
只作为范围对账，联合功能验证使用选定 Unit；未选外设不计主机功能 PASS。

## 可见 guest 执行

使用项目 Python 环境和独立 Device Service；输出必须是新的 ignored 目录。
测试必须显式传入 `--api`，使用独立端口、状态目录和控制凭据；
8787 属于用户测试服务，Agent 不使用、停止或重启它。

```sh
PYTHONPATH=platform/tools:.work/py312 python3.12 \
  tests/uiflow2/api_sweep/run_guest.py \
  --api http://127.0.0.1:8788 \
  --device cores3 --source /path/to/finite_probe.py \
  --done-marker MY_PROBE_DONE --out-dir .work/api-sweep/my-probe \
  --token-file /path/to/device-service-token
```

`run_guest.py` 按实际固件分区表准备 VFS，通过 API 上传、创建可见会话、
分页读取串口、采集帧和 evidence ZIP，再 `purge=0` 停止并核验历史和 PID。
它不直接启动 QEMU。`run_hardware_guest.py` 在相同生命周期中按 guest
marker 驱动真实输入/QOM 请求。交互式程序使用 Device Service `/program`
和明确的 `expected_execution_id`；START、应用 READY 与测试完成分别记录。

## 结果规则

每个功能结论绑定设备、固件与运行时 SHA、源码、会话以及相关帧/输入/
controller 或 PCM/pcap 证据。setter/getter 对账、实际像素、输入事件和数据
传输按各接口契约验证。`PRESENT`、`CALL_OK`、导入成功和 HTTP 拒绝仅记录
其各自证据层；无法取得所需 fixture、模型或账户时保留具体 blocker。

原始固件、ZIP、Flash、完整串口和逐帧结果保留 ignored `.work/`，不提交。
源码库只保存必要的小型摘要、哈希和复现入口。全部会话结果属于
virtual-device validation，不能继承为真机结果或物理精度结论。

通信、TLS、BLE 固件 lane 与逐方法合并规则见
[protocol runners](README-protocols.md)。

SPI SD、独立 FAT/PCM/相机 oracle 与输入证据边界见
[hardware probes](README-hardware.md)。

## Cardputer 原生音频

在独立 Device Service 选择原生 Xtensa 运行时及对应的 ROM 和构建依赖。
使用设备各自的原厂 UIFlow2 合并镜像并核对[证据中的 SHA](cardputer-audio-summary.json)。
`DEVICE` 取 `cardputer` 或 `cardputer-adv`，`MODE` 取 `tone` 或 `silence`。
`DEVICE_SERVICE_URL` 是隔离服务的 origin，`BASE_IMAGE`、`BASE_SHA256`、
`TOKEN_FILE`、`RUN_ROOT` 指向本次测试的镜像、摘要、凭据和输出位置。

```sh
mkdir -p "$RUN_ROOT/fixture-$MODE"
printf '%s\n' "$MODE" > "$RUN_ROOT/fixture-$MODE/audio-test.mode"
python3 tests/uiflow2/api_sweep/run_hardware_guest.py \
  --api "$DEVICE_SERVICE_URL" --token-file "$TOKEN_FILE" \
  --device "$DEVICE" --runtime qemu --base-image "$BASE_IMAGE" \
  --expected-base-sha256 "$BASE_SHA256" \
  --source tests/uiflow2/api_sweep/probe_cardputer_audio.py \
  --fixture-dir "$RUN_ROOT/fixture-$MODE" --done-marker NATIVE_AUDIO_FINISHED \
  --out-dir "$RUN_ROOT/$DEVICE-$MODE"
python3 tests/uiflow2/api_sweep/verify_cardputer_audio.py "$RUN_ROOT/$DEVICE-$MODE" "$MODE"
```

静音轮次在可信本地服务允许的测试目录中生成一秒 32,000 字节的全零 PCM。
运行同一命令时增加 `--runtime-env-json`，其文件只设置
`M5SW_I2S_RX_PCM_FILE` 为该 PCM 的绝对路径。默认生成的 440 Hz 注入源
和原生输出都进入 tone 轮次的同会话 ZIP。静音轮次的 host 输入覆盖
仅保留 provenance，ZIP 保留由 pilot 起始的实际 TX 和后续静音样本。来宾
从正常 `M5.Mic.record` 收集 16 kHz 单声道采样，经 UART 取回；`M5.Speaker.playRaw`
提交 8 kHz、660 Hz 输入，再按来宾报告的 48 kHz 单声道 I2S1 格式分析
native TX。RMS 是数字采样值。浏览器、物理麦克风、扬声器声学和供电未执行。

### 同会话的 WAV 替换与 PCM API

准备 16 kHz 单声道、16 位、持续一秒的两份 WAV。一份是峰值 12,000 的
523 Hz 正弦波，一份是零值。分别上传并取得 artifact SHA。使用上面同一
原厂基座与 runner，把 `--source` 改为
`probe_cardputer_audio_api.py`，移除 `--fixture-dir`，并改用
`--done-marker AUDIO_API_DONE --drive-json "$ACTION_FILE"`。动作文件如下。

```json
{
  "AUDIO_API_WAIT tone": [{"endpoint":"audio.inject","payload":{"artifact_id":"<tone SHA>"}}],
  "AUDIO_API_WAIT silence": [{"endpoint":"audio.inject","payload":{"artifact_id":"<silence SHA>"}}],
  "AUDIO_API_DONE": [{"endpoint":"audio.pcm?format=metrics&sample_rate_hz=48000","method":"GET"}]
}
```

从 `AUDIO_API_MIC` UART 行按相位和偏移重建每次 3,200 个 s16le 样本。
第一轮主频应在 523 Hz 附近。零值源切换后，来宾录音可能有前一次音色的滤波
余量，检查 RMS 显著降低及末段 RMS。按来宾公布的 48 kHz 单声道 I2S1 检查
扬声器主频约 660 Hz。停止后分段读取 `/audio.pcm`，比对同会话 ZIP 中的
`audio/speaker.pcm` 和各段 SHA-256。最后一份暂存的麦克风 PCM 摘要位于
`manifest.json`。两块板各一轮、所有租约释放的 [virtual-device 证据](cardputer-audio-api-summary.json)。

### 原版 MP3 的审核播放断言

通过审核服务载入 Cardputer ADV MP3 Player v1.0.0 原版 app BIN，准备含
524 Hz 参考音轨的 FAT32 镜像。按[验证记录](cardputer-mp3-review-summary.json)
核对原版、合成 Flash、镜像与运行时的 SHA-256。创建隔离的 dry-run 并保存
验证方案。按键使用 `key_ret`，保持 0.1 秒、等待 1.4 秒。音频方案为
`validation.audio_playback`，声明 `after_input=key_ret`、48 kHz、524 Hz、8 Hz
容差和 RMS 下限 100。确认报告为 `PASS`，根据记录的偏移和 SHA-256 在同会话
ZIP 回验 PCM。对照轮次分别将频率改为 880 Hz 和撤去会话的 `audio.read` 权限，
报告分别给出 `E_SIM_AUDIO_ASSERTION_FAILED` 和 `E_SIM_AUDIO_PARTIAL`。每轮结束
检查租约释放。此处为原生虚拟设备验证。

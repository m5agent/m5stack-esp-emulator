# Core2 UIFlow2 首帧、离线 WLAN 与 LVGL

日期：2026-10-27。起点：`a0ad8150`。类型：`virtual-device validation`。

## 根因与修复

1. 普通 Core2 会话的默认 NIC 被 Ethernet 消费后，没有创建片上 WiFi MAC。
   同一 stock UIFlow2 程序能创建 `WLAN` 对象，却在 `active(True)` 内轮询
   未映射的寄存器。原始最小复现的 584-byte 背景帧 SHA 与 issue #3 一致。
   `0049` 在没有显式 WiFi NIC 时仍连接真实 MAC/MMIO/DMA/IRQ，并关闭 radio
   和 AP 定时器；不会隐式建立宿主网络。显式 WiFi NIC 保持原路径。
2. 普通 Core2 会话遗漏了 radio 会话已有的 deterministic clock。
   服务现在对两者使用同一有界 TCG/icount 参数，S3 参数不变。
3. 实际截图检查发现 UIFlow2 LVGL 标题被撕成横条。SPI 模型在 DMA
   `OUT_LINK START` 时消费描述符，又在 `USR` 时发送旧 FIFO，造成重复写。
   `0050` 改为在 `USR` 按实际长度消费描述符一次，并避免越界读取 FIFO。
   初始串口 DONE/非黑像素不足以发现该错误，新增字形区域与条纹负控。
4. 冷构建脚本补回仓库已有的 `0034` equal-CCOMPARE 修复。
   它是构建栈一致性修复，不作为缺失 WiFi MAC 的直接根因。

## 固件与运行时身份

- stock base：UIFlow2 `V2.5.3`，SHA256
  `b228c0e2d877e77a8a352e917ed84f4da8ea92d15b25e28f431a2999620fe3c4`；
- stock application header-through-final-segment SHA256：
  `c02171cfdde7a51e19c40dbe3e1e1b95033a0087591d34c69f88ebbfdd49de47`；
- 探针只替换 LittleFS VFS，逐字节检查 VFS 外未变化；
- 最终 Xtensa runtime SHA256：
  `712851db882fed73696a2598f9ba5c036d4d26a21e7ef11e59aca41ca1e84f2e`；
- QEMU base `40edccac415693c5130f91c01d84176ae6008566`，完整补丁栈、
  source receipt、各派生镜像/源码/串口/帧/ZIP 哈希见 [summary.json](summary.json)。

## 验证路径

底层绘图、Widgets、M5UI/LVGL 和离线网络探针全部使用可见 Device Service
session；先导出并校验 ZIP，再 `purge=0&retain_flash=0` 停止。检查真实运行
binary/PID/start token、QOM radio 状态、历史末帧、串口、Flash 释放和 PID 退出。
LVGL 同一源码修复前后由全宽横条变为正常可读标题；最终截图已经人工打开检查。
最后补强的历史串口门禁另外对四份已保留原始日志复验，均没有 ZIP 后新增
reset/traceback；该次检查属于离线复验，没有倒填原执行时的工具身份。

```bash
PYTHONPATH=platform/tools:.work/py312 python3.12 \
  tests/firmware/core2_startup/run_service_test.py \
  --case all --out-dir .work/core2-startup/replay \
  --expected-runtime-sha256 712851db882fed73696a2598f9ba5c036d4d26a21e7ef11e59aca41ca1e84f2e \
  --runtime-source-receipt .work/core2-runtime-final/source-receipt.json \
  --token-file <local-service-token-file>
```

运行器不启动服务或 QEMU。平台单元测试、实际 C patch replay、设备组及完整
外设矩阵结果在最终 summary 中分别记录；未通过的原始轮次保留在本地归档。
平台 1261 项测试通过（1 skipped），Core2 设备组 6/6、24 checks 通过。
完整矩阵为 66 PASS / 1 FAIL，无自动重试；Cardputer-ADV IMU 在本次运行时和
未修改主线冷构建上使用同一派生固件都失败，保留为既有样本缺口，不能把定向
通过拼接成 67/67。板型识别/I2C 初始化仍需另行定位。
源码分支只保存小型总结，不保存固件、ROM、大 ZIP 或完整请求响应。
显式网络回归的可重放入口是
[`run_radio_service_test.py`](../../../tests/firmware/core2_startup/run_radio_service_test.py)；
两次会话使用同一 headless probe，只替换本地受控 HTTP fixture 端口，黑帧
不作为显示结果。完整命令见[运行器说明](../../../tests/firmware/core2_startup/README.md)。

## 验证边界

- issue #2/#3 的公开最小启动路径已复现；原始私有完整应用归档尚未取得，
  不声称四份完整应用、私有后端或全部业务已通过。
- 离线 NTP 请求实际在发送时返回 `OSError(118)`，证明传输错误有界；
  不表示完成了公网 NTP 校时、DNS 或收包超时验证。
- 旧 UIFlow1 `v1.15.4` 的 LVGL7 interrupt/completion wait 仍属于
  `RUNTIME-03`，不能由本次 UIFlow2 LVGL 结果关闭。
- RF、功耗、电气和物理硬件验证为 `NOT RUN`。

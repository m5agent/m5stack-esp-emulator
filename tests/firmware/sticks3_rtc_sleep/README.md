# StickS3 原生 RTC 浅睡与唤醒

## 原版 All day watch 0.3.8

以 [留存原版和同会话记录](all-day-watch-native.summary.json)中的上传 BIN、
规范化 Flash 和 ROM SHA-256 为准，在独立 Device Service 启动 `sticks3`、
`runtime=qemu` 的离线会话。以第一次有效帧作为输入顺序的起点。
先点 A、点 B，再按下 B 并间隔约 2.28 秒释放。历史顺序的各次派发约为
2.33、3.37、4.45、6.73 秒。快速释放负对照使用相同按键顺序且取消额外等待。

等待独立 QMP `query-status` 读到 `suspended`，保留无输入观察，
再通过 Device Service 输入 B 键。验收读取 QMP `running`、最终非黑帧、
一个上电启动、65 秒内的串口与后端看门狗记录。先获取证据 ZIP，
以 `purge=0` 停止并核对租约释放。原始失败、观测版和中间候选分别保留。

Device Service 1.87 的复验在挂起后使用 `kind=button control=b action=click`，
回执记录宿主计时及已发送按下和释放。原版保持一个启动且观察窗内无 IWDT。
[语义按钮同会话证据](device-service-semantic-wake.summary.json)

服务接管的复验在同一隔离设备服务中断后使用原状态目录启动下一代服务。
接回挂起的同一 QEMU 进程与会话，语义 B 键唤醒来宾，并通过 GPIO12 读回确认释放。
[服务重启与唤醒证据](device-service-suspend-reattach.summary.json)

ESP32-S3 [RTC 寄存器定义](https://github.com/espressif/esp-idf/blob/v5.4.1/components/soc/esp32s3/register/soc/rtc_cntl_reg.h)
和 [SDK 完成轮询](https://github.com/espressif/esp-idf/blob/v5.4.1/components/esp_hw_support/port/esp32s3/rtc_sleep.c)
限定本项为数字 GPIO 浅睡的拒绝与唤醒。RTC 慢时钟睡眠期间的耗时、定时、组合唤醒源、深睡、浏览器和真机是独立验收项。

## 定时唤醒负对照

该 ESP-IDF 探针通过 `esp_sleep_enable_timer_wakeup` 和
`esp_light_sleep_start` 测试 ESP32-S3 定时唤醒。来宾依次请求
100 ms 和 220 ms 睡眠，两次之间由 FreeRTOS 调度一个 50 ms 的等待。

使用 ESP-IDF v5.5.4 `735507283d5b2f9fb363a1901172dbd9e847945d` 和
仓库根目录的忽略目录构建。Flash 规格为 StickS3 的 8 MiB。

```sh
source "${IDF_PATH}/export.sh"
mkdir -p .work/sticks3-rtc-sleep-build
idf.py -C tests/firmware/sticks3_rtc_sleep \
  -B "${PWD}/.work/sticks3-rtc-sleep-build" \
  -D "SDKCONFIG=${PWD}/.work/sticks3-rtc-sleep-build/sdkconfig" build
idf.py -C tests/firmware/sticks3_rtc_sleep \
  -B "${PWD}/.work/sticks3-rtc-sleep-build" merge-bin --fill-flash-size 8MB
```

通过独立 Device Service 的 `sticks3` 原生 `qemu` 会话启动合并镜像。
完整串口必须先出现一次 `RTC_SLEEP_BOOT`，再按顺序出现两组
`RTC_SLEEP_ENTER`、`RTC_SLEEP_RETURN` 和一次 `RTC_SLEEP_PASS iterations=2`。
两次返回均需 `status=0`，且 `cause` 需匹配启动行的 `timer_cause`。
`elapsed_us` 来自 `esp_timer_get_time`，最多允许比请求值早 5 ms。
设置主机观察期限。停在 `ENTER`、失败标记或重新启动均表示该次测试失败。
取证绑定固件、运行时和 ROM 的 SHA-256，保存同一会话串口和证据包。
停止后核对运行时和租约清理。探针覆盖定时器触发的浅睡唤醒。

## B 键 GPIO 唤醒

GPIO 版本在独立构建目录启用 `M5_RTC_GPIO_WAKE`。使用相同 ESP-IDF、
Flash 规格与合并命令。

```sh
mkdir -p .work/sticks3-rtc-gpio-build
idf.py -C tests/firmware/sticks3_rtc_sleep \
  -B "${PWD}/.work/sticks3-rtc-gpio-build" \
  -D "SDKCONFIG=${PWD}/.work/sticks3-rtc-gpio-build/sdkconfig" \
  -D M5_RTC_GPIO_WAKE=ON build
idf.py -C tests/firmware/sticks3_rtc_sleep \
  -B "${PWD}/.work/sticks3-rtc-gpio-build" merge-bin --fill-flash-size 8MB
```

探针通过 `gpio_wakeup_enable` 给 GPIO12 配置低电平唤醒，并通过
`esp_sleep_enable_gpio_wakeup` 启用该唤醒源。启动时保持 B 键释放。
串口出现 `RTC_GPIO_SLEEP_ENTER` 并经过无输入观察窗口后，通过
正常板级按键路径按住 B 键，取得 `RTC_GPIO_SLEEP_RETURN` 后释放。
验收需要一个 `RTC_GPIO_SLEEP_BOOT`、B 键动作前无返回、动作后
`status=0`、`cause` 匹配启动行的 `gpio_cause` 及 `RTC_GPIO_SLEEP_PASS`。
记录输入事件、返回串口和同会话 ZIP。另起会话保持 B 键释放可校验
观察窗口内无自发返回。

## 检查进入睡眠时已为低电平的 B 键

在新构建目录对 GPIO 版本同时加 `-D M5_RTC_GPIO_REJECT=ON`。
B 键按下后保持，直到 `RTC_GPIO_REJECT_PASS` 或失败标记再释放。
同一来宾先完成睡眠和唤醒，再通过 `esp_light_sleep_start` 请求第二次睡眠。
第二次请求前 B 键必须为低电平，RTC 拒绝原因应为零。检查 API 返回
`ESP_ERR_SLEEP_REJECT`、RTC 拒绝原因为 GPIO，及 SDK 清除中断状态后
`sleep_raw=0x0`。最后通过 W1C 写入清除拒绝原因并检查读回。
`RTC_GPIO_REJECT_PASS` 表示这些断言在一次启动中均满足。

[ESP-IDF 来宾观测](rtc-light-sleep-fixture.summary.json)保存定时基线、旧版 GPIO 失败、中间候选及最终唤醒和拒绝结果。

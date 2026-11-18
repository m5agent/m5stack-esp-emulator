# StickS3 RTC 定时唤醒探针

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
观察窗口内无自发返回。GPIO 模式覆盖 B 键唤醒。睡眠请求前已按住 B 键的
拒绝路径仍待独立验证。

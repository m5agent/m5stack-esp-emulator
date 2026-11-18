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
